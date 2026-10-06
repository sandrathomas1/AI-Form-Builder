import frappe


def get_context(context):
	context.no_cache = 1
	context.title = "AI Form Builder"
	context.show_sidebar = False
	context.logged_in = frappe.session.user != "Guest"
	context.can_manage = frappe.has_permission("AI Form Template", "create")
