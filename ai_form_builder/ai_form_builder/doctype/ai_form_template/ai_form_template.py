import frappe
from frappe import _
from frappe.model.document import Document

from ai_form_builder.utils.validation import validate_mapping


class AIFormTemplate(Document):
	def autoname(self):
		# The first revision is named by its form code (as before); later
		# revisions keep the same form code and add a revision suffix.
		self.name = (
			f"{self.template_code}-REV-{self.template_version}"
			if self.previous_revision
			else self.template_code
		)

	def validate(self):
		self._validate_unique_code()
		self._validate_source_pdf()
		self._set_area_from_group()
		if self.enable_project_configuration and not self.reference_doctype:
			frappe.throw(_("Reference DocType is required when Project Configuration is enabled."))
		for field in self.fields:
			validate_mapping(field, self.number_of_pages or None)

	def _validate_unique_code(self):
		"""One code per form; only revisions of the same form may share it."""
		others = frappe.get_all(
			"AI Form Template",
			filters={"template_code": self.template_code, "name": ("!=", self.name or "")},
			pluck="name",
		)
		if not others:
			return
		from ai_form_builder.services.form_registry import lineage

		related = set(lineage(self))
		for other in others:
			if other in related or self.name in lineage(frappe.get_doc("AI Form Template", other)):
				continue
			frappe.throw(_("Form code {0} is already used by {1}.").format(self.template_code, other))

	def _set_area_from_group(self):
		if not self.form_group:
			return
		group_area = frappe.db.get_value("AI Form Group", self.form_group, "target_area")
		if not self.target_area:
			self.target_area = group_area
		elif group_area and group_area != self.target_area:
			frappe.throw(_("Group {0} belongs to area {1}.").format(self.form_group, group_area))

	def _validate_source_pdf(self):
		if not self.source_pdf:
			return
		file_doc = frappe.get_doc("File", {"file_url": self.source_pdf})
		if not file_doc.file_name.lower().endswith(".pdf"):
			frappe.throw(_("Only PDF files may be used as form templates."))
		settings = frappe.get_single("AI Form Builder Settings")
		if file_doc.file_size and file_doc.file_size > (settings.maximum_pdf_size_mb or 25) * 1024 * 1024:
			frappe.throw(_("PDF exceeds the configured maximum size."))
		if not self.number_of_pages or self.has_value_changed("source_pdf"):
			# A PDF attached without AI analysis (manual or existing forms) still
			# needs its page count for the mapping editor's page validation.
			import fitz

			with fitz.open(file_doc.get_full_path()) as pdf:
				self.number_of_pages = len(pdf)

	def before_insert(self):
		if self.status == "Draft" and self.source_pdf and not self.previous_revision:
			self.status = "Uploaded"
