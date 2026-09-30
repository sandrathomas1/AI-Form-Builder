import frappe
from frappe import _

from ai_form_builder.services.doctype_generator import DocTypeGenerator


@frappe.whitelist()
def generate_doctype(template_name, doctype_name=None):
	frappe.only_for(["AI Form Builder Manager", "System Manager"])
	template = frappe.get_doc("AI Form Template", template_name)
	template.check_permission("write")
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
	template.db_set("status", "Generated")
	return generated
