"""Form Library: one registry for AI-PDF, manual no-code and existing-DocType forms.

Every form is an AI Form Template pointing at one Frappe DocType. Areas and
groups are configuration records (AI Form Area / AI Form Group); nothing here
knows what any particular area means.
"""

import frappe
from frappe import _
from frappe.utils import cint

from ai_form_builder.integrations import docuflow
from ai_form_builder.services.project_form_service import (
	RUNTIME_FIELDNAMES,
	install_runtime_for_template,
	set_template_default,
)
from ai_form_builder.utils.validation import FIELDNAME_RE, sanitize_fieldname

TEMPLATE = "AI Form Template"
# Statuses whose DocType may be offered to projects.
LIVE_STATUSES = ("Approved", "Generated", "Published")
# Statuses whose mapping is frozen; change them through a new revision.
LOCKED_STATUSES = ("Published", "Superseded")
LAYOUT_FIELD_TYPES = {
	"Section Break",
	"Column Break",
	"Tab Break",
	"HTML",
	"Button",
	"Image",
	"Fold",
	"Heading",
}
SYSTEM_FIELDNAMES = {
	*RUNTIME_FIELDNAMES,
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"amended_from",
}
LINK_LIKE = {"Link", "Table", "Table MultiSelect"}


def default_reference():
	"""Context record new project-configurable forms link to.

	Settings win; otherwise the Docuflow project when Docuflow is installed;
	otherwise none (the form behaves exactly as an unconfigured form).
	"""
	settings = frappe.get_single("AI Form Builder Settings")
	doctype = settings.get("default_reference_doctype")
	fieldname = settings.get("default_reference_fieldname") or "project"
	if not doctype:
		doctype, adapter_fieldname = docuflow.get_default_context()
		fieldname = adapter_fieldname or fieldname
	return doctype, (fieldname if doctype else None)


def edit_route(doctype):
	"""Native Frappe editor for the DocType: Form Builder for custom, Customize Form for standard."""
	if frappe.db.get_value("DocType", doctype, "custom"):
		return {"route": ["Form", "DocType", doctype]}
	return {"route": ["Form", "Customize Form"], "route_options": {"doc_type": doctype}}


def ensure_reference_field(doctype_name, reference_doctype, reference_fieldname):
	"""Add the context Link (e.g. project) to a custom DocType created by this app."""
	if not (reference_doctype and reference_fieldname):
		return
	doctype = frappe.get_doc("DocType", doctype_name)
	if any(field.fieldname == reference_fieldname for field in doctype.fields):
		return
	doctype.append(
		"fields",
		{
			"label": _(reference_doctype),
			"fieldname": reference_fieldname,
			"fieldtype": "Link",
			"options": reference_doctype,
			"in_list_view": 1,
			"in_standard_filter": 1,
		},
	)
	doctype.save()


def assert_unregistered(doctype):
	existing = frappe.db.get_value(
		TEMPLATE,
		{"generated_doctype": doctype, "status": ["not in", ["Superseded", "Disabled"]]},
	)
	if existing:
		frappe.throw(_("DocType {0} is already in the Form Library as {1}.").format(doctype, existing))


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
	"""Put an existing DocType in the library. No DocType is generated or recreated."""
	meta = frappe.get_meta(doctype)
	if meta.istable or meta.issingle or meta.is_virtual:
		frappe.throw(_("Child, single and virtual DocTypes cannot be registered as forms."))
	if frappe.db.exists(TEMPLATE, template_code):
		frappe.throw(_("Template code {0} already exists.").format(template_code))
	assert_unregistered(doctype)
	enable_project_configuration = cint(enable_project_configuration)
	if enable_project_configuration:
		if not reference_doctype:
			reference_doctype, default_fieldname = default_reference()
			reference_fieldname = reference_fieldname or default_fieldname
		if not reference_fieldname or not meta.get_field(reference_fieldname):
			frappe.throw(
				_(
					"{0} has no field {1} to hold the {2}. Add it with Frappe first, then register the form."
				).format(doctype, reference_fieldname or "?", reference_doctype or _("reference"))
			)
	template = frappe.get_doc(
		{
			"doctype": TEMPLATE,
			"template_title": template_title,
			"template_code": template_code,
			"source_type": "Existing DocType",
			"status": "Generated",
			"target_area": target_area,
			"form_group": form_group,
			"description": description,
			"generated_doctype": doctype,
			"target_doctype": doctype,
			"enable_project_configuration": enable_project_configuration,
			"reference_doctype": reference_doctype if enable_project_configuration else None,
			"reference_fieldname": reference_fieldname if enable_project_configuration else None,
		}
	).insert()
	if enable_project_configuration:
		# Only a project-configured form needs the hidden runtime fields.
		install_runtime_for_template(template)
	sync_fields(template)
	return template


