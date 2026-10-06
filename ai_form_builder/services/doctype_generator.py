import json

import frappe
from frappe import _


class DocTypeGenerator:
	def generate(self, template, name: str):
		if frappe.db.exists("DocType", name):
			frappe.throw(_("DocType {0} already exists; it was not overwritten.").format(name))
		fields = []
		fields.extend(self._runtime_fields(template.name))
		for section in sorted(template.sections, key=lambda row: row.sequence or 0):
			fields.append(
				{
					"label": section.section_label,
					"fieldtype": "Section Break",
					"fieldname": frappe.scrub(section.section_key),
				}
			)
			for _column_index in range(max(0, (section.column_count or 1) - 1)):
				fields.append({"fieldtype": "Column Break"})
		for row in template.fields:
			if row.ignore_field or not row.final_fieldtype:
				continue
			field = {
				"label": row.label,
				"fieldname": row.fieldname,
				"fieldtype": row.final_fieldtype,
				# Mandatory rules are an overlay when a template is project configured.
				# Global reqd would reject a field hidden by one project before our hook.
				"reqd": 0 if template.enable_project_configuration else row.mandatory,
				"read_only": row.read_only,
				"hidden": row.hidden,
				"default": row.default_value,
				"description": row.description,
			}
			if row.final_fieldtype == "Select":
				field["options"] = row.options
			if row.final_fieldtype == "Link":
				field["options"] = row.link_target
			fields.append(field)
		self._add_reference_fields(template, fields)
		doctype = frappe.get_doc(
			{
				"doctype": "DocType",
				"name": name,
				"module": "AI Form Builder",
				"custom": 1,
				"is_submittable": 0,
				"fields": fields,
				"permissions": [
					{
						"role": "AI Form Builder User",
						"read": 1,
						"write": 1,
						"create": 1,
						"delete": 1,
						"print": 1,
						"email": 1,
					}
				],
			}
		)
		doctype.insert(ignore_permissions=False)
		self._ensure_client_script(doctype.name)
		frappe.clear_cache(doctype=name)
		return doctype.name

	def _runtime_fields(self, template_name):
		return [
			{"label": "AI Form Template", "fieldname": "ai_form_template", "fieldtype": "Link", "options": "AI Form Template", "hidden": 1, "read_only": 1, "default": template_name},
			{"label": "AI Project Form Configuration", "fieldname": "ai_form_project_configuration", "fieldtype": "Link", "options": "AI Project Form Configuration", "hidden": 1, "read_only": 1},
			{"label": "AI Form Configuration Snapshot", "fieldname": "ai_form_configuration_snapshot", "fieldtype": "Code", "options": "JSON", "hidden": 1, "read_only": 1},
		]

	def _add_reference_fields(self, template, fields):
		if not template.enable_project_configuration:
			return
		fieldnames = {field.get("fieldname") for field in fields}
		if template.reference_fieldname and template.reference_fieldname in fieldnames:
			return
		# A configured fieldname is honoured; otherwise a neutral reusable context pair is used.
		if template.reference_fieldname:
			fields.append({"label": "Reference", "fieldname": template.reference_fieldname, "fieldtype": "Link", "options": template.reference_doctype, "reqd": 0})
			return
		fields.extend([
			{"label": "Reference DocType", "fieldname": "ai_form_reference_doctype", "fieldtype": "Link", "options": "DocType", "hidden": 1, "read_only": 1, "default": template.reference_doctype},
			{"label": "Reference", "fieldname": "ai_form_reference_name", "fieldtype": "Dynamic Link", "options": "ai_form_reference_doctype"},
		])
		template.db_set("reference_fieldname", "ai_form_reference_name", update_modified=False)

	def _ensure_client_script(self, doctype_name):
		"""Generated forms contain only a tiny entrypoint; behaviour lives in one module."""
		if not frappe.db.exists("DocType", "Client Script"):
			return
		name = f"AI Form Builder Project Runtime - {doctype_name}"
		if frappe.db.exists("Client Script", name):
			return
		frappe.get_doc({
			"doctype": "Client Script", "name": name, "dt": doctype_name, "enabled": 1,
			"script": f"frappe.ui.form.on({json.dumps(doctype_name)}, {{setup(frm) {{ ai_form_builder.project_form.setup(frm); }}, refresh(frm) {{ ai_form_builder.project_form.apply_configuration(frm); }}}});",
		}).insert(ignore_permissions=True)
