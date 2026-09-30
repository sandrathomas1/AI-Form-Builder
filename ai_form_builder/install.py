import frappe


def after_install():
	for role in ("AI Form Builder Manager", "AI Form Builder User"):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
