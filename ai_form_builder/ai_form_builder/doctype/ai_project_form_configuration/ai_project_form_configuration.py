import frappe
from frappe import _
from frappe.model.document import Document

from ai_form_builder.services.project_form_service import populate_fields, prune_profile_overrides


class AIProjectFormConfiguration(Document):
	def validate(self):
		if not self.generated_doctype:
			self.generated_doctype = frappe.db.get_value(
				"AI Form Template", self.form_template, "generated_doctype"
			)
		if (
			not self.generated_doctype
			and frappe.db.get_value("AI Form Template", self.form_template, "storage_mode") != "Spec"
		):
			# Spec forms have no DocType: their records are AI Form Record rows.
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
		if self.field_profile:
			profile_form = frappe.db.get_value("AI Form Field Profile", self.field_profile, "form_template")
			if profile_form != self.form_template:
				frappe.throw(_("Field profile {0} belongs to another form.").format(self.field_profile))
			prune_profile_overrides(self)
		populate_fields(self)

	def on_update(self):
		if not self.is_new():
			self.db_set("configuration_version", (self.configuration_version or 1) + 1, update_modified=False)
