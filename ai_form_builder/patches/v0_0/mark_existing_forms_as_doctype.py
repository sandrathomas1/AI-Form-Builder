import frappe


def execute():
	"""Forms made before spec forms existed keep their DocType behaviour.

	The new storage_mode column defaults to Spec; every template that already
	has a DocType, or was analysed into DocType-style field mappings, is a
	DocType form.
	"""
	frappe.db.sql(
		"""
		update `tabAI Form Template`
		set storage_mode = 'DocType'
		where ifnull(spec_json, '') = ''
		  and (ifnull(generated_doctype, '') != ''
		       or ifnull(target_doctype, '') != ''
		       or source_type in ('Manual', 'Existing DocType')
		       or ifnull(analysis_json, '') != ''
		       or status != 'Uploaded')
		"""
	)
