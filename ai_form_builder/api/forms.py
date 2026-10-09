"""Form Library actions shared by all three ways of creating a form."""

import frappe
from frappe import _

from ai_form_builder.integrations import docuflow
from ai_form_builder.services import form_registry

TEMPLATE = "AI Form Template"


def _manager():
	frappe.only_for(["AI Form Builder Manager", "System Manager"])


def _template(template_name, ptype="write"):
	template = frappe.get_doc(TEMPLATE, template_name)
	template.check_permission(ptype)
	return template


@frappe.whitelist()
def get_new_form_defaults():
	"""Defaults for the New Form wizard."""
	_manager()
	reference_doctype, reference_fieldname = form_registry.default_reference()
	return {
		"reference_doctype": reference_doctype,
		"reference_fieldname": reference_fieldname,
		"docuflow_installed": docuflow.is_installed(),
	}


@frappe.whitelist()
def register_existing_doctype(
	doctype,
	template_title,
	template_code,
	target_area=None,
	form_group=None,
	description=None,
	enable_project_configuration=0,
	reference_doctype=None,
	reference_fieldname=None,
):
	_manager()
	frappe.has_permission(TEMPLATE, "create", throw=True)
	template = form_registry.register_existing_doctype(
		doctype,
		template_title,
		template_code,
		target_area=target_area,
		form_group=form_group,
		description=description,
		enable_project_configuration=enable_project_configuration,
		reference_doctype=reference_doctype,
		reference_fieldname=reference_fieldname,
	)
	return {"template": template.name, "doctype": doctype}


@frappe.whitelist()
def sync_fields(template_name):
	_manager()
	return form_registry.sync_fields(_template(template_name))


@frappe.whitelist()
def publish(template_name):
	_manager()
	return form_registry.publish(_template(template_name)).name


@frappe.whitelist()
def create_revision(template_name):
	_manager()
	frappe.has_permission(TEMPLATE, "create", throw=True)
	return form_registry.create_revision(_template(template_name, "read")).name


@frappe.whitelist()
def get_edit_route(template_name):
	"""Where to edit the form's fields with Frappe's own builder."""
	_manager()
	template = _template(template_name, "read")
	if not template.generated_doctype:
		frappe.throw(_("This form has no DocType yet."))
	return form_registry.edit_route(template.generated_doctype)


@frappe.whitelist()
def get_workflow_route(template_name):
	"""Open the standard Frappe Workflow for the form's DocType (existing or new)."""
	_manager()
	template = _template(template_name, "read")
	if not template.generated_doctype:
		frappe.throw(_("This form has no DocType yet."))
	workflow = frappe.db.get_value("Workflow", {"document_type": template.generated_doctype})
	if workflow:
		return {"route": ["Form", "Workflow", workflow]}
	return {
		"route": ["Form", "Workflow", "new"],
		"route_options": {
			"document_type": template.generated_doctype,
			"workflow_name": template.template_title,
		},
	}


@frappe.whitelist()
def get_enabled_forms(reference_doctype, reference_name, area=None):
	"""Forms the current user can open for a context record (e.g. a project)."""
	return form_registry.get_enabled_forms(reference_doctype, reference_name, area=area)
