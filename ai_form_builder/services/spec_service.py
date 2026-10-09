"""Spec forms: a form that is data, never a DocType.

The spec lives on its AI Form Template (``spec_json``). Publishing a spec form
writes nothing but that template's own row, so a form created on a production
site is a database record like any other: no DocType, no Client Script, no
migrate, nothing to push through git. Records of every spec form are rows of
the one ``AI Form Record`` DocType.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from ai_form_builder.services import form_spec, spec_renderer
from ai_form_builder.services.extract import ACCEPTED, draft, kind_of

TEMPLATE = "AI Form Template"
RECORD = "AI Form Record"
SPEC = "Spec"
EDITABLE_STATUSES = ("Uploaded", "Draft", "Analysis Failed", "Review Required", "Approved")
LIVE_STATUSES = ("Published",)
EXPORT_FORMAT = "ai-form-builder/spec@1"


def is_spec_form(template) -> bool:
	return (template.get("storage_mode") or SPEC) == SPEC and not template.get("generated_doctype")


def get_spec(template) -> dict:
	if not template.get("spec_json"):
		return {}
	try:
		return json.loads(template.spec_json)
	except (TypeError, ValueError):
		return {}


def set_spec(template, raw: dict, strict=True):
	"""Store a spec on the template and mirror its fields for project configuration.

	``strict`` refuses an unusable spec; an AI draft is stored leniently so the
	reviewer can fix it, and publishing then insists on a valid one.
	"""
	spec = form_spec.clean(raw) if strict else form_spec.normalise(raw)
	if not spec.get("title"):
		spec["title"] = template.template_title or ""
	template.spec_json = json.dumps(spec, indent=1, ensure_ascii=False)
	_mirror_fields(template, spec)
	return spec


def _mirror_fields(template, spec):
	"""The template's field rows follow the spec.

	Project configuration (show / hide / require a field per project) reads
	these rows, so it works for spec forms unchanged. They hold no layout: the
	spec's pages do.
	"""
	template.set("fields", [])
	template.set("sections", [])
	for sequence, section in enumerate(form_spec.form_sections(spec), 1):
		key = form_spec.scrub(section["label"]) or f"section_{sequence}"
		template.append(
			"sections",
			{"sequence": sequence, "section_label": section["label"], "section_key": key, "page_number": 1},
		)
	for field in spec.get("fields") or ():
		template.append(
			"fields",
			{
				"label": field.get("label") or field["name"],
				"fieldname": field["name"],
				"section_name": field.get("section") or form_spec.DEFAULT_SECTION,
				"suggested_fieldtype": form_spec.FRAPPE_TYPES[field["type"]],
				"final_fieldtype": form_spec.FRAPPE_TYPES[field["type"]],
				"options": "\n".join(field.get("options") or ()),
				"mandatory": 1 if field.get("mandatory") else 0,
				"is_signature": 1 if field["type"] == "Signature" else 0,
				**_no_coordinates(),
			},
		)
	for grid in spec.get("grids") or ():
		template.append(
			"fields",
			{
				"label": grid.get("label") or grid["name"],
				"fieldname": grid["name"],
				"section_name": grid.get("section") or form_spec.DEFAULT_SECTION,
				"suggested_fieldtype": "Table",
				"final_fieldtype": "Table",
				"is_table": 1,
				**_no_coordinates(),
			},
		)


def _no_coordinates():
	return {"page_number": 1, "x": 0, "y": 0, "width": 1, "height": 1, "is_printable": 0, "confidence": 100}


# ---------------------------------------------------------------------------
# Reading the uploaded sheet
# ---------------------------------------------------------------------------


def source_path(template) -> tuple[str, str]:
	if not template.source_pdf:
		frappe.throw(_("Upload the client's sheet first."))
	file_doc = frappe.get_doc("File", {"file_url": template.source_pdf})
	kind = kind_of(file_doc.file_name)
	if not kind:
		frappe.throw(
			_("Upload a PDF, Excel (.xlsx) or Word (.docx) file. Accepted: {0}").format(", ".join(ACCEPTED))
		)
	return file_doc.get_full_path(), kind


def analyze(template_name: str):
	"""Read the sheet into a spec; runs in the background on the ``long`` queue."""
	from ai_form_builder.integrations import llm

	template = frappe.get_doc(TEMPLATE, template_name)
	path, kind = source_path(template)
	template.db_set({"status": "Analyzing", "analysis_started_at": now_datetime(), "analysis_error": None})
	frappe.db.commit()
	try:
		hints = None
		sheet = draft(path, kind)
		if kind == "PDF":
			from ai_form_builder.services.pdf_analyzer import PDFAnalyzer

			inspection = PDFAnalyzer().inspect(path)
			settings = frappe.get_single("AI Form Builder Settings")
			if len(inspection["pages"]) > (settings.maximum_pages or 20):
				frappe.throw(_("The PDF has more pages than the configured maximum."))
			hints = {"widgets": inspection["widgets"]}
			template.number_of_pages = len(inspection["pages"])
		config = llm.get_config()
		if config["api_key"]:
			provider = llm.get_provider()
			spec = provider.generate_spec(kind, path, title=template.template_title, draft=sheet, hints=hints)
			template.ai_provider = config["provider"]
			template.ai_model = config["model"]
		elif sheet is not None:
			# No AI configured: the structural read of an Excel/Word sheet is
			# already a working form for the reviewer to finish.
			spec = sheet
			template.ai_provider = template.ai_model = None
		else:
			llm.get_provider()  # throws the "no key configured" message
		set_spec(template, spec, strict=False)
		template.update(
			{
				"source_kind": kind,
				"storage_mode": SPEC,
				"status": "Review Required",
				"analysis_json": template.spec_json,
				"analysis_completed_at": now_datetime(),
				"analyzed_by": frappe.session.user,
				"analysis_error": None,
			}
		)
		template.save(ignore_permissions=True)
		frappe.publish_realtime(
			"ai_form_builder_analysis", {"template": template.name, "status": template.status}
		)
	except Exception:
		frappe.db.rollback()
		frappe.db.set_value(
			TEMPLATE,
			template_name,
			{"status": "Analysis Failed", "analysis_error": frappe.get_traceback()[-4000:]},
		)
		frappe.db.commit()
		raise


# ---------------------------------------------------------------------------
# Review, publish, revise, move between sites
# ---------------------------------------------------------------------------


def review_payload(template) -> dict:
	spec = get_spec(template)
	return {
		"name": template.name,
		"title": template.template_title,
		"code": template.template_code,
		"status": template.status,
		"version": template.template_version,
		"source": template.source_pdf,
		"source_kind": template.source_kind,
		"editable": template.status in EDITABLE_STATUSES,
		"spec": spec,
		"errors": form_spec.validate(form_spec.normalise(spec)) if spec else [_("Not analysed yet.")],
		"unplaced": sorted({f["name"] for f in spec.get("fields") or ()} - form_spec.placed_fields(spec))
		if spec
		else [],
		"field_types": list(form_spec.FIELD_TYPES),
	}


def preview_html(spec: dict) -> str:
	values, grid_rows = spec_renderer.sample_data(spec)
	return spec_renderer.render_html(spec, values, grid_rows)


def save_spec(template, raw):
	if template.status not in EDITABLE_STATUSES:
		frappe.throw(_("This revision is {0}; create a revision to change it.").format(_(template.status)))
	set_spec(template, raw, strict=False)
	if template.status in ("Uploaded", "Draft", "Analysis Failed"):
		template.status = "Review Required"
	template.save()
	return template


def publish(template):
	"""Make this revision the live one. Writes no DocType."""
	from ai_form_builder.services.form_registry import lineage

	if template.status in ("Superseded", "Disabled"):
		frappe.throw(_("A {0} revision cannot be published.").format(_(template.status)))
	try:
		set_spec(template, get_spec(template), strict=True)
	except form_spec.SpecError as error:
		frappe.throw(
			_("Fix the form before publishing:")
			+ "<br>"
			+ "<br>".join(frappe.utils.escape_html(e) for e in error.errors)
		)
	older = lineage(template)
	for name in older:
		if frappe.db.get_value(TEMPLATE, name, "status") != "Superseded":
			frappe.db.set_value(TEMPLATE, name, "status", "Superseded")
	if older:
		for doctype in ("AI Project Form Configuration", "AI Form Field Profile"):
			for name in frappe.get_all(doctype, filters={"form_template": ["in", older]}, pluck="name"):
				frappe.db.set_value(doctype, name, "form_template", template.name, update_modified=False)
	template.status = "Published"
	template.save()
	return template


def export_spec(template) -> dict:
	"""A portable copy of the form for another site (or for git, if wanted)."""
	return {
		"format": EXPORT_FORMAT,
		"template_title": template.template_title,
		"template_code": template.template_code,
		"template_version": template.template_version,
		"document_category": template.document_category,
		"description": template.description,
		"spec": get_spec(template),
	}


def import_spec(payload: dict, target_area=None, form_group=None, enable_project_configuration=1):
	"""Create a Review Required spec form from an exported copy."""
	from ai_form_builder.services.form_registry import default_reference

	if not isinstance(payload, dict) or payload.get("format") != EXPORT_FORMAT:
		frappe.throw(_("This is not an AI Form Builder export."))
	if frappe.db.exists(TEMPLATE, {"template_code": payload.get("template_code")}):
		frappe.throw(_("Form code {0} already exists on this site.").format(payload.get("template_code")))
	reference_doctype = reference_fieldname = None
	if cint(enable_project_configuration):
		reference_doctype, reference_fieldname = default_reference()
	template = frappe.get_doc(
		{
			"doctype": TEMPLATE,
			"template_title": payload.get("template_title"),
			"template_code": payload.get("template_code"),
			"template_version": payload.get("template_version"),
			"document_category": payload.get("document_category") or "Form",
			"description": payload.get("description"),
			"source_type": "AI PDF",
			"storage_mode": SPEC,
			"status": "Review Required",
			"target_area": target_area,
			"form_group": form_group,
			"enable_project_configuration": 1 if reference_doctype else 0,
			"reference_doctype": reference_doctype,
			"reference_fieldname": reference_fieldname,
		}
	)
	set_spec(template, payload.get("spec") or {}, strict=False)
	template.insert()
	return template
