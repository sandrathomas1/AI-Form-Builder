import base64
from io import BytesIO

import fitz
import frappe
from frappe.utils import format_value


class PDFRenderer:
	def render(self, template, document) -> bytes:
		file_doc = frappe.get_doc("File", {"file_url": template.source_pdf})
		pdf = fitz.open(file_doc.get_full_path())
		overflowed = []
		for field in template.fields:
			if field.ignore_field or not field.is_printable or field.page_number > len(pdf):
				continue
			value = document.get(field.existing_field_mapping or field.fieldname)
			if value in (None, ""):
				continue
			rect = fitz.Rect(field.x, field.y, field.x + field.width, field.y + field.height)
			page = pdf[field.page_number - 1]
			if field.is_signature or field.final_fieldtype == "Signature":
				self._insert_signature(page, rect, value)
				continue
			if field.is_option_group:
				if str(value) == str(field.option_value):
					page.insert_textbox(rect, "✓", fontsize=min(field.font_size or 10, rect.height), align=1)
				continue
			text = format_value(value, field.final_fieldtype or "Data")
			font_size = field.font_size or template.default_font_size or 10
			placed = False
			while font_size >= (template.minimum_font_size or 6):
				if (
					page.insert_textbox(
						rect,
						text,
						fontsize=font_size,
						fontname=field.font_family or template.default_font or "helv",
						align={"Left": 0, "Center": 1, "Right": 2}.get(field.horizontal_alignment, 0),
					)
					>= 0
				):
					placed = True
					break
				font_size -= 1
			if not placed:
				overflowed.append(field.label)
				if field.overflow_strategy == "Error":
					pdf.close()
					frappe.throw(frappe._("Value does not fit in PDF field: {0}").format(field.label))
		buffer = BytesIO()
		pdf.save(buffer)
		pdf.close()
		if overflowed:
			frappe.log_error(
				message=", ".join(overflowed), title="AI Form Builder PDF fields could not fit their values"
			)
		return buffer.getvalue()

	def _insert_signature(self, page, rect, value):
		"""Insert a base64/data-URI signature without exposing it publicly."""
		if not isinstance(value, str):
			return
		try:
			payload = value.split(",", 1)[1] if value.startswith("data:") else value
			page.insert_image(rect, stream=base64.b64decode(payload), keep_proportion=True, overlay=True)
		except (IndexError, ValueError, TypeError):
			frappe.log_error(title="AI Form Builder signature could not be rendered")
