import frappe
from frappe import _
from frappe.model.document import Document

from ai_form_builder.services.project_form_service import populate_fields


class AIProjectFormConfiguration(Document):
	def validate(self):
		if not self.generated_doctype:
			self.generated_doctype = frappe.db.get_value("AI Form Template", self.form_template, "generated_doctype")
		if not self.generated_doctype:
			frappe.throw(_("The selected template has no generated DocType."))
		existing = frappe.db.exists(
			"AI Project Form Configuration",
			{
				"reference_doctype": self.reference_doctype,
				"reference_name": self.reference_name,
				"form_template": self.form_template,
				"name": ("!=", self.name or ""),
			},
		)
		if existing:
			frappe.throw(_("Only one configuration is allowed for this reference and form template."))
		populate_fields(self)

	def on_update(self):
		if not self.is_new():
			self.db_set("configuration_version", (self.configuration_version or 1) + 1, update_modified=False)
