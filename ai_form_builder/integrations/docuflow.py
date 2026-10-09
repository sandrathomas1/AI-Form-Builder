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

import os
from urllib.parse import urlencode

import frappe

APP = "docuflow"
PROJECT_DOCTYPE = "DCMS Project"
PROJECT_FIELDNAME = "project"
# Docuflow's SPA shell (website_route_rules in docuflow/hooks.py).
SHELL_PATHS = ("/d", "/docuflow")
# Docuflow work-area key -> its SPA route (frontend/src/data/navigation.js
# WORKSPACES / WORKSPACE_PREFIXES). Only used to pre-fill the seeded areas;
# each AI Form Area holds its own routes from then on.
DEFAULT_AREA_ROUTES = {"quality": "/d/quality", "hse": "/d/hse"}
MANAGER_ROLES = ("AI Form Builder Manager", "System Manager")
BRIDGE_JS = "/assets/ai_form_builder/js/docuflow_form_library.js"
BRIDGE_CSS = "/assets/ai_form_builder/css/docuflow_form_library.css"


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
	title_field = frappe.get_meta(doctype).title_field  # project_name on DCMS Project
	return frappe.db.get_value(doctype, project, title_field) if title_field else None


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


def _asset_version():
	"""Changes whenever the panel script changes, so browsers never keep a stale copy."""
	path = frappe.get_app_path("ai_form_builder", "public", "js", "docuflow_form_library.js")
	return int(os.path.getmtime(path)) if os.path.exists(path) else 0


def _is_shell_path(path):
	return any(path == base or path.startswith(base + "/") for base in SHELL_PATHS)


def inject_bridge(response=None, request=None):
	"""after_request hook: add the Form Library panel to Docuflow's /d page.

	Docuflow's page is a standalone HTML shell without include hooks, so the
	panel's script and stylesheet are appended to the rendered HTML. Docuflow
	files are not touched; nothing happens for other pages, for guests, or
	when Docuflow is not installed.
	"""
	try:
		if not response or not request or request.method != "GET" or response.status_code != 200:
			return
		if not _is_shell_path(request.path) or response.mimetype != "text/html":
			return
		if response.direct_passthrough or response.headers.get("Content-Encoding"):
			return
		if frappe.session.user == "Guest" or not is_installed():
			return
		html = response.get_data(as_text=True)
		if BRIDGE_JS in html or "</body>" not in html:
			return
		version = _asset_version()
		tags = (
			f'<link rel="stylesheet" href="{BRIDGE_CSS}?v={version}">'
			f'<script defer src="{BRIDGE_JS}?v={version}"></script>'
		)
		response.set_data(html.replace("</body>", tags + "</body>", 1))
	except Exception:
		frappe.logger().error("AI Form Builder could not add its panel to Docuflow", exc_info=True)


def _area_rows():
	rows = frappe.get_all(
		"AI Form Area",
		filters={"enabled": 1, "show_in_external_app": 1, "external_app": APP},
		fields=["name", "area_code", "external_reference", "external_route_prefixes", "sequence"],
		order_by="sequence asc, name asc",
	)
	for row in rows:
		row.prefixes = [
			line.strip().rstrip("/")
			for line in (row.external_route_prefixes or "").splitlines()
			if line.strip()
		]
		del row["external_route_prefixes"]
	return rows


def _group_rows(areas):
	groups = frappe.get_all(
		"AI Form Group",
		filters={"enabled": 1, "target_area": ["in", areas or [""]]},
		fields=["name", "parent_group", "target_area", "sequence"],
		order_by="sequence asc, name asc",
	)
	by_name = {group.name: group for group in groups}
	for group in groups:
		path, current = [], group.name
		while current and current in by_name and current not in path:
			path.insert(0, current)
			current = by_name[current].parent_group
		group.label = " / ".join(path)
	return sorted(groups, key=lambda group: (group.target_area, group.label))


def can_manage():
	return bool(set(MANAGER_ROLES) & set(frappe.get_roles()))


