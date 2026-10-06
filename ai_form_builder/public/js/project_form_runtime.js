window.ai_form_builder = window.ai_form_builder || {};
ai_form_builder.project_form = {
	setup(frm) {
		Object.keys(frm.doc).forEach(fieldname => frm.on(fieldname, () => this.apply_configuration(frm)));
	},
	apply_configuration(frm) {
		if (!frm.doc.ai_form_template) return;
		frappe.call({
			method: "ai_form_builder.api.project_configuration.get_runtime_configuration",
			args: {form_template: frm.doc.ai_form_template, document: frm.doc, document_name: frm.is_new() ? null : frm.doc.name},
			quiet: true,
			callback: ({message}) => {
				if (!message) return;
				if (!message.enabled) {
					frm.disable_save();
					frappe.msgprint(__("This form is not enabled for the selected project."));
					return;
				}
				Object.entries(message.fields || {}).forEach(([fieldname, rules]) => {
					frm.set_df_property(fieldname, "hidden", !rules.enabled);
					frm.set_df_property(fieldname, "reqd", !!(rules.enabled && rules.mandatory));
					frm.set_df_property(fieldname, "read_only", !!rules.read_only);
					if (rules.label_override) frm.set_df_property(fieldname, "label", rules.label_override);
					frm.refresh_field(fieldname);
				});
			},
		});
	},
	on_reference_change(frm) { this.apply_configuration(frm); },
};
