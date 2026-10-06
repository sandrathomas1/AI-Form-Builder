import frappe


@frappe.whitelist()
def get_context():
	frappe.only_for(["AI Form Builder Manager", "System Manager"])
	return {}
