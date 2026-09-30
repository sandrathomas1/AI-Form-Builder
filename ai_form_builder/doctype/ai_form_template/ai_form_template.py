import frappe
from frappe import _
from frappe.model.document import Document

from ai_form_builder.utils.validation import validate_mapping


class AIFormTemplate(Document):
	def validate(self):
		self._validate_source_pdf()
		for field in self.fields:
			validate_mapping(field, self.number_of_pages or None)

	def _validate_source_pdf(self):
		if not self.source_pdf:
			return
		file_doc = frappe.get_doc("File", {"file_url": self.source_pdf})
		if not file_doc.file_name.lower().endswith(".pdf"):
			frappe.throw(_("Only PDF files may be used as form templates."))
		settings = frappe.get_single("AI Form Builder Settings")
		if file_doc.file_size and file_doc.file_size > (settings.maximum_pdf_size_mb or 25) * 1024 * 1024:
			frappe.throw(_("PDF exceeds the configured maximum size."))

	def before_insert(self):
		if self.status == "Draft" and self.source_pdf:
			self.status = "Uploaded"
