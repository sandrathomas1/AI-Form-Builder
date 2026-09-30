import frappe
from frappe import _


class DocTypeGenerator:
	def generate(self, template, name: str):
		if frappe.db.exists("DocType", name):
			frappe.throw(_("DocType {0} already exists; it was not overwritten.").format(name))
		fields = []
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
				"reqd": row.mandatory,
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
		frappe.clear_cache(doctype=name)
		return doctype.name
