import frappe
from frappe import _

from ai_form_builder.services.pdf_renderer import PDFRenderer


@frappe.whitelist()
def generate_pdf(template_name, doctype, document_name):
	template = frappe.get_doc("AI Form Template", template_name)
	template.check_permission("read")
	if template.generated_doctype != doctype and template.target_doctype != doctype:
		frappe.throw(_("Template is not mapped to this DocType."))
	document = frappe.get_doc(doctype, document_name)
	document.check_permission("read")
	content = PDFRenderer().render(template, document)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{template.template_code}-{document.name}.pdf",
			"content": content,
			"is_private": 1,
			"attached_to_doctype": doctype,
			"attached_to_name": document.name,
		}
	).insert(ignore_permissions=True)
	return file_doc.file_url
