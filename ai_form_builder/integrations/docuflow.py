"""Optional Docuflow adapter.

Everything Docuflow-specific lives here; the core form library never imports
Docuflow and keeps working when it is not installed. Docuflow is only read
through its DocTypes and public helpers. Nothing here writes to Docuflow
records or changes its behaviour.

What Docuflow offers (verified against the docuflow app, read only):

- Projects are the DocType ``DCMS Project``; the record name is the project
  code, the title is ``project_name``. Docuflow records link to it through a
  field named ``project``.
- The SPA's active project is stored as a user default and exposed by
  ``docuflow.api.active_project.get_active_project_default(user)``.
- Its work areas (doc-control, quality, hse, ...) and register lists are
  fixed in code (``frontend/src/data/navigation.js``, ``quality/*_registry.py``),
  with no hook or registry DocType that another app can extend. Dynamic forms are
  therefore offered next to them, from AI Form Builder (Desk links carrying the
  project), not injected into Docuflow's sidebar.
- Project membership is enforced by Docuflow's own ``has_permission`` on
  ``DCMS Project``; ``frappe.has_permission`` honours it, so no Docuflow
  permission code is called or weakened here.
"""

import frappe

APP = "docuflow"
PROJECT_DOCTYPE = "DCMS Project"
PROJECT_FIELDNAME = "project"


def is_installed():
	try:
		return APP in frappe.get_installed_apps()
	except Exception:
		return False


def get_project_doctype():
	"""Docuflow's project DocType, or None when Docuflow is absent."""
	if is_installed() and frappe.db.exists("DocType", PROJECT_DOCTYPE):
		return PROJECT_DOCTYPE
	return None


def get_default_context():
	"""(reference_doctype, reference_fieldname) new forms should link to."""
	doctype = get_project_doctype()
	return (doctype, PROJECT_FIELDNAME) if doctype else (None, None)


def get_active_project(user=None):
	"""The project currently selected in Docuflow's top bar, if any."""
	if not get_project_doctype():
		return None
	try:
		from docuflow.api.active_project import get_active_project_default
	except ImportError:
		return None
	try:
		return get_active_project_default(user)
	except Exception:
		return None


def get_project_title(project):
	doctype = get_project_doctype()
	if not doctype or not project:
		return None
	return frappe.db.get_value(doctype, project, "project_name")


def get_areas():
	"""Library areas the administrator has tied to Docuflow (external_app = docuflow)."""
	return frappe.get_all(
		"AI Form Area",
		filters={"enabled": 1, "external_app": APP},
		fields=["name", "area_code", "external_reference"],
		order_by="sequence asc, name asc",
	)


@frappe.whitelist()
def get_context():
	"""What the Desk pages need to pre-select the Docuflow project."""
	doctype = get_project_doctype()
	project = get_active_project() if doctype else None
	return {
		"installed": bool(doctype),
		"reference_doctype": doctype,
		"reference_fieldname": PROJECT_FIELDNAME if doctype else None,
		"active_project": project,
		"project_title": get_project_title(project),
	}


@frappe.whitelist()
def get_project_forms(project=None, area=None):
	"""Dynamic forms enabled for a Docuflow project, grouped area → group.

	Returns an empty list when Docuflow is not installed.
	"""
	doctype = get_project_doctype()
	if not doctype:
		return []
	project = project or get_active_project()
	if not project:
		return []
	from ai_form_builder.services.form_registry import get_enabled_forms

	return get_enabled_forms(doctype, project, area=area)
