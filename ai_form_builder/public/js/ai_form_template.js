frappe.ui.form.on("AI Form Template", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Analyze PDF"), () => frappe.call({method: "ai_form_builder.api.template.analyze_template", args: {template_name: frm.doc.name}, callback: () => frm.reload_doc()}));
			frm.add_custom_button(__("Approve Mapping"), () => frappe.call({method: "ai_form_builder.api.template.approve_mapping", args: {template_name: frm.doc.name}, callback: () => frm.reload_doc()}));
			frm.add_custom_button(__("Generate DocType"), () => frappe.prompt({label: __("DocType Name"), fieldname: "doctype_name", fieldtype: "Data", reqd: 1, default: frm.doc.template_title}, values => frappe.call({method: "ai_form_builder.api.generator.generate_doctype", args: {template_name: frm.doc.name, doctype_name: values.doctype_name}, callback: () => frm.reload_doc()})));
		}
	}
});
