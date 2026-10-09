import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import cint, escape_html, flt, getdate

from ai_form_builder.services import form_spec, spec_renderer
from ai_form_builder.services.project_form_service import configuration_dict, find_configuration

TRUE = ("1", "true", "yes", "on")


class AIFormRecord(Document):
	"""One filled-in copy of a spec form. Every spec form shares this DocType."""

	def autoname(self):
		code = self.form_code or frappe.db.get_value("AI Form Template", self.form_template, "template_code")
		self.name = make_autoname(f"{code}-.#####", doc=self)

	def before_insert(self):
		template = frappe.get_doc("AI Form Template", self.form_template)
		if template.generated_doctype or (template.storage_mode or "Spec") != "Spec":
			frappe.throw(
				_("{0} is a DocType form; open it from its own list.").format(template.template_title)
			)
		if template.status != "Published":
			frappe.throw(_("{0} is not published yet.").format(template.template_title))
		self.form_title = template.template_title
		self.form_code = template.template_code
		self.template_version = template.template_version
		self.reference_doctype = template.reference_doctype if template.enable_project_configuration else None
		# The record keeps the layout it was raised on: a later revision of the
		# form never changes how this record prints.
		self.spec_snapshot = template.spec_json

	def validate(self):
		if self.is_new() and not self.spec_snapshot:
			self.before_insert()
		spec = self.spec()
		self._clean_values(spec)
		self._clean_rows(spec)
		rules = self._project_rules()
		self._check_reference_access()
		self._check_read_only(rules)
		if self.status == "Completed":
			self._check_mandatory(spec, rules)

	# ------------------------------------------------------------------ data
	def spec(self) -> dict:
		try:
			return json.loads(self.spec_snapshot or "{}")
		except ValueError:
			return {}

	def values_dict(self) -> dict:
		return {row.field_name: row.value for row in self.get("values") or ()}

	def grid_rows_dict(self) -> dict:
		rows = {}
		for row in sorted(self.get("rows") or (), key=lambda r: (r.row_group, cint(r.row_no))):
			try:
				cells = json.loads(row.cell_values or "{}")
			except ValueError:
				cells = {}
			rows.setdefault(row.row_group, []).append(cells if isinstance(cells, dict) else {})
		return rows

	def set_data(self, values: dict | None = None, grids: dict | None = None):
		"""Replace the entered data (the form page posts everything at once)."""
		spec = self.spec()
		fields = form_spec.field_map(spec)
		if values is not None:
			self.set("values", [])
			for name, field in fields.items():
				if name in values:
					self.append(
						"values",
						{
							"field_name": name,
							"label": field.get("label"),
							"field_type": field["type"],
							"value": values[name],
						},
					)
		if grids is not None:
			self.set("rows", [])
			for name, grid in form_spec.grid_map(spec).items():
				posted = grids.get(name) or []
				columns = {column["name"] for column in grid.get("columns") or ()}
				for number, cells in enumerate(posted, 1):
					if not isinstance(cells, dict):
						continue
					cells = {key: value for key, value in cells.items() if key in columns}
					self.append(
						"rows", {"row_group": name, "row_no": number, "cell_values": json.dumps(cells)}
					)

	def render_html(self) -> str:
		return spec_renderer.render_html(self.spec(), self.values_dict(), self.grid_rows_dict())

	# ------------------------------------------------------------------ checks
	def _clean_values(self, spec):
		fields = form_spec.field_map(spec)
		kept = []
		for row in self.get("values") or ():
			field = fields.get(row.field_name)
			if not field:
				continue
			row.label = field.get("label")
			row.field_type = field["type"]
			row.value = _coerce(field, row.value)
			kept.append(row)
		self.set("values", kept)

	def _clean_rows(self, spec):
		grids = form_spec.grid_map(spec)
		kept = []
		by_grid = {}
		for row in self.get("rows") or ():
			grid = grids.get(row.row_group)
			if not grid:
				continue
			try:
				cells = json.loads(row.cell_values or "{}")
			except ValueError:
				cells = {}
			columns = {column["name"]: column for column in grid.get("columns") or ()}
			cells = {
				key: _coerce(columns[key], value) for key, value in (cells or {}).items() if key in columns
			}
			by_grid.setdefault(row.row_group, []).append((row, cells))
		for name, rows in by_grid.items():
			grid = grids[name]
			fixed = grid.get("fixed_rows") or []
			if len(rows) > len(fixed) and not grid.get("allow_add", True):
				frappe.throw(_("{0} takes no extra rows.").format(grid.get("label") or name))
			for index, (row, cells) in enumerate(rows):
				# Pre-printed text cannot be changed from the form.
				if index < len(fixed):
					cells.update(fixed[index])
					row.is_preprinted = 1
				else:
					row.is_preprinted = 0
				row.row_no = index + 1
				row.cell_values = json.dumps(cells, ensure_ascii=False)
				kept.append(row)
		self.set("rows", kept)

	def _project_rules(self) -> dict:
		"""Per-project show/require/read-only rules, frozen on first save."""
		if not (self.reference_doctype and self.reference_name):
			return {}
		if self.configuration_snapshot and not self.is_new():
			try:
				return json.loads(self.configuration_snapshot)
			except ValueError:
				pass
		configuration = find_configuration(self.reference_doctype, self.reference_name, self.form_template)
		if not configuration or not configuration.enabled:
			frappe.throw(_("This form is not enabled for {0}.").format(self.reference_name))
		rules = configuration_dict(configuration)
		self.project_configuration = configuration.name
		self.configuration_snapshot = json.dumps(rules, sort_keys=True)
		return rules

	def _check_reference_access(self):
		if (
			self.reference_doctype
			and self.reference_name
			and not frappe.has_permission(self.reference_doctype, "read", self.reference_name)
		):
			frappe.throw(
				_("You do not have access to {0} {1}.").format(
					_(self.reference_doctype), self.reference_name
				),
				frappe.PermissionError,
			)

	def _check_read_only(self, rules):
		if self.is_new() or not rules:
			return
		before = self.get_doc_before_save()
		if not before:
			return
		old = before.values_dict()
		new = self.values_dict()
		for name, rule in rules.items():
			if (rule["read_only"] or not rule["enabled"]) and (old.get(name) or "") != (new.get(name) or ""):
				label = rule.get("label_override") or name
				frappe.throw(
					_("{0} cannot be changed on this project.").format(label), frappe.PermissionError
				)

	def _check_mandatory(self, spec, rules):
		values = self.values_dict()
		grids = self.grid_rows_dict()
		missing = []
		for field in spec.get("fields") or ():
			rule = rules.get(field["name"])
			required = (rule["mandatory"] and rule["enabled"]) if rule else field.get("mandatory")
			# A tick box answers "no" by staying empty, so it is never missing.
			if required and field["type"] != "Check" and values.get(field["name"]) in (None, ""):
				missing.append((rule or {}).get("label_override") or field.get("label") or field["name"])
		for grid in spec.get("grids") or ():
			rule = rules.get(grid["name"])
			if rule and rule["enabled"] and rule["mandatory"] and not grids.get(grid["name"]):
				missing.append(rule.get("label_override") or grid.get("label"))
		if missing:
			frappe.throw(
				_("Fill in before completing: {0}").format(", ".join(escape_html(m) for m in missing)),
				frappe.MandatoryError,
			)


def _coerce(field: dict, value):
	"""Store every value as text in the shape its type expects."""
	if value is None:
		return ""
	kind = field.get("type")
	text = str(value).strip() if kind != "Signature" else str(value)
	if text == "":
		return ""
	label = field.get("label") or field.get("name")
	if kind == "Check":
		return "1" if text.lower() in TRUE else "0"
	if kind == "Int":
		try:
			return str(int(flt(text)))
		except (TypeError, ValueError):
			frappe.throw(_("{0} must be a whole number.").format(label))
	if kind == "Float":
		try:
			float(text)
		except ValueError:
			frappe.throw(_("{0} must be a number.").format(label))
		return text
	if kind == "Date":
		try:
			return str(getdate(text))
		except Exception:
			frappe.throw(_("{0} must be a date.").format(label))
	if kind == "Select" and text not in (field.get("options") or ()):
		frappe.throw(_("{0} must be one of: {1}").format(label, ", ".join(field.get("options") or ())))
	if kind == "Signature" and not (text.startswith("data:image/") and ";base64," in text):
		frappe.throw(_("{0} must be a drawn signature.").format(label))
	return text
