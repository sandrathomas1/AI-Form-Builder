import frappe
from frappe.sessions import get_csrf_token


def get_context(context):
	context.no_cache = 1
	context.title = "Review form fields"
	context.show_sidebar = False
	context.csrf_token = get_csrf_token()
