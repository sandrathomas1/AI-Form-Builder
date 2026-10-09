"""Build and review spec forms (forms that are data, not DocTypes)."""

import frappe
from frappe import _

from ai_form_builder.services import spec_service

TEMPLATE = "AI Form Template"


def _manager():
	frappe.only_for(["AI Form Builder Manager", "System Manager"])


def _template(template_name, ptype="write"):
	template = frappe.get_doc(TEMPLATE, template_name)
	template.check_permission(ptype)
	if not spec_service.is_spec_form(template):
		frappe.throw(
			_("{0} is a DocType form; edit it with Frappe's Form Builder.").format(template.template_title)
		)
	return template


@frappe.whitelist()
def get_review(template_name):
	_manager()
	return spec_service.review_payload(_template(template_name, "read"))


@frappe.whitelist()
def save_spec(template_name, spec):
	_manager()
	template = spec_service.save_spec(_template(template_name), frappe.parse_json(spec))
	return spec_service.review_payload(template)


@frappe.whitelist()
def preview(template_name, spec=None):
	"""The sheet as it will print, filled with sample values."""
	_manager()
	template = _template(template_name, "read")
	from ai_form_builder.services import form_spec

	raw = frappe.parse_json(spec) if spec else spec_service.get_spec(template)
	return spec_service.preview_html(form_spec.normalise(raw))


@frappe.whitelist()
def publish(template_name):
	_manager()
	return spec_service.publish(_template(template_name)).name


@frappe.whitelist()
def reanalyze(template_name):
	_manager()
	template = _template(template_name)
	if template.status == "Analyzing":
		frappe.throw(_("Analysis is already running."))
	if template.status not in spec_service.EDITABLE_STATUSES:
		frappe.throw(_("Create a revision to read the sheet again."))
	return queue_analysis(template)


def queue_analysis(template):
	template.db_set("status", "Analyzing")
	settings = frappe.get_single("AI Form Builder Settings")
	if settings.enable_background_processing:
		frappe.enqueue(
			"ai_form_builder.services.spec_service.analyze",
			queue="long",
			timeout=1800,
			template_name=template.name,
			enqueue_after_commit=True,
		)
		return {"queued": True}
	spec_service.analyze(template.name)
	return {"queued": False}


@frappe.whitelist()
def export_spec(template_name):
	_manager()
	return spec_service.export_spec(_template(template_name, "read"))


@frappe.whitelist()
def import_spec(payload, target_area=None, form_group=None, enable_project_configuration=1):
	_manager()
	frappe.has_permission(TEMPLATE, "create", throw=True)
	template = spec_service.import_spec(
		frappe.parse_json(payload),
		target_area=target_area,
		form_group=form_group,
		enable_project_configuration=enable_project_configuration,
	)
	return template.name
