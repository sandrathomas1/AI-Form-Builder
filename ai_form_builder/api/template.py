import frappe
from frappe import _
from frappe.utils import cint

from ai_form_builder.services.extract import kind_of
from ai_form_builder.services.form_registry import LOCKED_STATUSES, default_reference
from ai_form_builder.services.template_service import analyze_template as run_analysis
from ai_form_builder.utils.validation import validate_mapping


def _manager():
	frappe.only_for(["AI Form Builder Manager", "System Manager"])


@frappe.whitelist()
def create_template_from_upload(
	template_title,
	template_code,
	source_pdf,
	document_category="Form",
	target_area=None,
	form_group=None,
	enable_project_configuration=0,
):
	"""Website frontend entrypoint; file upload remains Frappe's standard endpoint."""
	_manager()
	kind = kind_of(source_pdf)
	if not kind:
		frappe.throw(_("Upload the client's sheet as a PDF, Excel (.xlsx) or Word (.docx) file."))
	reference_doctype = reference_fieldname = None
	if cint(enable_project_configuration):
		reference_doctype, reference_fieldname = default_reference()
	doc = frappe.get_doc(
		{
			"doctype": "AI Form Template",
			"template_title": template_title,
			"template_code": template_code,
			"source_pdf": source_pdf,
			"source_kind": kind,
			"storage_mode": "Spec",
			"document_category": document_category,
			"target_area": target_area,
			"form_group": form_group,
			"enable_project_configuration": 1 if reference_doctype else 0,
			"reference_doctype": reference_doctype,
			"reference_fieldname": reference_fieldname,
		}
	).insert()
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_client_templates():
	"""Small, role-checked data set for the client-facing landing page."""
	_manager()
	return frappe.get_all(
		"AI Form Template",
		fields=["name", "template_title", "status", "generated_doctype", "storage_mode", "modified"],
		order_by="modified desc",
		limit_page_length=20,
	)


@frappe.whitelist()
def analyze_template(template_name):
	_manager()
	template = frappe.get_doc("AI Form Template", template_name)
	template.check_permission("write")
	if template.status == "Analyzing":
		frappe.throw(_("Analysis is already running."))
	from ai_form_builder.services.spec_service import is_spec_form

	if is_spec_form(template):
		from ai_form_builder.api.spec_forms import queue_analysis

		return queue_analysis(template)
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


@frappe.whitelist()
def save_mapping(template_name, fields, sections=None):
	"""Replace mapping rows after validating browser-provided values server-side."""
	_manager()
	template = frappe.get_doc("AI Form Template", template_name)
	template.check_permission("write")
	if template.status in LOCKED_STATUSES:
		frappe.throw(
			_("This revision is {0}; create a revision to change its mapping.").format(_(template.status))
		)
	if template.status not in {"Review Required", "Approved"} and not template.generated_doctype:
		frappe.throw(_("Analyze the template before editing its mapping."))
	fields = frappe.parse_json(fields)
	sections = frappe.parse_json(sections or "[]")
	if not isinstance(fields, list) or not isinstance(sections, list):
		frappe.throw(_("Mapping must contain field and section lists."))
	# Once a DocType exists the mapping can only place that DocType's fields.
	live_fields = (
		{df.fieldname for df in frappe.get_meta(template.generated_doctype).fields}
		if template.generated_doctype and frappe.db.exists("DocType", template.generated_doctype)
		else None
	)
	template.set("fields", [])
	fieldnames = set()
	for row in fields:
		mapping = template.append("fields", row)
		mapping.page_number = cint(mapping.page_number)
		validate_mapping(mapping, template.number_of_pages)
		if not mapping.ignore_field and mapping.fieldname in fieldnames:
			frappe.throw(_("Fieldnames must be unique."))
		fieldnames.add(mapping.fieldname)
		if live_fields is not None and not mapping.ignore_field:
			target = mapping.existing_field_mapping or mapping.fieldname
			if target not in live_fields and mapping.get("mapping_status") != "Orphaned":
				frappe.throw(
					_("{0} is not a field of {1}. Add it with Frappe, then use Sync Fields.").format(
						target, template.generated_doctype
					)
				)
	template.set("sections", [])
	for row in sections:
		if not row.get("section_label") or not row.get("section_key"):
			frappe.throw(_("Every section needs a label and stable key."))
		template.append("sections", row)
	template.save()
	return get_template_fields(template.name)
