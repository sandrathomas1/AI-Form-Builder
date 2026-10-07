frappe.listview_settings["AI Form Template"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Create Manually"), () => {
			const dialog = new frappe.ui.Dialog({
				title: __("Create Manual Form"),
				fields: [
					{ fieldname: "template_title", label: __("Form Title"), fieldtype: "Data", reqd: 1 },
					{ fieldname: "template_code", label: __("Template Code"), fieldtype: "Data", reqd: 1 },
					{ fieldname: "form_group", label: __("Form Group"), fieldtype: "Link", options: "AI Form Group" },
					{ fieldname: "enable_project_configuration", label: __("Enable Project Configuration"), fieldtype: "Check" },
					{ fieldname: "reference_doctype", label: __("Reference DocType"), fieldtype: "Link", options: "DocType", depends_on: "eval:doc.enable_project_configuration" },
					{ fieldname: "reference_fieldname", label: __("Reference Fieldname"), fieldtype: "Data", depends_on: "eval:doc.enable_project_configuration" },
				],
				primary_action_label: __("Create and Edit with Frappe"),
				primary_action(values) {
					frappe.call({ method: "ai_form_builder.api.manual_form.create_manual_form", args: values, freeze: true }).then(({ message }) => {
						dialog.hide();
						frappe.set_route("Form", "DocType", message.doctype);
					});
				},
			});
			dialog.show();
		});
	},
};
