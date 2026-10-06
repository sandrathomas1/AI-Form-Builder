frappe.ui.form.on("AI Project Form Configuration", {
	form_template(frm) {
		if (!frm.doc.reference_doctype || !frm.doc.reference_name || !frm.doc.form_template) return;
		frappe.call({method: "ai_form_builder.api.project_configuration.get_form_configuration", args: {reference_doctype: frm.doc.reference_doctype, reference_name: frm.doc.reference_name, form_template: frm.doc.form_template}, callback: r => {
			if (!frm.doc.fields?.length) frm.set_value("fields", r.message.fields);
			if (!frm.doc.generated_doctype) frm.set_value("generated_doctype", r.message.generated_doctype);
		}});
	},
	refresh(frm) {
		if (!frm.is_new()) frm.add_custom_button(__("Sync Fields From Template"), () => frappe.call({method: "ai_form_builder.api.project_configuration.sync_configuration_fields", args: {configuration_name: frm.doc.name}, freeze: true, callback: () => frm.reload_doc()}));
	},
});
