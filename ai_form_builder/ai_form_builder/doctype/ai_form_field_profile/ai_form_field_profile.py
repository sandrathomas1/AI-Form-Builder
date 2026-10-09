from frappe.model.document import Document

from ai_form_builder.services.project_form_service import populate_fields


class AIFormFieldProfile(Document):
	def validate(self):
		# A profile starts from the master form; existing choices are never overwritten.
		populate_fields(self)