def sync_fields(template):
	"""Bring the template's field registry up to date with the live DocType.

	New Frappe fields are added (unmapped, not printed). Labels/types/options of
	known fields follow the DocType. Fields deleted from the DocType are marked
	Orphaned, never removed, so historical mappings stay readable. PDF
	coordinates, print settings and project configurations are not touched.
	"""
	doctype = template.generated_doctype or template.target_doctype
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("This form has no DocType to sync from."))
	frappe.clear_cache(doctype=doctype)
	meta = frappe.get_meta(doctype)
	by_target = {(row.existing_field_mapping or row.fieldname): row for row in template.fields}
	seen = set()
	summary = {"added": [], "updated": [], "orphaned": [], "restored": []}
	for df in meta.fields:
		if df.fieldname in SYSTEM_FIELDNAMES or df.fieldtype in LAYOUT_FIELD_TYPES:
			continue
		row = by_target.get(df.fieldname)
		if not row:
			fieldname = df.fieldname if FIELDNAME_RE.match(df.fieldname) else sanitize_fieldname(df.fieldname)
			row = template.append(
				"fields",
				{
					"fieldname": fieldname,
					"existing_field_mapping": df.fieldname if fieldname != df.fieldname else None,
					"label": df.label or df.fieldname,
					"mandatory": df.reqd,
					"read_only": df.read_only,
					"hidden": df.hidden,
					"default_value": df.default if df.default and len(str(df.default)) <= 140 else None,
					# Not on the PDF until someone maps it in the mapping editor.
					"page_number": 1,
					"x": 0,
					"y": 0,
					"width": 1,
					"height": 1,
					"is_printable": 0,
				},
			)
			_copy_type(row, df)
			row.mapping_status = "Active"
			summary["added"].append(df.fieldname)
		else:
			before = (row.label, row.final_fieldtype, row.options, row.link_target)
			row.label = df.label or row.label or df.fieldname
			_copy_type(row, df)
			if before != (row.label, row.final_fieldtype, row.options, row.link_target):
				summary["updated"].append(df.fieldname)
			if row.get("mapping_status") == "Orphaned":
				summary["restored"].append(df.fieldname)
			row.mapping_status = "Active"
		seen.add(id(row))
	for row in template.fields:
		if id(row) in seen or row.ignore_field or row.get("mapping_status") == "Orphaned":
			continue
		row.mapping_status = "Orphaned"
		summary["orphaned"].append(row.existing_field_mapping or row.fieldname)
	template.save()
	return summary


def _copy_type(row, df):
	row.final_fieldtype = df.fieldtype
	# Select choices live in `options`; Link/Table targets in `link_target`.
	row.options = (df.options or "") if df.fieldtype == "Select" else ""
	row.link_target = df.options if df.fieldtype in LINK_LIKE and df.options else None
	row.is_signature = 1 if df.fieldtype == "Signature" else row.is_signature
	row.is_table = 1 if df.fieldtype in ("Table", "Table MultiSelect") else 0


def lineage(template):
	"""Earlier revisions of this form, newest first."""
	names, current = [], template.previous_revision
	while current and current not in names:
		names.append(current)
		current = frappe.db.get_value(TEMPLATE, current, "previous_revision")
	return names


def publish(template):
	"""Make this revision the live one for its DocType.

	Earlier revisions become Superseded (their records keep pointing at them,
	so their PDFs and snapshots are unchanged). Project configurations and
	profiles move to this revision so projects keep their settings.
	"""
	if not template.generated_doctype:
		frappe.throw(_("Create the form's DocType before publishing it."))
	if template.status in ("Superseded", "Disabled"):
		frappe.throw(_("A {0} revision cannot be published.").format(_(template.status)))
	older = lineage(template)
	for name in older:
		if frappe.db.get_value(TEMPLATE, name, "status") != "Superseded":
			frappe.db.set_value(TEMPLATE, name, "status", "Superseded")
	if older:
		for doctype in ("AI Project Form Configuration", "AI Form Field Profile"):
			for name in frappe.get_all(doctype, filters={"form_template": ["in", older]}, pluck="name"):
				frappe.db.set_value(doctype, name, "form_template", template.name, update_modified=False)
	install_runtime_for_template(template)
	set_template_default(template.generated_doctype, template.name, replace=True)
	template.status = "Published"
	template.save()
	return template


