"""Focused tests for the project form overlay.

These avoid site fixtures so the business rules remain quick to validate in
isolation; Frappe integration tests exercise the same public services.
"""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai_form_builder.services import pdf_renderer, project_form_service as service


class FakeConfiguration:
	def __init__(self, fields=None, form_template="MASTER"):
		self.fields = fields or []
		self.form_template = form_template

	def append(self, fieldname, value):
		assert fieldname == "fields"
		self.fields.append(SimpleNamespace(**value))

	def set(self, fieldname, value):
		assert fieldname == "fields"
		self.fields = value


def row(**kwargs):
	return SimpleNamespace(**kwargs)


def master_template():
	return SimpleNamespace(
		fields=[
			row(fieldname="project", label="Project", mandatory=1, read_only=1, ignore_field=0, final_fieldtype="Link"),
			row(fieldname="supplier", label="Supplier", mandatory=1, read_only=0, ignore_field=0, final_fieldtype="Data"),
			row(fieldname="layout", label="Layout", mandatory=0, read_only=0, ignore_field=0, final_fieldtype="Section Break"),
			row(fieldname="ignored", label="Ignored", mandatory=0, read_only=0, ignore_field=1, final_fieldtype="Data"),
		]
	)


def test_sync_preserves_project_overrides_and_adds_new_master_fields():
	config = FakeConfiguration([row(fieldname="project", field_label="Project", enabled=0, mandatory=0, read_only=0)])
	with patch.object(service, "get_template", return_value=master_template()):
		service.populate_fields(config)
	assert [(field.fieldname, field.enabled) for field in config.fields] == [("project", 0), ("supplier", 1)]


def test_reset_to_master_never_changes_the_generated_doctype_or_values():
	config = FakeConfiguration([row(fieldname="supplier", field_label="Supplier", enabled=0, mandatory=0, read_only=1, label_override="Vendor")])
	with patch.object(service, "get_template", return_value=master_template()):
		service.reset_fields_to_master(config)
	assert [(field.fieldname, field.enabled, field.mandatory, field.read_only, field.label_override) for field in config.fields] == [
		("project", 1, 1, 1, ""),
		("supplier", 1, 1, 0, ""),
	]


def test_each_project_configuration_keeps_independent_field_overrides():
	project_a = FakeConfiguration([row(fieldname="supplier", enabled=0, mandatory=0, read_only=0, label_override="")])
	project_b = FakeConfiguration([row(fieldname="supplier", enabled=1, mandatory=1, read_only=0, label_override="Vendor")])
	assert service.configuration_dict(project_a)["supplier"]["enabled"] is False
	assert service.configuration_dict(project_b)["supplier"] == {"enabled": True, "mandatory": True, "read_only": False, "label_override": "Vendor"}


def test_existing_document_prefers_its_configuration_snapshot():
	document = SimpleNamespace(
		ai_form_configuration_snapshot='{"supplier": {"enabled": false}}',
		ai_form_project_configuration="CONFIG-A",
		is_new=lambda: False,
		get=lambda key: getattr(document, key, None),
	)
	template = SimpleNamespace(enable_project_configuration=1)
	assert service.get_document_configuration(template, document) == ({"supplier": {"enabled": False}}, "CONFIG-A")


def test_project_aware_validation_ignores_disabled_master_mandatory_field():
	class ValidationError(Exception):
		pass

	document = SimpleNamespace(
		doctype="Generated QA",
		is_new=lambda: True,
		meta=SimpleNamespace(get_label=lambda fieldname: fieldname),
		get=lambda key: {"ai_form_template": "MASTER", "supplier": None}.get(key),
	)
	template = SimpleNamespace(enable_project_configuration=1)
	fake_frappe = SimpleNamespace(
		db=SimpleNamespace(exists=lambda *args: True, get_value=lambda *args: 1),
		throw=lambda message: (_ for _ in ()).throw(ValidationError(message)),
	)
	with patch.object(service, "frappe", fake_frappe), patch.object(service, "get_template", return_value=template), patch.object(service, "get_document_configuration", return_value=({"supplier": {"enabled": False, "mandatory": True}}, "CONFIG-A")), patch.object(service, "snapshot_document_configuration"):
		service.validate_project_form(document)


def test_renderer_skips_disabled_fields_and_renders_enabled_fields():
	class FakePage:
		def __init__(self):
			self.values = []

		def insert_textbox(self, rect, text, **kwargs):
			self.values.append(text)
			return 1

	class FakePDF:
		def __init__(self):
			self.page = FakePage()

		def __len__(self):
			return 1

		def __getitem__(self, index):
			return self.page

		def save(self, buffer):
			buffer.write(b"pdf")

		def close(self):
			pass

	pdf = FakePDF()
	template = SimpleNamespace(
		source_pdf="/private/form.pdf", default_font="helv", default_font_size=10, minimum_font_size=6,
		fields=[
			row(fieldname="supplier", existing_field_mapping=None, ignore_field=0, is_printable=1, page_number=1, x=0, y=0, width=10, height=10, is_signature=0, final_fieldtype="Data", is_option_group=0, font_size=None, font_family=None, horizontal_alignment="Left", overflow_strategy="Wrap Then Shrink", label="Supplier"),
			row(fieldname="material", existing_field_mapping=None, ignore_field=0, is_printable=1, page_number=1, x=0, y=0, width=10, height=10, is_signature=0, final_fieldtype="Data", is_option_group=0, font_size=None, font_family=None, horizontal_alignment="Left", overflow_strategy="Wrap Then Shrink", label="Material"),
		],
	)
	document = {"supplier": "Must stay hidden", "material": "Concrete"}
	with patch.object(pdf_renderer.frappe, "get_doc", return_value=SimpleNamespace(get_full_path=lambda: "/tmp/form.pdf")), patch.object(pdf_renderer.fitz, "open", return_value=pdf), patch.object(pdf_renderer, "get_document_configuration", return_value=({"supplier": {"enabled": False}, "material": {"enabled": True}}, "CONFIG-A")):
		assert pdf_renderer.PDFRenderer().render(template, document) == b"pdf"
	assert pdf.page.values == ["Concrete"]


def load_tests(loader, tests, pattern):
	return unittest.TestSuite(
		unittest.FunctionTestCase(test)
		for test in (
			test_sync_preserves_project_overrides_and_adds_new_master_fields,
			test_reset_to_master_never_changes_the_generated_doctype_or_values,
			test_each_project_configuration_keeps_independent_field_overrides,
			test_existing_document_prefers_its_configuration_snapshot,
			test_project_aware_validation_ignores_disabled_master_mandatory_field,
			test_renderer_skips_disabled_fields_and_renders_enabled_fields,
		)
	)
