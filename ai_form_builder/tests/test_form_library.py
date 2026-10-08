"""Integration tests for the Form Library, project configuration and Docuflow adapter.

They run against a real site (`bench --site <site> run-tests --app ai_form_builder`)
and create throw-away Custom DocTypes prefixed "AFB Test", removed afterwards.
"""

import json
from unittest.mock import patch

import fitz
import frappe
from frappe.tests.utils import FrappeTestCase

from ai_form_builder.api import forms as forms_api
from ai_form_builder.api import manual_form, project_configuration
from ai_form_builder.api import template as template_api
from ai_form_builder.api.generator import generate_doctype
from ai_form_builder.api.pdf import generate_pdf
from ai_form_builder.integrations import docuflow
from ai_form_builder.services import form_registry
from ai_form_builder.services.project_form_service import configuration_dict, template_rows
from ai_form_builder.services.template_service import analyze_template

PROJECT = "AFB Test Project"
SAFETY = "AFB Test Safety Inspection"
SAFETY_ITEM = "AFB Test Safety Item"
TEST_USER = "afb-test-user@example.com"


def _pdf_url(name, with_widget=False):
	pdf = fitz.open()
	page = pdf.new_page()
	page.insert_text((40, 60), "Client form")
	if with_widget:
		widget = fitz.Widget()
		widget.field_name = "inspector_name"
		widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
		widget.rect = fitz.Rect(40, 100, 240, 120)
		page.add_widget(widget)
	content = pdf.tobytes()
	pdf.close()
	return (
		frappe.get_doc({"doctype": "File", "file_name": f"{name}.pdf", "content": content, "is_private": 1})
		.insert(ignore_permissions=True)
		.file_url
	)


