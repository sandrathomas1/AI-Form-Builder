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
		and row.final_fieldtype
		and row.final_fieldtype not in LAYOUT_FIELD_TYPES
		and row.fieldname not in SYSTEM_FIELDS
	]


def populate_fields(configuration, preserve=True):
	"""Add missing master fields without changing existing project choices."""
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


def configuration_dict(configuration):
	return {
		row.fieldname: {
			"enabled": bool(row.enabled),
			"mandatory": bool(row.mandatory),
			"read_only": bool(row.read_only),
			"label_override": row.label_override or "",
		}
		for row in configuration.fields
	}


def get_reference(template, document):
	fieldname = template.reference_fieldname
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
			return json.loads(document.ai_form_configuration_snapshot), document.get("ai_form_project_configuration")
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
	if configuration_name and not frappe.db.get_value("AI Project Form Configuration", configuration_name, "enabled"):
		frappe.throw(_("This form is not enabled for the selected project."))
	for fieldname, rules in configuration.items():
		if rules["enabled"] and rules["mandatory"] and document.get(fieldname) in (None, ""):
			label = document.meta.get_label(fieldname) or fieldname
			frappe.throw(_("{0} is mandatory for this project.").format(label))
	snapshot_document_configuration(document)


def ensure_runtime_fields(doctype_name):
	"""Migration-safe metadata installation for generated DocTypes."""
	doc = frappe.get_doc("DocType", doctype_name)
	existing = {field.fieldname for field in doc.fields}
	missing = [
		{"label": "AI Form Template", "fieldname": "ai_form_template", "fieldtype": "Link", "options": "AI Form Template", "hidden": 1, "read_only": 1},
		{"label": "AI Project Form Configuration", "fieldname": "ai_form_project_configuration", "fieldtype": "Link", "options": "AI Project Form Configuration", "hidden": 1, "read_only": 1},
		{"label": "AI Form Configuration Snapshot", "fieldname": "ai_form_configuration_snapshot", "fieldtype": "Code", "options": "JSON", "hidden": 1, "read_only": 1},
	]
	for field in missing:
		if field["fieldname"] not in existing:
			doc.append("fields", field)
	if any(field["fieldname"] not in existing for field in missing):
		doc.save(ignore_permissions=True)
		frappe.clear_cache(doctype=doctype_name)
	return doctype_name


def install_runtime_for_template(template):
	"""Upgrade an existing generated DocType without recreating or deleting it."""
	if not template.generated_doctype or not frappe.db.exists("DocType", template.generated_doctype):
		return
	ensure_runtime_fields(template.generated_doctype)
	doctype = frappe.get_doc("DocType", template.generated_doctype)
	changed = False
	for field in doctype.fields:
		if field.fieldname == "ai_form_template" and not field.default:
			field.default = template.name
			changed = True
		if template.enable_project_configuration and field.fieldname in {row.fieldname for row in template_rows(template)} and field.reqd:
			field.reqd = 0
			changed = True
	if changed:
		doctype.save(ignore_permissions=True)
		frappe.clear_cache(doctype=doctype.name)
	from ai_form_builder.services.doctype_generator import DocTypeGenerator

	DocTypeGenerator()._ensure_client_script(doctype.name)
