import base64

import fitz

WIDGET_FIELD_TYPES = {
	"Text": "Data",
	"Text Field": "Data",
	"CheckBox": "Check",
	"Checkbox": "Check",
	"ComboBox": "Select",
	"ListBox": "Select",
	"Signature": "Signature",
}


class PDFAnalyzer:
	"""Read untrusted PDFs as data only; coordinates are PDF points from top-left."""

	def inspect(self, path: str) -> dict:
		document = fitz.open(path)
		pages = []
		widgets = []
		for index, page in enumerate(document):
			text = page.get_text("text")
			pages.append(
				{"page": index + 1, "width": page.rect.width, "height": page.rect.height, "text": text}
			)
			for widget in page.widgets() or []:
				rect = widget.rect
				widgets.append(
					{
						"name": widget.field_name,
						"type": str(widget.field_type_string),
						"page": index + 1,
						"rect": {"x": rect.x0, "y": rect.y0, "width": rect.width, "height": rect.height},
					}
				)
		document.close()
		return {"pages": pages, "widgets": widgets, "has_text": any(page["text"].strip() for page in pages)}

	def acroform_analysis(self, inspection: dict) -> dict | None:
		"""Build a deterministic mapping when editable widgets are present.

		This deliberately avoids a paid AI request. Widget coordinates already use the
		same top-left PDF point model used by the renderer.
		"""
		if not inspection["widgets"]:
			return None
		fields = []
		for widget in inspection["widgets"]:
			fieldtype = WIDGET_FIELD_TYPES.get(widget["type"], "Data")
			rect = widget["rect"]
			fields.append(
				{
					"label": widget["name"] or "PDF Field",
					"fieldname": widget["name"] or f"pdf_field_{len(fields) + 1}",
					"suggested_fieldtype": fieldtype,
					"section": "pdf_fields",
					"page": widget["page"],
					"rect": rect,
					"mandatory": False,
					"confidence": 1.0,
				}
			)
		return {
			"document": {"title": "PDF Form", "classification": "form", "pages": len(inspection["pages"])},
			"sections": [{"key": "pdf_fields", "label": "PDF Fields", "sequence": 1, "page": 1}],
			"fields": fields,
		}

	def render_page_images(self, path: str, scale: float = 1.25) -> list[str]:
		"""Render flat-PDF pages for vision analysis without persisting images."""
		document = fitz.open(path)
		images = []
		for page in document:
			pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
			images.append("data:image/jpeg;base64," + base64.b64encode(pixmap.tobytes("jpeg")).decode())
		document.close()
		return images
