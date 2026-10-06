import frappe


@frappe.whitelist()
def get_context(template_name):
	frappe.only_for(["AI Form Builder Manager", "System Manager"])
	template = frappe.get_doc("AI Form Template", template_name)
	template.check_permission("read")
	return {
		"name": template.name,
		"title": template.template_title,
		"source_pdf": template.source_pdf,
		"pages": template.number_of_pages,
		"fields": [row.as_dict() for row in template.fields],
		"sections": [row.as_dict() for row in template.sections],
	}
