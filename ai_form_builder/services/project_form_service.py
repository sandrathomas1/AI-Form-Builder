"""Project-specific display and validation overlays for generated AI forms.

The overlay deliberately stores only field settings.  It never changes the
generated DocType or the master template mapping.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint

SYSTEM_FIELDS = {
	"ai_form_template",
	"ai_form_project_configuration",
	"ai_form_configuration_snapshot",
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
}
LAYOUT_FIELD_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Fold", "Heading"}


def get_template(template_name):
	return frappe.get_doc("AI Form Template", template_name)


def template_rows(template):
	return [
		row
		for row in template.fields
		if not row.ignore_field
		and (getattr(row, "mapping_status", None) or "Active") != "Orphaned"
		and row.final_fieldtype
		and row.final_fieldtype not in LAYOUT_FIELD_TYPES
		and row.fieldname not in SYSTEM_FIELDS
	]


def populate_fields(configuration, preserve=True):
	"""Add missing master fields without changing existing project choices.

	A configuration that uses a field profile stores only its own overrides,
	so it is not filled with master rows.
	"""
	if getattr(configuration, "field_profile", None):
		return configuration
	template = get_template(configuration.form_template)
	existing = {row.fieldname: row for row in configuration.fields}
	for source in template_rows(template):
		if source.fieldname in existing:
			continue
		configuration.append(
			"fields",
			{
				"fieldname": source.fieldname,
				"field_label": source.label,
				"enabled": 1,
				"mandatory": cint(source.mandatory),
				"read_only": cint(source.read_only),
				"is_system_field": 0,
			},
		)
	return configuration


def reset_fields_to_master(configuration):
	"""Reset only the UI overlay; generated fields and saved values are untouched."""
	template = get_template(configuration.form_template)
	configuration.set("fields", [])
	for source in template_rows(template):
		configuration.append(
			"fields",
			{
				"fieldname": source.fieldname,
				"field_label": source.label,
				"enabled": 1,
				"mandatory": cint(source.mandatory),
				"read_only": cint(source.read_only),
				"label_override": "",
				"is_system_field": 0,
			},
		)
	return configuration


def find_configuration(reference_doctype, reference_name, form_template):
	if not all((reference_doctype, reference_name, form_template)):
		return None
	name = frappe.db.get_value(
		"AI Project Form Configuration",
		{
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"form_template": form_template,
		},
	)
	return frappe.get_doc("AI Project Form Configuration", name) if name else None


def rows_dict(rows):
	return {
		row.fieldname: {
			"enabled": bool(row.enabled),
			"mandatory": bool(row.mandatory),
			"read_only": bool(row.read_only),
			"label_override": row.label_override or "",
		}
		for row in rows
	}


def get_profile_rows(profile_name):
	if not profile_name or not frappe.db.exists("AI Form Field Profile", profile_name):
		return []
	return frappe.get_doc("AI Form Field Profile", profile_name).fields


def configuration_dict(configuration):
	"""Effective rules: shared profile first, then this project's own rows."""
	rules = rows_dict(get_profile_rows(getattr(configuration, "field_profile", None)))
	rules.update(rows_dict(configuration.fields))
	return rules


def prune_profile_overrides(configuration):
	"""Keep only the rows that differ from the selected profile."""
	profile = rows_dict(get_profile_rows(getattr(configuration, "field_profile", None)))
	if not profile:
		return configuration
	configuration.set(
		"fields",
		[
			row
			for row in configuration.fields
			if rows_dict([row])[row.fieldname] != profile.get(row.fieldname)
		],
	)
	return configuration


def effective_rows(configuration):
	"""Rows for the project field grid: every master field with its effective rule."""
	template = get_template(configuration.form_template)
	rules = configuration_dict(configuration)
	rows = []
	for source in template_rows(template):
		rule = rules.get(source.fieldname) or {
			"enabled": True,
			"mandatory": bool(cint(source.mandatory)),
			"read_only": bool(cint(source.read_only)),
			"label_override": "",
		}
		rows.append(
			{
				"fieldname": source.fieldname,
				"field_label": source.label,
				"enabled": int(rule["enabled"]),
				"mandatory": int(rule["mandatory"]),
				"read_only": int(rule["read_only"]),
				"label_override": rule["label_override"],
			}
		)
	return rows