def _drop_doctype(name):
	if frappe.db.exists("DocType", name):
		for template in frappe.get_all("AI Form Template", filters={"generated_doctype": name}, pluck="name"):
			_drop_template(template)
		frappe.delete_doc("DocType", name, force=True, ignore_permissions=True)
	for script in frappe.get_all("Client Script", filters={"dt": name}, pluck="name"):
		frappe.delete_doc("Client Script", script, force=True, ignore_permissions=True)
	# Custom DocType deletion keeps the table; test DocTypes must leave nothing behind.
	frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{name}`")


def _pdf_bytes(file_url):
	with open(frappe.get_doc("File", {"file_url": file_url}).get_full_path(), "rb") as handle:
		return handle.read()


def _drop_template(name):
	for doctype in ("AI Project Form Configuration", "AI Form Field Profile"):
		for row in frappe.get_all(doctype, filters={"form_template": name}, pluck="name"):
			frappe.delete_doc(doctype, row, force=True, ignore_permissions=True)
	for child in frappe.get_all("AI Form Template", filters={"previous_revision": name}, pluck="name"):
		_drop_template(child)
	if frappe.db.exists("AI Form Template", name):
		frappe.delete_doc("AI Form Template", name, force=True, ignore_permissions=True)


def _add_fields(doctype, fields):
	"""What an administrator does in Frappe's Form Builder, then Save."""
	doc = frappe.get_doc("DocType", doctype)
	for field in fields:
		doc.append("fields", field)
	doc.save()
	frappe.clear_cache(doctype=doctype)


def _cleanup():
	frappe.set_user("Administrator")
	for doctype in (
		SAFETY,
		"AFB Test Concrete Inspection",
		"AFB Test Observation",
		"AFB Test Design Review",
		"AFB Test AI Form",
		"AFB Test Mapped Form",
		SAFETY_ITEM,
	):
		_drop_doctype(doctype)
	for template in frappe.get_all(
		"AI Form Template", filters={"template_code": ["like", "AFB-T-%"]}, pluck="name"
	):
		_drop_template(template)
	for name in frappe.get_all(
		"Custom Field", filters={"dt": "ToDo", "fieldname": ["like", "%afb%"]}, pluck="name"
	):
		frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
	for name in frappe.get_all(
		"Custom Field", filters={"dt": "ToDo", "fieldname": ["like", "ai_form_%"]}, pluck="name"
	):
		frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
	frappe.clear_cache(doctype="ToDo")
	for name in ("AFB Test Civil", "AFB Test Structural", "AFB Test Engineering"):
		for doctype in ("AI Form Group", "AI Form Area"):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	_drop_doctype(PROJECT)
	if frappe.db.exists("User", TEST_USER):
		frappe.delete_doc("User", TEST_USER, force=True, ignore_permissions=True)
	frappe.db.commit()


class FormLibraryTestCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_cleanup()
		frappe.get_doc(
			{
				"doctype": "DocType",
				"name": PROJECT,
				"module": "AI Form Builder",
				"custom": 1,
				"autoname": "field:project_code",
				"fields": [
					{
						"fieldname": "project_code",
						"label": "Project Code",
						"fieldtype": "Data",
						"reqd": 1,
						"unique": 1,
					}
				],
				"permissions": [
					{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
					{"role": "AI Form Builder User", "read": 1},
				],
			}
		).insert()
		for code in ("AFB-A", "AFB-B", "AFB-C"):
			frappe.get_doc({"doctype": PROJECT, "project_code": code}).insert()
		frappe.get_doc(
			{
				"doctype": "DocType",
				"name": SAFETY_ITEM,
				"module": "AI Form Builder",
				"custom": 1,
				"istable": 1,
				"fields": [
					{"fieldname": "item", "label": "Item", "fieldtype": "Data", "reqd": 1, "in_list_view": 1}
				],
			}
		).insert()
		cls.safety = manual_form.create_manual_form(
			template_title=SAFETY,
			template_code="AFB-T-SI",
			form_group="Safety",
			enable_project_configuration=1,
			reference_doctype=PROJECT,
			reference_fieldname="project",
			allow_attachments=1,
		)["template"]
		_add_fields(
			SAFETY,
			[
				{"fieldname": "inspection_date", "label": "Date", "fieldtype": "Date", "reqd": 1},
				{"fieldname": "area_name", "label": "Area", "fieldtype": "Data"},
				{"fieldname": "inspector", "label": "Inspector", "fieldtype": "Data", "reqd": 1},
				{"fieldname": "permit_number", "label": "Permit Number", "fieldtype": "Data", "reqd": 1},
				{"fieldname": "contractor", "label": "Contractor", "fieldtype": "Data", "reqd": 1},
				{"fieldname": "finding", "label": "Finding", "fieldtype": "Small Text"},
				{"fieldname": "corrective_action", "label": "Corrective Action", "fieldtype": "Small Text"},
				{
					"fieldname": "items",
					"label": "Items",
					"fieldtype": "Table",
					"options": SAFETY_ITEM,
					"reqd": 1,
				},
				{"fieldname": "signature", "label": "Signature", "fieldtype": "Signature"},
			],
		)
		forms_api.sync_fields(cls.safety)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		_cleanup()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")

	# helpers -------------------------------------------------------------
	def configure(self, project, fields=None, profile=None, enabled=1):
		name = project_configuration.set_form_enabled(PROJECT, project, self.safety, enabled)
		doc = frappe.get_doc("AI Project Form Configuration", name)
		doc.field_profile = profile
		if profile:
			# Applying a profile in the UI starts the grid from the profile.
			doc.set("fields", [])
		rows = {row.fieldname: row for row in doc.fields}
		for fieldname, rules in (fields or {}).items():
			row = rows.get(fieldname) or doc.append("fields", {"fieldname": fieldname})
			row.update(rules)
		doc.save()
		return doc

	def inspection(self, project, **values):
		data = {
			"doctype": SAFETY,
			"project": project,
			"inspection_date": "2026-10-08",
			"inspector": "Inspector",
			"items": [{"item": "Scaffold"}],
		}
		data.update(values)
		return frappe.get_doc(data)


class TestAreasAndGroups(FormLibraryTestCase):
	def test_initial_quality_and_hse_configuration(self):
		self.assertTrue(frappe.db.exists("AI Form Area", "Quality"))
		self.assertTrue(frappe.db.exists("AI Form Area", "HSE"))
		self.assertEqual(frappe.db.get_value("AI Form Group", "QA", "target_area"), "Quality")
		self.assertEqual(frappe.db.get_value("AI Form Group", "QC", "target_area"), "Quality")
		self.assertEqual(frappe.db.get_value("AI Form Group", "Safety", "target_area"), "HSE")

	def test_new_area_and_group_hierarchy_need_no_code(self):
		frappe.get_doc(
			{"doctype": "AI Form Area", "area_name": "AFB Test Engineering", "sequence": 30}
		).insert()
		frappe.get_doc(
			{
				"doctype": "AI Form Group",
				"group_name": "AFB Test Civil",
				"target_area": "AFB Test Engineering",
			}
		).insert()
		sub = frappe.get_doc(
			{
				"doctype": "AI Form Group",
				"group_name": "AFB Test Structural",
				"parent_group": "AFB Test Civil",
			}
		).insert()
		self.assertEqual(sub.target_area, "AFB Test Engineering")
		group = frappe.get_doc("AI Form Group", "AFB Test Civil")
		group.parent_group = "AFB Test Structural"
		self.assertRaises(frappe.ValidationError, group.save)
		wrong = frappe.get_doc(
			{
				"doctype": "AI Form Group",
				"group_name": "AFB Test Wrong",
				"parent_group": "AFB Test Civil",
				"target_area": "HSE",
			}
		)
		self.assertRaises(frappe.ValidationError, wrong.insert)

		# Scenario 5: a form in the new area, assigned to a project, works end to end.
		created = manual_form.create_manual_form(
			template_title="AFB Test Design Review",
			template_code="AFB-T-DRR",
			form_group="AFB Test Structural",
			enable_project_configuration=1,
			reference_doctype=PROJECT,
			reference_fieldname="project",
		)
		template = frappe.get_doc("AI Form Template", created["template"])
		self.assertEqual(template.target_area, "AFB Test Engineering")
		project_configuration.set_form_enabled(PROJECT, "AFB-A", template.name, 1)
		forms = form_registry.get_enabled_forms(PROJECT, "AFB-A", area="AFB Test Engineering")
		self.assertEqual([form["doctype"] for form in forms], ["AFB Test Design Review"])
		self.assertEqual(forms[0]["group_path"], ["AFB Test Civil", "AFB Test Structural"])
		frappe.get_doc({"doctype": "AFB Test Design Review", "project": "AFB-A"}).insert()


class TestManualForms(FormLibraryTestCase):
	def test_manual_form_is_a_custom_doctype_without_source_files(self):
		meta = frappe.get_meta(SAFETY)
		self.assertTrue(meta.custom)
		self.assertEqual(meta.module, "AI Form Builder")
		for fieldname in ("project", "attachment", "ai_form_template", "ai_form_configuration_snapshot"):
			self.assertTrue(meta.get_field(fieldname), fieldname)
		self.assertEqual(meta.get_field("ai_form_template").default, self.safety)
		path = frappe.get_module_path("AI Form Builder", "doctype", frappe.scrub(SAFETY))
		self.assertFalse(frappe.os.path.exists(path))
		template = frappe.get_doc("AI Form Template", self.safety)
		self.assertEqual(
			(template.source_type, template.status, template.target_area), ("Manual", "Generated", "HSE")
		)

	def test_quality_form_scenario(self):
		created = manual_form.create_manual_form(
			template_title="AFB Test Concrete Inspection",
			template_code="AFB-T-CIR",
			form_group="QA",
			enable_project_configuration=1,
			reference_doctype=PROJECT,
			reference_fieldname="project",
			allow_attachments=1,
		)
		self.assertEqual(created["route"], ["Form", "DocType", "AFB Test Concrete Inspection"])
		_add_fields(
			"AFB Test Concrete Inspection",
			[
				{"fieldname": "inspection_date", "label": "Date", "fieldtype": "Date"},
				{"fieldname": "location", "label": "Location", "fieldtype": "Data"},
				{"fieldname": "drawing", "label": "Drawing", "fieldtype": "Data"},
				{
					"fieldname": "inspection_result",
					"label": "Inspection Result",
					"fieldtype": "Select",
					"options": "\nAccepted\nRejected",
				},
				{"fieldname": "comments", "label": "Comments", "fieldtype": "Small Text"},
				{"fieldname": "signature", "label": "Signature", "fieldtype": "Signature"},
			],
		)
		summary = forms_api.sync_fields(created["template"])
		self.assertIn("inspection_result", summary["added"])
		forms_api.publish(created["template"])
		project_configuration.set_form_enabled(PROJECT, "AFB-A", created["template"], 1)
		forms = form_registry.get_enabled_forms(PROJECT, "AFB-A", area="Quality")
		self.assertEqual(
			[(form["title"], form["group"]) for form in forms], [("AFB Test Concrete Inspection", "QA")]
		)
		doc = frappe.get_doc(
			{"doctype": "AFB Test Concrete Inspection", "project": "AFB-A", "inspection_result": "Accepted"}
		).insert()
		self.assertEqual(doc.ai_form_template, created["template"])
		self.assertEqual(form_registry.get_enabled_forms(PROJECT, "AFB-B", area="Quality"), [])

	def test_hse_form_scenario_without_ai(self):
		created = manual_form.create_manual_form(
			template_title="AFB Test Observation",
			template_code="AFB-T-OBS",
			form_group="Safety",
			enable_project_configuration=1,
			reference_doctype=PROJECT,
			reference_fieldname="project",
		)
		with patch("ai_form_builder.integrations.openai_provider.OpenAIProvider") as provider:
			project_configuration.set_form_enabled(PROJECT, "AFB-A", created["template"], 1)
			frappe.get_doc({"doctype": "AFB Test Observation", "project": "AFB-A"}).insert()
			provider.assert_not_called()
		self.assertEqual(frappe.db.get_value("AI Form Template", created["template"], "target_area"), "HSE")

	def test_sync_adds_updates_and_orphans_without_losing_mapping(self):
		template = frappe.get_doc("AI Form Template", self.safety)
		row = next(row for row in template.fields if row.fieldname == "finding")
		row.update({"x": 50, "y": 60, "width": 200, "height": 30, "is_printable": 1})
		template.save()
		_add_fields(SAFETY, [{"fieldname": "weather", "label": "Weather", "fieldtype": "Data"}])
		doctype = frappe.get_doc("DocType", SAFETY)
		next(f for f in doctype.fields if f.fieldname == "finding").label = "Observation"
		doctype.save()
		summary = forms_api.sync_fields(self.safety)
		self.assertIn("finding", summary["updated"])
		template.reload()
		finding = next(row for row in template.fields if row.fieldname == "finding")
		self.assertEqual(
			(finding.label, finding.x, finding.y, finding.is_printable), ("Observation", 50, 60, 1)
		)

		doctype = frappe.get_doc("DocType", SAFETY)
		doctype.fields = [f for f in doctype.fields if f.fieldname != "weather"]
		doctype.save()
		summary = forms_api.sync_fields(self.safety)
		self.assertEqual(summary["orphaned"], ["weather"])
		template.reload()
		weather = next(row for row in template.fields if row.fieldname == "weather")
		self.assertEqual(weather.mapping_status, "Orphaned")
		self.assertEqual(forms_api.sync_fields(self.safety)["orphaned"], [])

	def test_table_field_is_registered_not_flattened(self):
		template = frappe.get_doc("AI Form Template", self.safety)
		items = next(row for row in template.fields if row.fieldname == "items")
		self.assertEqual(
			(items.final_fieldtype, items.link_target, items.is_table), ("Table", SAFETY_ITEM, 1)
		)
		self.assertFalse(any(row.fieldname == "item" for row in template.fields))


def _reset_todo():
	for template in frappe.get_all("AI Form Template", filters={"generated_doctype": "ToDo"}, pluck="name"):
		_drop_template(template)
	for name in frappe.get_all(
		"Custom Field",
		filters={
			"dt": "ToDo",
			"fieldname": [
				"in",
				[
					"afb_project",
					"ai_form_template",
					"ai_form_project_configuration",
					"ai_form_configuration_snapshot",
				],
			],
		},
		pluck="name",
	):
		frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
	frappe.clear_cache(doctype="ToDo")


def _docfield_count(doctype):
	return frappe.db.count("DocField", {"parent": doctype})


class TestExistingDocType(FormLibraryTestCase):
	def setUp(self):
		super().setUp()
		_reset_todo()

	def tearDown(self):
		_reset_todo()

	def test_register_existing_standard_doctype_without_changing_it(self):
		fields_before = _docfield_count("ToDo")
		created = forms_api.register_existing_doctype("ToDo", "AFB Test Todo", "AFB-T-TODO", form_group="QC")
		template = frappe.get_doc("AI Form Template", created["template"])
		self.assertEqual(
			(template.source_type, template.generated_doctype, template.status),
			("Existing DocType", "ToDo", "Generated"),
		)
		self.assertTrue(any(row.fieldname == "description" for row in template.fields))
		self.assertEqual(_docfield_count("ToDo"), fields_before)
		self.assertFalse(frappe.get_meta("ToDo").get_field("ai_form_template"))
		self.assertRaises(
			frappe.ValidationError,
			forms_api.register_existing_doctype,
			"ToDo",
			"AFB Test Todo 2",
			"AFB-T-TODO2",
		)
		self.assertEqual(form_registry.edit_route("ToDo")["route"], ["Form", "Customize Form"])

	def test_project_configured_existing_doctype_gets_custom_fields_only(self):
		from frappe.custom.doctype.custom_field.custom_field import create_custom_field

		fields_before = _docfield_count("ToDo")
		create_custom_field(
			"ToDo", {"fieldname": "afb_project", "label": "Project", "fieldtype": "Link", "options": PROJECT}
		)
		created = forms_api.register_existing_doctype(
			"ToDo",
			"AFB Test Todo P",
			"AFB-T-TODOP",
			enable_project_configuration=1,
			reference_doctype=PROJECT,
			reference_fieldname="afb_project",
		)
		meta = frappe.get_meta("ToDo")
		self.assertTrue(meta.get_field("ai_form_template"))
		self.assertEqual(meta.get_field("ai_form_template").default, created["template"])
		self.assertEqual(_docfield_count("ToDo"), fields_before)
		project_configuration.set_form_enabled(PROJECT, "AFB-A", created["template"], 1)
		todo = frappe.get_doc({"doctype": "ToDo", "description": "Check", "afb_project": "AFB-A"}).insert()
		self.assertEqual(todo.ai_form_template, created["template"])
		self.assertTrue(todo.ai_form_configuration_snapshot)
		# ToDo records outside the library flow are untouched by the hook.
		frappe.get_doc({"doctype": "Note", "title": "AFB plain note"}).insert().delete()


class TestProjectConfiguration(FormLibraryTestCase):
	def test_same_form_two_projects_hidden_fields_are_not_mandatory(self):
		self.configure("AFB-A", {"permit_number": {"enabled": 0}, "contractor": {"enabled": 0}})
		self.configure(
			"AFB-B",
			{"permit_number": {"enabled": 1, "mandatory": 1}, "contractor": {"enabled": 1, "mandatory": 1}},
		)
		a = self.inspection("AFB-A").insert()
		self.assertTrue(a.name)
		self.assertRaises(frappe.MandatoryError, self.inspection("AFB-B").insert)
		self.inspection("AFB-B", permit_number="PTW-1", contractor="ACME").insert()
		meta = frappe.get_meta(SAFETY)
		self.assertTrue(meta.get_field("permit_number") and meta.get_field("contractor"))
		self.assertTrue(frappe.db.has_column(SAFETY, "permit_number"))

	def test_master_mandatory_still_applies_to_unconfigured_fields(self):
		self.configure("AFB-A", {"permit_number": {"enabled": 0}, "contractor": {"enabled": 0}})
		doc = self.inspection("AFB-A")
		doc.inspector = None
		config = frappe.get_doc(
			"AI Project Form Configuration", {"reference_name": "AFB-A", "form_template": self.safety}
		)
		config.set("fields", [row for row in config.fields if row.fieldname != "inspector"])
		config.save()
		self.assertRaises(frappe.MandatoryError, doc.insert)

	def test_hidden_table_rows_are_not_mandatory(self):
		self.configure(
			"AFB-A", {"permit_number": {"enabled": 0}, "contractor": {"enabled": 0}, "items": {"enabled": 0}}
		)
		doc = self.inspection("AFB-A", items=[{"item": None}])
		doc.insert()
		self.configure(
			"AFB-B",
			{
				"permit_number": {"enabled": 0},
				"contractor": {"enabled": 0},
				"items": {"enabled": 1, "mandatory": 1},
			},
		)
		self.assertRaises(frappe.MandatoryError, self.inspection("AFB-B", items=[{"item": None}]).insert)

	def test_hidden_value_is_preserved_and_snapshot_freezes_configuration(self):
		self.configure("AFB-A", {"permit_number": {"enabled": 1}, "contractor": {"enabled": 1}})
		doc = self.inspection("AFB-A", permit_number="PTW-9", contractor="ABC Trading").insert()
		snapshot = json.loads(doc.ai_form_configuration_snapshot)
		self.assertTrue(snapshot["contractor"]["enabled"])
		self.configure("AFB-A", {"contractor": {"enabled": 0}})
		doc.reload()
		doc.finding = "Edited later"
		doc.save()
		self.assertEqual(frappe.db.get_value(SAFETY, doc.name, "contractor"), "ABC Trading")
		self.assertEqual(json.loads(doc.ai_form_configuration_snapshot), snapshot)
		runtime = project_configuration.get_runtime_configuration(self.safety, document_name=doc.name)
		self.assertTrue(runtime["fields"]["contractor"]["enabled"])
		fresh = project_configuration.get_runtime_configuration(
			self.safety, document=json.dumps({"project": "AFB-A"})
		)
		self.assertFalse(fresh["fields"]["contractor"]["enabled"])

	def test_project_read_only_is_enforced_server_side(self):
		self.configure(
			"AFB-A",
			{"permit_number": {"enabled": 0}, "contractor": {"enabled": 0}, "area_name": {"read_only": 1}},
		)
		doc = self.inspection("AFB-A", area_name="Zone 1").insert()
		doc.area_name = "Zone 2"
		self.assertRaises(frappe.PermissionError, doc.save)
		doc.reload()
		doc.finding = "Allowed"
		doc.save()

	def test_form_must_be_enabled_for_the_project(self):
		self.configure("AFB-C", enabled=0)
		self.assertRaises(frappe.ValidationError, self.inspection("AFB-C").insert)

	def test_reusable_profile_with_project_override(self):
		profile = frappe.get_doc(
			{"doctype": "AI Form Field Profile", "profile_name": "Basic", "form_template": self.safety}
		).insert()
		self.assertTrue(any(row.fieldname == "contractor" for row in profile.fields))
		for row in profile.fields:
			if row.fieldname in ("permit_number", "contractor"):
				row.enabled = 0
		profile.save()
		config = self.configure(
			"AFB-C", profile=profile.name, fields={"contractor": {"enabled": 1, "mandatory": 1}}
		)
		self.assertEqual([row.fieldname for row in config.fields], ["contractor"])
		rules = configuration_dict(config)
		self.assertFalse(rules["permit_number"]["enabled"])
		self.assertTrue(rules["contractor"]["mandatory"])
		self.assertRaises(frappe.MandatoryError, self.inspection("AFB-C").insert)
		self.inspection("AFB-C", contractor="ACME").insert()
		payload = project_configuration.get_form_configuration(PROJECT, "AFB-C", self.safety)
		self.assertEqual(
			len(payload["fields"]), len(template_rows(frappe.get_doc("AI Form Template", self.safety)))
		)
		contractor = next(row for row in payload["fields"] if row["fieldname"] == "contractor")
		self.assertEqual((contractor["enabled"], contractor["mandatory"]), (1, 1))
		self.assertEqual(payload["profiles"][0]["name"], profile.name)


class TestRevisions(FormLibraryTestCase):
	def test_revision_lifecycle_keeps_history(self):
		self.configure("AFB-A", {"permit_number": {"enabled": 0}, "contractor": {"enabled": 0}})
		forms_api.publish(self.safety)
		old_record = self.inspection("AFB-A").insert()
		self.assertRaises(frappe.ValidationError, template_api.save_mapping, self.safety, "[]")
		revision = forms_api.create_revision(self.safety)
		self.assertEqual(revision, "AFB-T-SI-REV-2")
		rev = frappe.get_doc("AI Form Template", revision)
		self.assertEqual(
			(rev.status, rev.generated_doctype, rev.template_code), ("Draft", SAFETY, "AFB-T-SI")
		)
		self.assertRaises(frappe.ValidationError, forms_api.create_revision, self.safety)
		forms_api.publish(revision)
		self.assertEqual(frappe.db.get_value("AI Form Template", self.safety, "status"), "Superseded")
		config = frappe.db.get_value(
			"AI Project Form Configuration", {"reference_name": "AFB-A"}, "form_template"
		)
		self.assertEqual(config, revision)
		new_record = self.inspection("AFB-A").insert()
		self.assertEqual(new_record.ai_form_template, revision)
		old_record.reload()
		self.assertEqual(old_record.ai_form_template, self.safety)
		old_record.finding = "still editable"
		old_record.save()
		self.assertEqual(len(frappe.get_all("DocType", filters={"name": ["like", f"{SAFETY}%"]})), 1)


class TestPdfAndAiRegression(FormLibraryTestCase):
	def test_existing_ai_workflow_end_to_end(self):
		"""Upload → analyse (AcroForm, no AI call) → review → approve → generate → record → PDF."""
		url = _pdf_url("afb-ai-form", with_widget=True)
		template = frappe.get_doc(
			{
				"doctype": "AI Form Template",
				"template_title": "AFB Test AI Form",
				"template_code": "AFB-T-AI",
				"source_pdf": url,
			}
		).insert()
		self.assertEqual(template.status, "Uploaded")
		self.assertEqual(template.number_of_pages, 1)
		with patch("ai_form_builder.services.template_service.OpenAIProvider") as provider:
			analyze_template(template.name)
			provider.assert_not_called()
		fields = template_api.get_template_fields(template.name)
		self.assertEqual(fields[0]["fieldname"], "inspector_name")
		template_api.approve_mapping(template.name)
		self.assertEqual(generate_doctype(template.name, "AFB Test AI Form"), "AFB Test AI Form")
		record = frappe.get_doc({"doctype": "AFB Test AI Form", "inspector_name": "Jane Inspector"}).insert()
		self.assertEqual(record.ai_form_template, template.name)
		file_url = generate_pdf(template.name, "AFB Test AI Form", record.name)
		content = _pdf_bytes(file_url)
		with fitz.open(stream=content, filetype="pdf") as pdf:
			self.assertIn("Jane Inspector", pdf[0].get_text())
		# AI form + Frappe no-code: add a field with Frappe, sync, mapping intact.
		_add_fields("AFB Test AI Form", [{"fieldname": "remarks", "label": "Remarks", "fieldtype": "Data"}])
		self.assertEqual(forms_api.sync_fields(template.name)["added"], ["remarks"])
		mapped = next(
			row
			for row in frappe.get_doc("AI Form Template", template.name).fields
			if row.fieldname == "inspector_name"
		)
		self.assertEqual((mapped.x, mapped.y, mapped.is_printable), (40, 100, 1))

	def test_manual_form_maps_an_attached_pdf_without_ai(self):
		created = manual_form.create_manual_form(
			template_title="AFB Test Mapped Form", template_code="AFB-T-MAP"
		)
		_add_fields(
			"AFB Test Mapped Form", [{"fieldname": "material", "label": "Material", "fieldtype": "Data"}]
		)
		forms_api.sync_fields(created["template"])
		template = frappe.get_doc("AI Form Template", created["template"])
		template.source_pdf = _pdf_url("afb-manual-form")
		template.save()
		self.assertEqual(template.number_of_pages, 1)
		rows = [row.as_dict() for row in template.fields]
		for row in rows:
			if row.fieldname == "material":
				row.update({"x": 40, "y": 200, "width": 200, "height": 20, "is_printable": 1})
		template_api.save_mapping(template.name, json.dumps(rows, default=str))
		bad = [
			*rows,
			{
				"fieldname": "not_in_doctype",
				"label": "X",
				"final_fieldtype": "Data",
				"page_number": 1,
				"x": 1,
				"y": 1,
				"width": 5,
				"height": 5,
			},
		]
		self.assertRaises(
			frappe.ValidationError, template_api.save_mapping, template.name, json.dumps(bad, default=str)
		)
		record = frappe.get_doc({"doctype": "AFB Test Mapped Form", "material": "Rebar B500"}).insert()
		content = _pdf_bytes(generate_pdf(template.name, "AFB Test Mapped Form", record.name))
		with fitz.open(stream=content, filetype="pdf") as pdf:
			self.assertIn("Rebar B500", pdf[0].get_text())


class TestPermissions(FormLibraryTestCase):
	def test_users_see_only_permitted_enabled_forms_and_cannot_administer(self):
		self.configure("AFB-A", {"permit_number": {"enabled": 0}, "contractor": {"enabled": 0}})
		user = frappe.get_doc(
			{"doctype": "User", "email": TEST_USER, "first_name": "AFB", "send_welcome_email": 0}
		).insert()
		user.add_roles("AI Form Builder User")
		frappe.set_user(TEST_USER)
		forms = forms_api.get_enabled_forms(PROJECT, "AFB-A")
		self.assertIn(SAFETY, [form["doctype"] for form in forms])
		self.assertRaises(
			frappe.PermissionError, manual_form.create_manual_form, "AFB Test Nope", "AFB-T-NOPE"
		)
		self.assertRaises(frappe.PermissionError, forms_api.publish, self.safety)
		self.assertRaises(
			frappe.PermissionError, project_configuration.set_form_enabled, PROJECT, "AFB-A", self.safety, 0
		)
		doc = self.inspection("AFB-A").insert()
		self.assertEqual(doc.owner, TEST_USER)
		frappe.set_user("Administrator")
		user.remove_roles("AI Form Builder User")
		frappe.set_user(TEST_USER)
		self.assertRaises(frappe.PermissionError, forms_api.get_enabled_forms, PROJECT, "AFB-A")


class TestDocuflowAdapter(FormLibraryTestCase):
	def test_adapter_is_inert_without_docuflow(self):
		with patch.object(frappe, "get_installed_apps", return_value=["frappe", "ai_form_builder"]):
			self.assertFalse(docuflow.is_installed())
			self.assertIsNone(docuflow.get_project_doctype())
			self.assertEqual(docuflow.get_default_context(), (None, None))
			self.assertIsNone(docuflow.get_active_project())
			self.assertEqual(docuflow.get_project_forms("ANY"), [])
			self.assertFalse(docuflow.get_context()["installed"])
			self.assertEqual(form_registry.default_reference(), (None, None))

	def test_adapter_resolves_docuflow_project_when_present(self):
		with (
			patch.object(
				frappe, "get_installed_apps", return_value=["frappe", "docuflow", "ai_form_builder"]
			),
			patch.object(
				frappe.db,
				"exists",
				side_effect=lambda doctype, name=None, *args, **kwargs: (doctype, name)
				== ("DocType", "DCMS Project")
				or None,
			),
		):
			self.assertEqual(docuflow.get_project_doctype(), "DCMS Project")
			self.assertEqual(docuflow.get_default_context(), ("DCMS Project", "project"))

	def test_settings_override_adapter_default(self):
		settings = frappe.get_single("AI Form Builder Settings")
		settings.default_reference_doctype = PROJECT
		settings.default_reference_fieldname = "project"
		settings.save()
		try:
			self.assertEqual(form_registry.default_reference(), (PROJECT, "project"))
		finally:
			settings.default_reference_doctype = None
			settings.save()


class TestDocuflowPanel(FormLibraryTestCase):
	"""The Form Library panel added to Docuflow's /d app from this app."""

	def _response(self, path, html="<html><body><div id=app></div></body></html>"):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request, Response

		request = Request(EnvironBuilder(path=path, method="GET").get_environ())
		return request, Response(html, mimetype="text/html")

	def test_bridge_is_added_only_to_docuflow_pages_for_logged_in_users(self):
		with patch.object(docuflow, "is_installed", return_value=True):
			request, response = self._response("/d/quality")
			docuflow.inject_bridge(response=response, request=request)
			html = response.get_data(as_text=True)
			self.assertIn(docuflow.BRIDGE_JS, html)
			self.assertEqual(html.count(docuflow.BRIDGE_JS), 1)
			docuflow.inject_bridge(response=response, request=request)
			self.assertEqual(response.get_data(as_text=True).count(docuflow.BRIDGE_JS), 1)
			for path in ("/app/todo", "/dashboard", "/data"):
				request, response = self._response(path)
				docuflow.inject_bridge(response=response, request=request)
				self.assertNotIn(docuflow.BRIDGE_JS, response.get_data(as_text=True), path)
			frappe.set_user("Guest")
			request, response = self._response("/d")
			docuflow.inject_bridge(response=response, request=request)
			self.assertNotIn(docuflow.BRIDGE_JS, response.get_data(as_text=True))
		frappe.set_user("Administrator")
		with patch.object(docuflow, "is_installed", return_value=False):
			request, response = self._response("/d/hse")
			docuflow.inject_bridge(response=response, request=request)
			self.assertNotIn(docuflow.BRIDGE_JS, response.get_data(as_text=True))

	def test_areas_switch_the_panel_on_by_configuration(self):
		for name in ("Quality", "HSE"):
			area = frappe.get_doc("AI Form Area", name)
			area.update(
				{
					"external_app": "docuflow",
					"show_in_external_app": 1,
					"external_route_prefixes": f"/d/{name.lower()}",
				}
			)
			area.save()
		frappe.get_doc(
			{
				"doctype": "AI Form Area",
				"area_name": "AFB Test Engineering",
				"external_app": "docuflow",
				"show_in_external_app": 1,
				"external_route_prefixes": "/d/project-controls\n/d/quality/submittals/",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "AI Form Group",
				"group_name": "AFB Test Civil",
				"target_area": "AFB Test Engineering",
			}
		).insert()
		with (
			patch.object(docuflow, "get_project_doctype", return_value=PROJECT),
			patch.object(docuflow, "get_active_project", return_value="AFB-A"),
		):
			config = docuflow.get_bridge_config()
		areas = {area["name"]: area["prefixes"] for area in config["areas"]}
		self.assertEqual(areas["Quality"], ["/d/quality"])
		self.assertEqual(areas["AFB Test Engineering"], ["/d/project-controls", "/d/quality/submittals"])
		self.assertTrue(config["can_manage"])
		self.assertEqual(config["active_project"], "AFB-A")
		self.assertIn(
			("AFB Test Civil", "AFB Test Engineering"),
			[(g["name"], g["target_area"]) for g in config["groups"]],
		)
		frappe.db.set_value("AI Form Area", "AFB Test Engineering", "show_in_external_app", 0)
		with patch.object(docuflow, "get_project_doctype", return_value=PROJECT):
			self.assertNotIn(
				"AFB Test Engineering", [area["name"] for area in docuflow.get_bridge_config()["areas"]]
			)

	def test_area_forms_for_managers_and_users(self):
		frappe.db.set_value(
			"AI Form Area",
			"HSE",
			{"external_app": "docuflow", "show_in_external_app": 1, "external_route_prefixes": "/d/hse"},
		)
		self.configure("AFB-A", {"permit_number": {"enabled": 0}, "contractor": {"enabled": 0}})
		with patch.object(docuflow, "get_project_doctype", return_value=PROJECT):
			managed = docuflow.get_area_forms("HSE", "AFB-A")["forms"]
			safety = next(form for form in managed if form["doctype"] == SAFETY)
			self.assertTrue(safety["enabled"])
			self.assertEqual(safety["edit_url"], f"/app/doctype/{SAFETY.replace(' ', '%20')}")
			self.assertEqual(safety["new_url"], "/app/afb-test-safety-inspection/new?project=AFB-A")
			self.assertIn("reference_name=AFB-A", safety["configure_url"])
			other = docuflow.get_area_forms("HSE", "AFB-B")["forms"]
			self.assertFalse(next(form for form in other if form["doctype"] == SAFETY)["enabled"])
			self.assertRaises(frappe.ValidationError, docuflow.get_area_forms, "Not An Area", "AFB-A")

			user = frappe.get_doc(
				{"doctype": "User", "email": TEST_USER, "first_name": "AFB", "send_welcome_email": 0}
			).insert()
			user.add_roles("AI Form Builder User")
			frappe.set_user(TEST_USER)
			self.assertFalse(docuflow.get_bridge_config()["can_manage"])
			forms = docuflow.get_area_forms("HSE", "AFB-A")["forms"]
			self.assertEqual([form["doctype"] for form in forms], [SAFETY])
			self.assertNotIn("edit_url", forms[0])
			self.assertEqual(docuflow.get_area_forms("HSE", "AFB-B")["forms"], [])

	def test_ai_upload_from_the_panel_files_the_form_under_its_area(self):
		settings = frappe.get_single("AI Form Builder Settings")
		settings.default_reference_doctype = PROJECT
		settings.save()
		try:
			created = template_api.create_template_from_upload(
				"AFB Test AI Panel",
				"AFB-T-AIP",
				_pdf_url("afb-panel"),
				target_area="Quality",
				form_group="QC",
				enable_project_configuration=1,
			)
			template = frappe.get_doc("AI Form Template", created["name"])
			self.assertEqual(
				(template.target_area, template.form_group, template.status), ("Quality", "QC", "Uploaded")
			)
			self.assertEqual((template.reference_doctype, template.reference_fieldname), (PROJECT, "project"))
		finally:
			settings.default_reference_doctype = None
			settings.save()

	def test_manual_form_starts_with_project_first_and_system_tab_last(self):
		fields = [f.fieldname for f in frappe.get_meta(SAFETY).fields]
		self.assertEqual(fields[:2], ["project", "attachment"])
		self.assertLess(fields.index("ai_form_system_tab"), fields.index("ai_form_template"))
		self.assertEqual(frappe.get_meta(SAFETY).get_field("project").label, "Project")
