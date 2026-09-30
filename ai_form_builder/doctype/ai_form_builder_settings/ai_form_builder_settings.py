import frappe
from frappe.model.document import Document


class AIFormBuilderSettings(Document):
	def validate(self):
		if self.maximum_pdf_size_mb and self.maximum_pdf_size_mb < 1:
			frappe.throw("Maximum PDF Size must be at least 1 MB")
		if (
			self.minimum_font_size
			and self.default_font_size
			and self.minimum_font_size > self.default_font_size
		):
			frappe.throw("Minimum Font Size cannot exceed Default Font Size")