def get_reference(template, document):
	fieldname = getattr(template, "reference_fieldname", None)
	if not fieldname:
		return None, None
	reference_name = document.get(fieldname)
	if not reference_name:
		return None, None
	return template.reference_doctype, reference_name


def get_document_configuration(template, document, use_snapshot=True):
	if not template.enable_project_configuration:
		return None, None
	if use_snapshot and not document.is_new() and document.get("ai_form_configuration_snapshot"):
		try:
			return json.loads(document.ai_form_configuration_snapshot), document.get(
				"ai_form_project_configuration"
			)
		except (TypeError, ValueError):
			pass
	reference_doctype, reference_name = get_reference(template, document)
	configuration = find_configuration(reference_doctype, reference_name, template.name)
	if not configuration:
		return None, None
	return configuration_dict(configuration), configuration.name


def snapshot_document_configuration(document):
	"""Freeze the chosen configuration on first successful save."""
	template_name = document.get("ai_form_template")
	if not template_name or document.get("ai_form_configuration_snapshot"):
		return
	template = get_template(template_name)
	if not template.enable_project_configuration:
		return
	configuration, configuration_name = get_document_configuration(template, document, use_snapshot=False)
	if configuration is None:
		return
	document.ai_form_project_configuration = configuration_name
	document.ai_form_configuration_snapshot = json.dumps(configuration, sort_keys=True)


def validate_project_form(document, method=None):
	"""Global document hook: authoritative project-aware form validation."""
	template_name = document.get("ai_form_template")
	if not template_name or not frappe.db.exists("AI Form Template", template_name):
		return
	template = get_template(template_name)
	if not template.enable_project_configuration:
		return
	configuration, configuration_name = get_document_configuration(template, document)
	if configuration is None:
		frappe.throw(_("This form is not enabled for the selected project."))
	if not configuration_name and document.is_new():
		frappe.throw(_("This form is not enabled for the selected project."))
	if configuration_name and not frappe.db.get_value(
		"AI Project Form Configuration", configuration_name, "enabled"
	):
		frappe.throw(_("This form is not enabled for the selected project."))
	validate_reference_access(template, document)
	validate_project_mandatory(document, configuration)
	validate_project_read_only(document, configuration)
	snapshot_document_configuration(document)


def validate_reference_access(template, document):
	"""A record may only be filed against a context record the user can read."""
	reference_doctype, reference_name = get_reference(template, document)
	if (
		reference_doctype
		and reference_name
		and not frappe.has_permission(reference_doctype, "read", reference_name)
	):
		frappe.throw(
			_("You do not have access to {0} {1}.").format(_(reference_doctype), reference_name),
			frappe.PermissionError,
		)


def validate_project_mandatory(document, configuration):
	"""Replace Frappe's mandatory check with a project-aware one.

	Frappe's own check still runs for every field the project does not
	configure; for configured fields the project rule decides. A field hidden
	for this project is therefore never mandatory here, however another
	project or the master defines it. Rows of a hidden table are skipped too.
	"""
	flags = getattr(document, "flags", None)
	if flags is not None and flags.ignore_mandatory:
		return
	hidden = {fieldname for fieldname, rules in configuration.items() if not rules["enabled"]}
	missing = []
	if hasattr(document, "_get_missing_mandatory_fields"):
		missing.extend(
			(fieldname, message)
			for fieldname, message in document._get_missing_mandatory_fields()
			if fieldname not in configuration
		)
		for child in document.get_all_children():
			if child.parentfield in hidden:
				continue
			missing.extend(child._get_missing_mandatory_fields())
	for fieldname, rules in configuration.items():
		if rules["enabled"] and rules["mandatory"] and document.get(fieldname) in (None, "", []):
			label = rules.get("label_override") or document.meta.get_label(fieldname) or fieldname
			missing.append((fieldname, _("{0} is mandatory for this project.").format(label)))
	if missing:
		frappe.throw("<br>".join(message for _fieldname, message in missing), frappe.MandatoryError)
	if flags is not None:
		flags.ignore_mandatory = True


def validate_project_read_only(document, configuration):
	"""Project read-only/hidden fields cannot be changed through the API.

	Values are never cleared. Fields the master already makes read-only or
	fetches from another record are left to Frappe.
	"""
	if document.is_new() or not hasattr(document, "has_value_changed"):
		return
	for fieldname, rules in configuration.items():
		if not (rules["read_only"] or not rules["enabled"]):
			continue
		df = document.meta.get_field(fieldname)
		if not df or df.read_only or df.fetch_from or df.fieldtype in ("Table", "Table MultiSelect"):
			continue
		if document.has_value_changed(fieldname):
			label = rules.get("label_override") or df.label or fieldname
			frappe.throw(_("{0} cannot be changed on this project.").format(label), frappe.PermissionError)


