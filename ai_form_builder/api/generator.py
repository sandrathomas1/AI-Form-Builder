import frappe
from frappe import _

from ai_form_builder.services.doctype_generator import DocTypeGenerator
from ai_form_builder.services.project_form_service import install_runtime_for_template


@frappe.whitelist()
def generate_doctype(template_name, doctype_name=None):
	frappe.only_for(["AI Form Builder Manager", "System Manager"])
	template = frappe.get_doc("AI Form Template", template_name)
	template.check_permission("write")
	if (template.storage_mode or "Spec") == "Spec":
		frappe.throw(
			_("{0} is a spec form: it is published as data and never gets a DocType.").format(
				template.template_title
			)
		)
	if template.status != "Approved":
		frappe.throw(_("Approve the mapping before generating a DocType."))
	name = doctype_name or template.target_doctype or template.template_title
	if template.target_doctype:
		if not frappe.db.exists("DocType", template.target_doctype):
			frappe.throw(_("Selected DocType does not exist."))
		generated = template.target_doctype
	else:
		generated = DocTypeGenerator().generate(template, name)
	template.db_set("generated_doctype", generated)
	# Existing target DocTypes need the same harmless metadata/runtime upgrade.
	template.generated_doctype = generated
	install_runtime_for_template(template)
	template.db_set("status", "Generated")
	return generated
