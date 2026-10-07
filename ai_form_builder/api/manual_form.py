"""Manual no-code form creation using Frappe's standard Custom DocType."""

import frappe
from frappe import _

from ai_form_builder.services.project_form_service import install_runtime_for_template
from ai_form_builder.utils.validation import sanitize_fieldname

TEMPLATE_DOCTYPE = "AI Form Template"
SYSTEM_FIELDS = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"ai_form_template",
	"ai_form_project_configuration",
	"ai_form_configuration_snapshot",
}
LAYOUT_FIELDS = {"Section Break", "Column Break", "Tab Break", "HTML", "Fold", "Heading"}


def _manager():
	frappe.only_for(["AI Form Builder Manager", "System Manager"])


@frappe.whitelist()
def create_manual_form(
	template_title,
	template_code,
	form_group=None,
	enable_project_configuration=0,
	reference_doctype=None,
	reference_fieldname=None,
):
	"""Create a blank Custom DocType and register it in the existing template flow.

	Fields are deliberately added through Frappe's DocType editor afterwards. The
	new template can be synced at any time; no parallel manual-form schema is
	maintained here.
	"""
	_manager()
	if frappe.db.exists(TEMPLATE_DOCTYPE, template_code):
		frappe.throw(_("Template code {0} already exists.").format(template_code))
	doctype_name = template_title.strip()
	if not doctype_name:
		frappe.throw(_("Form title is required."))
	if frappe.db.exists("DocType", doctype_name):
		frappe.throw(_("DocType {0} already exists.").format(doctype_name))
	if enable_project_configuration and not reference_doctype:
		frappe.throw(_("Reference DocType is required when Project Configuration is enabled."))

	doctype = frappe.get_doc(
		{
			"doctype": "DocType",
			"name": doctype_name,
			"module": "AI Form Builder",
			"custom": 1,
			"is_submittable": 0,
			"permissions": [
				{
					"role": "AI Form Builder User",
					"read": 1,
					"write": 1,
					"create": 1,
					"delete": 1,
					"print": 1,
					"email": 1,
				}
			],
		}
	).insert()
	template = frappe.get_doc(
		{
			"doctype": TEMPLATE_DOCTYPE,
			"template_title": template_title,
			"template_code": template_code,
			"source_type": "Manual",
			"status": "Generated",
			"form_group": form_group,
			"generated_doctype": doctype.name,
			"target_doctype": doctype.name,
			"enable_project_configuration": int(enable_project_configuration or 0),
			"reference_doctype": reference_doctype,
			"reference_fieldname": reference_fieldname,
		}
	).insert()
	install_runtime_for_template(template)
	return {"template": template.name, "doctype": doctype.name}


@frappe.whitelist()
def sync_manual_fields(template_name):
	"""Import new Frappe-configured fields without removing mapping metadata."""
	_manager()
	template = frappe.get_doc(TEMPLATE_DOCTYPE, template_name)
	template.check_permission("write")
	if template.source_type != "Manual":
		frappe.throw(_("Only manual templates can be synced this way."))
	meta = frappe.get_meta(template.generated_doctype)
	existing = {row.fieldname: row for row in template.fields}
	for field in meta.fields:
		if field.fieldname in SYSTEM_FIELDS or field.fieldtype in LAYOUT_FIELDS:
			continue
		row = existing.get(field.fieldname)
		if not row:
			row = template.append("fields", {"fieldname": sanitize_fieldname(field.fieldname)})
		row.label = field.label or field.fieldname
		row.suggested_fieldtype = field.fieldtype
		row.final_fieldtype = field.fieldtype
		row.options = field.options or ""
		row.mandatory = field.reqd
		row.read_only = field.read_only
		row.hidden = field.hidden
		row.link_target = field.options if field.fieldtype == "Link" else ""
		# Manual forms have no PDF coordinates. These inert values satisfy the
		# shared mapping validator and are never rendered because printable=0.
		row.page_number = row.page_number or 1
		row.width = row.width or 1
		row.height = row.height or 1
		row.is_printable = 0
	template.save()
	return {"template": template.name, "fields": len(template.fields)}