RUNTIME_FIELDNAMES = ("ai_form_template", "ai_form_project_configuration", "ai_form_configuration_snapshot")


def ensure_runtime_fields(doctype_name):
	"""Migration-safe metadata installation for generated DocTypes.

	Custom DocTypes are extended in place. A standard DocType (an existing
	DocType registered in the library) gets Custom Fields instead, so its
	source definition is never touched.
	"""
	if not frappe.db.get_value("DocType", doctype_name, "custom"):
		return ensure_runtime_custom_fields(doctype_name)
	doc = frappe.get_doc("DocType", doctype_name)
	existing = {field.fieldname for field in doc.fields}
	missing = [
		{
			"label": "AI Form Template",
			"fieldname": "ai_form_template",
			"fieldtype": "Link",
			"options": "AI Form Template",
			"hidden": 1,
			"read_only": 1,
		},
		{
			"label": "AI Project Form Configuration",
			"fieldname": "ai_form_project_configuration",
			"fieldtype": "Link",
			"options": "AI Project Form Configuration",
			"hidden": 1,
			"read_only": 1,
		},
		{
			"label": "AI Form Configuration Snapshot",
			"fieldname": "ai_form_configuration_snapshot",
			"fieldtype": "Code",
			"options": "JSON",
			"hidden": 1,
			"read_only": 1,
		},
	]
	for field in missing:
		if field["fieldname"] not in existing:
			doc.append("fields", field)
	if any(field["fieldname"] not in existing for field in missing):
		doc.save(ignore_permissions=True)
		frappe.clear_cache(doctype=doctype_name)
	return doctype_name


def ensure_runtime_custom_fields(doctype_name):
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			doctype_name: [
				{
					"label": "AI Form Template",
					"fieldname": "ai_form_template",
					"fieldtype": "Link",
					"options": "AI Form Template",
					"hidden": 1,
					"read_only": 1,
					"insert_after": None,
				},
				{
					"label": "AI Project Form Configuration",
					"fieldname": "ai_form_project_configuration",
					"fieldtype": "Link",
					"options": "AI Project Form Configuration",
					"hidden": 1,
					"read_only": 1,
					"insert_after": "ai_form_template",
				},
				{
					"label": "AI Form Configuration Snapshot",
					"fieldname": "ai_form_configuration_snapshot",
					"fieldtype": "Code",
					"options": "JSON",
					"hidden": 1,
					"read_only": 1,
					"insert_after": "ai_form_project_configuration",
				},
			]
		},
		ignore_validate=True,
		update=False,
	)
	return doctype_name


def set_template_default(doctype_name, template_name, replace=False):
	"""New records of the DocType are stamped with this template (revision)."""
	# frappe.new_doc keeps a per-request template of defaults; drop it so a
	# record created later in this request gets the new revision.
	getattr(frappe.local, "new_doc_templates", {}).pop(doctype_name, None)
	custom_field = frappe.db.get_value("Custom Field", {"dt": doctype_name, "fieldname": "ai_form_template"})
	if custom_field:
		if replace or not frappe.db.get_value("Custom Field", custom_field, "default"):
			frappe.db.set_value("Custom Field", custom_field, "default", template_name)
			frappe.clear_cache(doctype=doctype_name)
		return
	doctype = frappe.get_doc("DocType", doctype_name)
	for field in doctype.fields:
		if (
			field.fieldname == "ai_form_template"
			and (replace or not field.default)
			and field.default != template_name
		):
			field.default = template_name
			doctype.save(ignore_permissions=True)
			frappe.clear_cache(doctype=doctype.name)


def install_runtime_for_template(template):
	"""Upgrade an existing generated DocType without recreating or deleting it.

	Master `reqd` flags are left alone: validate_project_mandatory decides,
	per project, which of them apply.
	"""
	if not template.generated_doctype or not frappe.db.exists("DocType", template.generated_doctype):
		return
	ensure_runtime_fields(template.generated_doctype)
	set_template_default(template.generated_doctype, template.name)
	from ai_form_builder.services.doctype_generator import DocTypeGenerator

	DocTypeGenerator()._ensure_client_script(template.generated_doctype)
