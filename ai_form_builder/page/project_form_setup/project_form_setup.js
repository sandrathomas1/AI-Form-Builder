frappe.pages["project-form-setup"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({parent: wrapper, title: __("Project Form Setup"), single_column: true});
	const type = page.add_field({label: __("Project Type"), fieldtype: "Link", options: "DocType", fieldname: "reference_doctype", default: "Project", change: load});
	const reference = page.add_field({label: __("Project"), fieldtype: "Dynamic Link", options: "reference_doctype", fieldname: "reference_name", change: load});
	const body = $("<div class='project-form-setup'></div>").appendTo(page.body);
	function load() {
		if (!type.get_value() || !reference.get_value()) return;
		frappe.call({method: "ai_form_builder.api.project_configuration.get_project_forms", args: {reference_doctype: type.get_value(), reference_name: reference.get_value()}, callback: r => {
			const groups = {};
			(r.message || []).forEach(form => (groups[form.group] = groups[form.group] || []).push(form));
			body.empty();
			Object.entries(groups).forEach(([group, forms]) => {
				body.append(`<h4>${frappe.utils.escape_html(group)}</h4>`);
				forms.forEach(form => body.append($(`<div class='list-row'><span>${form.enabled ? "☑" : "☐"} ${frappe.utils.escape_html(form.template_title)}</span><button class='btn btn-xs btn-default'>${__("Configure Fields")}</button></div>`).find("button").on("click", () => configure(form))));
			});
		}});
	}
	function configure(form) {
		frappe.call({method: "ai_form_builder.api.project_configuration.get_form_configuration", args: {reference_doctype: type.get_value(), reference_name: reference.get_value(), form_template: form.name}, callback: r => {
			const doc = r.message;
			frappe.prompt([{fieldname: "enabled", label: __("Enable this form"), fieldtype: "Check", default: doc.enabled}], values => { doc.enabled = values.enabled; edit_fields(doc); }, __("Form Configuration"), __("Configure Fields"));
		}});
	}
	function edit_fields(doc) {
		const dialog = new frappe.ui.Dialog({title: __("Configure Fields"), fields: [{fieldname: "fields", fieldtype: "Table", label: __("Fields"), cannot_add_rows: true, in_place_edit: true, data: doc.fields, fields: [
			{fieldname:"field_label", label:__("Field"), fieldtype:"Data", read_only:1, in_list_view:1}, {fieldname:"enabled", label:__("Show"), fieldtype:"Check", in_list_view:1}, {fieldname:"mandatory", label:__("Mandatory"), fieldtype:"Check", in_list_view:1}, {fieldname:"read_only", label:__("Read Only"), fieldtype:"Check", in_list_view:1}, {fieldname:"label_override", label:__("Label Override"), fieldtype:"Data", in_list_view:1}
		]}], primary_action_label: __("Save Configuration"), primary_action(values) { doc.fields = values.fields; frappe.call({method:"ai_form_builder.api.project_configuration.save_form_configuration", args:{configuration:doc}, callback: () => { dialog.hide(); load(); }}); }});
		dialog.add_custom_action(__("Select All"), () => { dialog.fields_dict.fields.grid.get_data().forEach(row => row.enabled = 1); dialog.fields_dict.fields.grid.refresh(); });
		dialog.add_custom_action(__("Reset to Master"), () => {
			if (!doc.name) { frappe.show_alert({message: __("Save this configuration before resetting it."), indicator: "orange"}); return; }
			frappe.confirm(__("Reset every field setting to the master form? This does not change saved document values."), () => frappe.call({method: "ai_form_builder.api.project_configuration.reset_configuration_to_master", args: {configuration_name: doc.name}, callback: r => { doc.fields = r.message.fields; dialog.fields_dict.fields.grid.df.data = doc.fields; dialog.fields_dict.fields.grid.refresh(); }}));
		});
		dialog.show();
	}
};