def next_version(version):
	version = (version or "0").strip()
	return str(cint(version) + 1) if version.isdigit() else f"{version}.1"


def create_revision(template):
	"""Controlled revision: a Draft copy of the template on the same DocType."""
	if template.status not in LOCKED_STATUSES and template.status != "Generated":
		frappe.throw(_("Only a generated or published form can be revised."))
	if frappe.db.exists(TEMPLATE, {"previous_revision": template.name}):
		frappe.throw(_("A newer revision of this form already exists."))
	revision = frappe.copy_doc(template)
	revision.previous_revision = template.name
	revision.template_version = next_version(template.template_version)
	revision.status = "Draft"
	revision.insert()
	return revision


def _area_of(template, groups):
	if template.target_area:
		return template.target_area
	group = groups.get(template.form_group)
	return group.target_area if group else None


def _group_path(group_name, groups):
	path = []
	while group_name and group_name in groups and group_name not in path:
		path.insert(0, group_name)
		group_name = groups[group_name].parent_group
	return path


def _library_rows(reference_doctype, area=None):
	templates = frappe.get_all(
		TEMPLATE,
		filters={
			"enable_project_configuration": 1,
			"reference_doctype": reference_doctype,
			"status": ["in", LIVE_STATUSES],
		},
		fields=[
			"name",
			"template_title",
			"template_code",
			"template_version",
			"generated_doctype",
			"document_category",
			"form_group",
			"target_area",
			"reference_fieldname",
			"source_pdf",
		],
	)
	groups = {
		group.name: group
		for group in frappe.get_all(
			"AI Form Group", fields=["name", "parent_group", "target_area", "sequence", "enabled"]
		)
	}
	areas = {
		row.name: row
		for row in frappe.get_all("AI Form Area", fields=["name", "sequence", "enabled", "external_app"])
	}
	rows = []
	for template in templates:
		template_area = _area_of(template, groups)
		if area and template_area != area:
			continue
		if template_area and template_area in areas and not areas[template_area].enabled:
			continue
		path = _group_path(template.form_group, groups)
		if any(not groups[name].enabled for name in path):
			continue
		template.area = template_area
		template.group_path = path
		template.group = " / ".join(path) or template.document_category or _("Other")
		template.sort_key = (
			areas[template_area].sequence if template_area in areas else 9999,
			template_area or "~",
			tuple((groups[name].sequence or 0, name) for name in path),
			template.template_title,
		)
		rows.append(template)
	rows.sort(key=lambda row: row.sort_key)
	for row in rows:
		del row["sort_key"]
	return rows


def get_setup_forms(reference_doctype, reference_name):
	"""Every project-configurable form with this project's enablement and profile."""
	rows = _library_rows(reference_doctype)
	configurations = {
		row.form_template: row
		for row in frappe.get_all(
			"AI Project Form Configuration",
			filters={"reference_doctype": reference_doctype, "reference_name": reference_name},
			fields=["name", "form_template", "enabled", "field_profile"],
		)
	}
	for row in rows:
		configuration = configurations.get(row.name)
		row.configuration = configuration.name if configuration else None
		row.enabled = configuration.enabled if configuration else 0
		row.field_profile = configuration.field_profile if configuration else None
	return rows


def get_enabled_forms(reference_doctype, reference_name, area=None):
	"""Forms a user may open for one context record (e.g. a project).

	Only forms enabled for that record whose DocType the user can read are
	returned; everything is checked with the user's own permissions.
	"""
	if not frappe.has_permission(reference_doctype, "read", reference_name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	enabled = set(
		frappe.get_all(
			"AI Project Form Configuration",
			filters={"reference_doctype": reference_doctype, "reference_name": reference_name, "enabled": 1},
			pluck="form_template",
		)
	)
	forms = []
	for row in _library_rows(reference_doctype, area=area):
		if row.name not in enabled or not row.generated_doctype:
			continue
		if not frappe.has_permission(row.generated_doctype, "read"):
			continue
		forms.append(
			{
				"form_template": row.name,
				"title": row.template_title,
				"code": row.template_code,
				"revision": row.template_version,
				"doctype": row.generated_doctype,
				"area": row.area,
				"group": row.group,
				"group_path": row.group_path,
				"reference_fieldname": row.reference_fieldname,
				"can_create": frappe.has_permission(row.generated_doctype, "create"),
				"has_pdf": bool(row.source_pdf),
			}
		)
	return forms
