"""Fill in spec forms. Every spec form's records are AI Form Record rows."""

import frappe
from frappe import _

from ai_form_builder.services import form_spec
from ai_form_builder.services.project_form_service import configuration_dict, find_configuration

RECORD = "AI Form Record"
TEMPLATE = "AI Form Template"


def _rules(template, reference_name, record=None):
	if record is not None and record.configuration_snapshot:
		return frappe.parse_json(record.configuration_snapshot) or {}
	if not (template.enable_project_configuration and reference_name):
		return {}
	configuration = find_configuration(template.reference_doctype, reference_name, template.name)
	return configuration_dict(configuration) if configuration else {}


def _payload(template, record, reference_name):
	spec = record.spec() if record and not record.is_new() else frappe.parse_json(template.spec_json or "{}")
	values = record.values_dict() if record else {}
	grid_rows = record.grid_rows_dict() if record else {}
	if not record or record.is_new():
		values = {f["name"]: f["default"] for f in spec.get("fields") or () if f.get("default")}
		grid_rows = {}
	# Every pre-printed line shows, whether or not the record has answered it yet.
	for grid in spec.get("grids") or ():
		rows = grid_rows.setdefault(grid["name"], [])
		for index, printed in enumerate(grid.get("fixed_rows") or ()):
			if index < len(rows):
				rows[index] = {**rows[index], **printed}
			else:
				rows.append(dict(printed))
	can_write = (
		frappe.has_permission(RECORD, "write", record)
		if record and not record.is_new()
		else frappe.has_permission(RECORD, "create")
	)
	return {
		"name": record.name if record and not record.is_new() else None,
		"form_template": template.name,
		"title": template.template_title,
		"code": template.template_code,
		"revision": record.template_version if record and not record.is_new() else template.template_version,
		"reference_doctype": template.reference_doctype if template.enable_project_configuration else None,
		"reference_name": record.reference_name if record and not record.is_new() else reference_name,
		"status": record.status if record and not record.is_new() else "Draft",
		"record_date": str(record.record_date) if record and record.record_date else frappe.utils.today(),
		"spec": spec,
		"sections": form_spec.form_sections(spec),
		"rules": _rules(template, reference_name, record if record and not record.is_new() else None),
		"values": values,
		"grids": grid_rows,
		"can_write": bool(can_write) and (not record or record.status != "Cancelled"),
	}


@frappe.whitelist()
def get_form(form_template=None, name=None, reference_name=None):
	"""Everything the entry page needs: the spec, the project's rules and the data."""
	if name:
		record = frappe.get_doc(RECORD, name)
		record.check_permission("read")
		template = frappe.get_doc(TEMPLATE, record.form_template)
		return _payload(template, record, record.reference_name)
	if not form_template:
		frappe.throw(_("Choose a form."))
	frappe.has_permission(RECORD, "create", throw=True)
	template = frappe.get_doc(TEMPLATE, form_template)
	if template.status != "Published" or template.generated_doctype:
		frappe.throw(_("{0} is not a published form.").format(template.template_title))
	if template.enable_project_configuration and reference_name:
		if not frappe.has_permission(template.reference_doctype, "read", reference_name):
			frappe.throw(_("You do not have access to {0}.").format(reference_name), frappe.PermissionError)
	return _payload(template, None, reference_name)


@frappe.whitelist()
def save(data, name=None):
	"""Create or update a record from the entry page."""
	data = frappe.parse_json(data) or {}
	if name:
		record = frappe.get_doc(RECORD, name)
		record.check_permission("write")
		if record.status == "Cancelled":
			frappe.throw(_("A cancelled record cannot be changed."))
	else:
		record = frappe.new_doc(RECORD)
		record.form_template = data.get("form_template")
		record.reference_name = data.get("reference_name")
		record.before_insert()
	if data.get("status") in ("Draft", "Completed"):
		record.status = data["status"]
	if data.get("record_date"):
		record.record_date = data["record_date"]
	# A key left out keeps what is stored; a key sent replaces it.
	record.set_data(data.get("values"), data.get("grids"))
	record.save()
	return record.name


@frappe.whitelist()
def download_pdf(name):
	"""Print the record on its sheet and file the PDF on the record."""
	from ai_form_builder.services import spec_renderer

	record = frappe.get_doc(RECORD, name)
	record.check_permission("read")
	content = spec_renderer.render_pdf(record.spec(), record.values_dict(), record.grid_rows_dict())
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{record.name}.pdf",
			"content": content,
			"is_private": 1,
			"attached_to_doctype": RECORD,
			"attached_to_name": record.name,
		}
	).insert(ignore_permissions=True)
	return file_doc.file_url
