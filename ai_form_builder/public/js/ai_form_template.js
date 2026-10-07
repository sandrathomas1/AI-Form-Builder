frappe.ui.form.on("AI Form Template", {
	refresh(frm) {
		if (!frm.is_new()) {
			if (frm.doc.source_type === "Manual") {
				frm.add_custom_button(__("Edit with Frappe"), () => frappe.set_route("Form", "DocType", frm.doc.generated_doctype));
				frm.add_custom_button(__("Sync Fields"), () => frappe.call({method: "ai_form_builder.api.manual_form.sync_manual_fields", args: {template_name: frm.doc.name}, callback: () => frm.reload_doc()}));
			} else {
				frm.add_custom_button(__("Review Mapping"), () => frappe.set_route("form-mapping-editor", frm.doc.name));
				frm.add_custom_button(__("Analyze PDF"), () => frappe.call({method: "ai_form_builder.api.template.analyze_template", args: {template_name: frm.doc.name}, callback: () => frm.reload_doc()}));
				frm.add_custom_button(__("Approve Mapping"), () => frappe.call({method: "ai_form_builder.api.template.approve_mapping", args: {template_name: frm.doc.name}, callback: () => frm.reload_doc()}));
				frm.add_custom_button(__("Generate DocType"), () => frappe.prompt({label: __("DocType Name"), fieldname: "doctype_name", fieldtype: "Data", reqd: 1, default: frm.doc.template_title}, values => frappe.call({method: "ai_form_builder.api.generator.generate_doctype", args: {template_name: frm.doc.name, doctype_name: values.doctype_name}, callback: () => frm.reload_doc()})));
			}
			if (frm.doc.enable_project_configuration) {
				frm.add_custom_button(__("Configure Project Usage"), () => frappe.set_route("project-form-setup"));
			}
		}
	}
});
