import frappe

from ai_form_builder.services.project_form_service import install_runtime_for_template


def execute():
	"""Safely enhance existing generated DocTypes; intentionally repeatable."""
	for name in frappe.get_all("AI Form Template", filters={"generated_doctype": ["is", "set"]}, pluck="name"):
		install_runtime_for_template(frappe.get_doc("AI Form Template", name))
