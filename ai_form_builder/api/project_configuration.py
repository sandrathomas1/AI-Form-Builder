import frappe

from ai_form_builder.services.project_form_service import (
	get_document_configuration,
	get_reference,
	get_template,
)

from ai_form_builder.services.project_form_service import find_configuration, populate_fields


def _manager():
	frappe.only_for(["AI Form Builder Manager", "System Manager"])


@frappe.whitelist()
def get_project_forms(reference_doctype, reference_name):
	"""Templates grouped for the lightweight Project Form Setup page."""
	if not frappe.has_permission("AI Form Template", "read"):
		frappe.throw("Not permitted", frappe.PermissionError)
	templates = frappe.get_all(
		"AI Form Template",
		filters={"enable_project_configuration": 1, "reference_doctype": reference_doctype, "status": ["in", ["Approved", "Generated"]]},
		fields=["name", "template_title", "generated_doctype", "document_category", "form_group"],
		order_by="form_group, template_title",
	)
	for template in templates:
		configuration = find_configuration(reference_doctype, reference_name, template.name)
		template["configuration"] = configuration.name if configuration else None
		template["enabled"] = configuration.enabled if configuration else 0
		template["group"] = template.form_group or template.document_category or "Other"
	return templates


@frappe.whitelist()
def get_form_configuration(reference_doctype, reference_name, form_template):
	_manager()
	configuration = find_configuration(reference_doctype, reference_name, form_template)
	if not configuration:
		template = frappe.get_doc("AI Form Template", form_template)
		configuration = frappe.new_doc("AI Project Form Configuration")
		configuration.reference_doctype = reference_doctype
		configuration.reference_name = reference_name
		configuration.form_template = form_template
		configuration.generated_doctype = template.generated_doctype
		populate_fields(configuration)
	return configuration.as_dict()


@frappe.whitelist()
def save_form_configuration(configuration):
	_manager()
	payload = frappe.parse_json(configuration)
	if payload.get("name") and frappe.db.exists("AI Project Form Configuration", payload["name"]):
		doc = frappe.get_doc("AI Project Form Configuration", payload["name"])
		doc.update(payload)
	else:
		doc = frappe.get_doc({"doctype": "AI Project Form Configuration", **payload})
	doc.save()
	return doc.name


@frappe.whitelist()
def sync_configuration_fields(configuration_name):
	_manager()
	doc = frappe.get_doc("AI Project Form Configuration", configuration_name)
	doc.check_permission("write")
	populate_fields(doc)
	doc.save()
	return doc.as_dict()


@frappe.whitelist()
def get_runtime_configuration(form_template, document=None, document_name=None):
	"""Read-only runtime endpoint used by all generated form client scripts."""
	template = get_template(form_template)
	if not template.enable_project_configuration:
		return {"enabled": True, "fields": {}}
	if document_name:
		doc = frappe.get_doc(template.generated_doctype, document_name)
		doc.check_permission("read")
	else:
		payload = frappe.parse_json(document or "{}")
		doc = frappe.get_doc({"doctype": template.generated_doctype, **payload})
	reference_doctype, reference_name = get_reference(template, doc)
	if reference_doctype and reference_name and not frappe.has_permission(reference_doctype, "read", reference_name):
		frappe.throw("Not permitted", frappe.PermissionError)
	configuration, configuration_name = get_document_configuration(template, doc)
	if configuration is None:
		return {"enabled": False, "fields": {}}
	enabled = bool(frappe.db.get_value("AI Project Form Configuration", configuration_name, "enabled")) if configuration_name else True
	return {"enabled": enabled, "fields": configuration, "configuration": configuration_name}
