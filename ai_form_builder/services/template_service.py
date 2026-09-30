import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ai_form_builder.integrations.openai_provider import OpenAIProvider
from ai_form_builder.services.pdf_analyzer import PDFAnalyzer
from ai_form_builder.services.schema_validator import validate_analysis


def analyze_template(template_name: str):
	template = frappe.get_doc("AI Form Template", template_name)
	file_doc = frappe.get_doc("File", {"file_url": template.source_pdf})
	inspection = PDFAnalyzer().inspect(file_doc.get_full_path())
	settings = frappe.get_single("AI Form Builder Settings")
	if len(inspection["pages"]) > (settings.maximum_pages or 20):
		frappe.throw(_("PDF exceeds the configured maximum page count."))
	template.db_set("status", "Analyzing")
	template.db_set("analysis_started_at", now_datetime())
	try:
		analysis = PDFAnalyzer().acroform_analysis(inspection)
		if not analysis:
			provider = OpenAIProvider(settings.get_password("api_key"), settings.ai_model)
			analysis = provider.analyze_document(
				inspection, PDFAnalyzer().render_page_images(file_doc.get_full_path())
			)
		analysis = validate_analysis(analysis)
		template.set("sections", [])
		for item in analysis.get("sections", []):
			template.append(
				"sections",
				{
					"section_label": item["label"],
					"section_key": item["key"],
					"sequence": item.get("sequence", 0),
					"page_number": item.get("page", 1),
				},
			)
		template.set("fields", [])
		for item in analysis["fields"]:
			rect = item["rect"]
			template.append(
				"fields",
				{
					"label": item.get("label"),
					"fieldname": item["fieldname"],
					"suggested_fieldtype": item["suggested_fieldtype"],
					"final_fieldtype": item["suggested_fieldtype"],
					"section_name": item.get("section"),
					"page_number": item["page"],
					"x": rect["x"],
					"y": rect["y"],
					"width": rect["width"],
					"height": rect["height"],
					"mandatory": item.get("mandatory", False),
					"confidence": item.get("confidence", 0),
				},
			)
		template.update(
			{
				"number_of_pages": len(inspection["pages"]),
				"analysis_json": json.dumps(analysis),
				"status": "Review Required",
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
		template.db_set("status", "Analysis Failed")
		template.db_set("analysis_error", frappe.get_traceback())
		raise
