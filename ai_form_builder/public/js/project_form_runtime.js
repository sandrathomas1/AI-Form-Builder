// One runtime for every AI Form Builder form. Each generated DocType carries only
// a two-line Client Script entrypoint; the project overlay is applied here.
// Hiding never clears a value: only display properties change.
window.ai_form_builder = window.ai_form_builder || {};
ai_form_builder.project_form = {
	_watched: {},
	setup(frm) {
		frm.__afb_original = {};
	},
	watch_reference(frm, fieldname) {
		const key = `${frm.doctype}:${fieldname}`;
		if (!fieldname || this._watched[key]) return;
		this._watched[key] = true;
		frappe.ui.form.on(frm.doctype, fieldname, (form) => this.apply_configuration(form));
	},
	remember(frm, fieldname) {
		frm.__afb_original = frm.__afb_original || {};
		if (frm.__afb_original[fieldname]) return;
		const df = frappe.meta.get_docfield(frm.doctype, fieldname, frm.doc.name) || {};
		frm.__afb_original[fieldname] = {
			hidden: df.hidden,
			reqd: df.reqd,
			read_only: df.read_only,
			label: df.label,
		};
	},
	restore(frm, keep) {
		Object.entries(frm.__afb_original || {}).forEach(([fieldname, props]) => {
			if (keep.has(fieldname)) return;
			Object.entries(props).forEach(([prop, value]) => frm.set_df_property(fieldname, prop, value));
		});
	},
	apply_configuration(frm) {
		if (!frm.doc.ai_form_template) return;
		frappe.call({
			method: "ai_form_builder.api.project_configuration.get_runtime_configuration",
			args: {
				form_template: frm.doc.ai_form_template,
				document: frm.doc,
				document_name: frm.is_new() ? null : frm.doc.name,
			},
			quiet: true,
			callback: ({ message }) => {
				if (!message) return;
				this.watch_reference(frm, message.reference_fieldname);
				this.add_pdf_button(frm, message);
				if (!message.enabled) {
					frm.disable_save();
					frappe.show_alert({
						message: __("This form is not enabled for the selected project."),
						indicator: "orange",
					});
					return;
				}
				frm.enable_save();
				const fields = message.fields || {};
				this.restore(frm, new Set(Object.keys(fields)));
				Object.entries(fields).forEach(([fieldname, rules]) => {
					if (!frm.fields_dict[fieldname]) return;
					this.remember(frm, fieldname);
					const original = frm.__afb_original[fieldname];
					frm.set_df_property(fieldname, "hidden", rules.enabled ? original.hidden : 1);
					frm.set_df_property(fieldname, "reqd", rules.enabled && rules.mandatory ? 1 : 0);
					frm.set_df_property(fieldname, "read_only", rules.read_only ? 1 : original.read_only);
					frm.set_df_property(fieldname, "label", rules.label_override || original.label);
				});
			},
		});
	},
	add_pdf_button(frm, message) {
		if (!message.has_pdf || frm.is_new() || frm.custom_buttons?.[__("Generate PDF")]) return;
		frm.add_custom_button(__("Generate PDF"), () =>
			frappe
				.call({
					method: "ai_form_builder.api.pdf.generate_pdf",
					args: {
						template_name: frm.doc.ai_form_template,
						doctype: frm.doctype,
						document_name: frm.doc.name,
					},
					freeze: true,
				})
				.then(({ message: url }) => {
					frm.reload_doc();
					if (url) window.open(url);
				})
		);
	},
	on_reference_change(frm) {
		this.apply_configuration(frm);
	},
};

