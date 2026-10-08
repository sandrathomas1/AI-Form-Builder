"""Manual no-code form creation using Frappe's standard Custom DocType."""

import frappe
from frappe import _
from frappe.utils import cint

from ai_form_builder.services import form_registry
from ai_form_builder.services.doctype_generator import DocTypeGenerator
from ai_form_builder.services.project_form_service import install_runtime_for_template
from ai_form_builder.utils.validation import sanitize_fieldname

TEMPLATE_DOCTYPE = "AI Form Template"


def _manager():
	frappe.only_for(["AI Form Builder Manager", "System Manager"])


DOCTYPE_PERMISSIONS = [
	{
		"role": "AI Form Builder Manager",
		"read": 1,
		"write": 1,
		"create": 1,
		"delete": 1,
		"print": 1,
		"email": 1,
		"report": 1,
		"export": 1,
		"share": 1,
	},
	{"role": "AI Form Builder User", "read": 1, "write": 1, "create": 1, "delete": 1, "print": 1, "email": 1},
]


@frappe.whitelist()
def create_manual_form(
	template_title,
	template_code,
	form_group=None,
	enable_project_configuration=0,
	reference_doctype=None,
	reference_fieldname=None,
	target_area=None,
	description=None,
	is_submittable=0,
	allow_attachments=0,
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
	enable_project_configuration = cint(enable_project_configuration)
	if enable_project_configuration and not reference_doctype:
		reference_doctype, default_fieldname = form_registry.default_reference()
		reference_fieldname = reference_fieldname or default_fieldname
	if enable_project_configuration and not reference_doctype:
		frappe.throw(_("Reference DocType is required when Project Configuration is enabled."))
	if enable_project_configuration and not reference_fieldname:
		reference_fieldname = sanitize_fieldname(reference_doctype)

	# Layout the admin starts from in Form Builder: the project link first,
	# then the optional attachment; the hidden runtime fields sit on their own
	# trailing "System" tab so they are out of the way while designing.
	fields = []
	if enable_project_configuration:
		fields.append(form_registry.reference_field(reference_doctype, reference_fieldname))
	if cint(allow_attachments):
		fields.append({"label": _("Attachment"), "fieldname": "attachment", "fieldtype": "Attach"})
	fields.append({"label": _("System"), "fieldname": "ai_form_system_tab", "fieldtype": "Tab Break"})
	fields.extend(DocTypeGenerator()._runtime_fields(template_code))
	doctype = frappe.get_doc(
		{
			"doctype": "DocType",
			"name": doctype_name,
			"module": "AI Form Builder",
			"custom": 1,
			"is_submittable": cint(is_submittable),
			"description": description,
			"track_changes": 1,
			"fields": fields,
			"permissions": DOCTYPE_PERMISSIONS,
		}
	).insert()
	if enable_project_configuration:
		form_registry.ensure_reference_field(doctype.name, reference_doctype, reference_fieldname)
	template = frappe.get_doc(
		{
			"doctype": TEMPLATE_DOCTYPE,
			"template_title": template_title,
			"template_code": template_code,
			"source_type": "Manual",
			"status": "Generated",
			"target_area": target_area,
			"form_group": form_group,
			"description": description,
			"generated_doctype": doctype.name,
			"target_doctype": doctype.name,
			"enable_project_configuration": enable_project_configuration,
			"reference_doctype": reference_doctype,
			"reference_fieldname": reference_fieldname,
		}
	).insert()
	install_runtime_for_template(template)
	form_registry.sync_fields(template)
	return {"template": template.name, "doctype": doctype.name, **form_registry.edit_route(doctype.name)}


@frappe.whitelist()
def sync_manual_fields(template_name):
	"""Import Frappe-configured fields without removing mapping metadata.

	Kept for existing callers; works for every source type.
	"""
	_manager()
	template = frappe.get_doc(TEMPLATE_DOCTYPE, template_name)
	template.check_permission("write")
	summary = form_registry.sync_fields(template)
	return {"template": template.name, "fields": len(template.fields), **summary}