@frappe.whitelist()
def get_bridge_config():
	"""Everything the /d panel needs once per page load."""
	doctype = get_project_doctype()
	if not doctype:
		return {"enabled": False}
	areas = _area_rows()
	project = get_active_project()
	return {
		"enabled": bool(areas),
		"areas": areas,
		"groups": _group_rows([area.name for area in areas]),
		"can_manage": can_manage(),
		"reference_doctype": doctype,
		"reference_fieldname": PROJECT_FIELDNAME,
		"active_project": project,
		"project_title": get_project_title(project),
	}


@frappe.whitelist()
def get_area_forms(area=None, project=None):
	"""Forms for one area (or every Docuflow area) and one project.

	Managers see every live form of the area with its project switch; other
	users see only the forms enabled for the project that they may open.
	"""
	from ai_form_builder.services import form_registry

	doctype = get_project_doctype()
	if not doctype:
		return {"forms": [], "project_title": None}
	areas = [row.name for row in _area_rows()]
	if area and area not in areas:
		frappe.throw(frappe._("Area {0} is not shown in Docuflow.").format(area))
	wanted = [area] if area else areas
	if project and not frappe.db.exists(doctype, project):
		project = None
	forms = []
	if can_manage():
		rows = (
			form_registry.get_setup_forms(doctype, project, include_drafts=True)
			if project
			else form_registry.library_rows(doctype, include_drafts=True)
		)
		for row in rows:
			if row.area not in wanted:
				continue
			enabled = bool(row.get("enabled"))
			if row.is_spec:
				live = row.status == "Published"
				urls = form_registry.spec_urls(row.name, project)
				forms.append(
					{
						"form_template": row.name,
						"title": row.template_title,
						"code": row.template_code,
						"status": row.status,
						"source_type": row.source_type,
						"doctype": None,
						"is_spec": True,
						"area": row.area,
						"group": row.group,
						"enabled": enabled,
						"review_url": urls["review_url"],
						"template_url": f"/app/ai-form-template/{row.name}",
						"configure_url": "/app/project-form-setup?"
						+ urlencode({"reference_doctype": doctype, "reference_name": project})
						if project and live
						else None,
						"new_url": urls["new_url"] if enabled and live and project else None,
						"list_url": urls["list_url"] if enabled and live and project else None,
					}
				)
				continue
			forms.append(
				{
					"form_template": row.name,
					"title": row.template_title,
					"code": row.template_code,
					"status": row.status,
					"source_type": row.source_type,
					"doctype": row.generated_doctype,
					"area": row.area,
					"group": row.group,
					"enabled": enabled,
					"edit_url": form_registry.edit_url(row.generated_doctype)
					if row.generated_doctype
					else None,
					"template_url": f"/app/ai-form-template/{row.name}",
					"configure_url": "/app/project-form-setup?"
					+ urlencode({"reference_doctype": doctype, "reference_name": project})
					if project
					else None,
					"new_url": form_registry.desk_url(
						row.generated_doctype, "new", {row.reference_fieldname: project}
					)
					if enabled and row.generated_doctype
					else None,
					"list_url": form_registry.desk_url(
						row.generated_doctype, "list", {row.reference_fieldname: project}
					)
					if enabled and row.generated_doctype
					else None,
				}
			)
	elif project:
		for row in form_registry.get_enabled_forms(doctype, project):
			if row["area"] not in wanted:
				continue
			row["enabled"] = True
			if row.get("is_spec"):
				urls = form_registry.spec_urls(row["form_template"], project)
				row["new_url"] = urls["new_url"] if row["can_create"] else None
				row["list_url"] = urls["list_url"]
				forms.append(row)
				continue
			values = {row["reference_fieldname"]: project}
			row["new_url"] = (
				form_registry.desk_url(row["doctype"], "new", values) if row["can_create"] else None
			)
			row["list_url"] = form_registry.desk_url(row["doctype"], "list", values)
			forms.append(row)
	return {"forms": forms, "project": project, "project_title": get_project_title(project)}
