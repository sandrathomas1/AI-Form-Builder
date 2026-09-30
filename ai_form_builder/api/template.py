import frappe
from frappe import _

from ai_form_builder.services.template_service import analyze_template as run_analysis


def _manager():
	frappe.only_for(["AI Form Builder Manager", "System Manager"])


@frappe.whitelist()
def analyze_template(template_name):
	_manager()
	template = frappe.get_doc("AI Form Template", template_name)
	template.check_permission("write")
	if template.status == "Analyzing":
		frappe.throw(_("Analysis is already running."))
	settings = frappe.get_single("AI Form Builder Settings")
	template.db_set("status", "Analyzing")
	if settings.enable_background_processing:
		frappe.enqueue(
			"ai_form_builder.services.template_service.analyze_template",
			queue="long",
			template_name=template.name,
		)
		return {"queued": True}
	run_analysis(template.name)
	return {"queued": False}


@frappe.whitelist()
def get_analysis(template_name):
	template = frappe.get_doc("AI Form Template", template_name)
	template.check_permission("read")
	return {"status": template.status, "analysis": template.analysis_json, "error": template.analysis_error}


@frappe.whitelist()
def approve_mapping(template_name):
	_manager()
	template = frappe.get_doc("AI Form Template", template_name)
	template.check_permission("write")
	if template.status not in {"Review Required", "Approved"}:
		frappe.throw(_("Only analyzed templates can be approved."))
	template.status = "Approved"
	template.save()
	return template.name


@frappe.whitelist()
def get_template_fields(template_name):
	template = frappe.get_doc("AI Form Template", template_name)
	template.check_permission("read")
	return [
		{
			"name": row.name,
			"label": row.label,
			"fieldname": row.fieldname,
			"type": row.final_fieldtype,
			"page": row.page_number,
			"x": row.x,
			"y": row.y,
			"width": row.width,
			"height": row.height,
		}
		for row in template.fields
		if not row.ignore_field
	]
