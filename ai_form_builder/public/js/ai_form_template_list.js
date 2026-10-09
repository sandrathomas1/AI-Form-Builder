// Form Library list: one "New Form" entry for all three ways of creating a form.
frappe.provide("ai_form_builder.library");

ai_form_builder.library.classification_fields = (get_dialog) => [
	{ fieldname: "target_area", label: __("Target Area"), fieldtype: "Link", options: "AI Form Area",
		get_query: () => ({ filters: { enabled: 1 } }) },
	{ fieldname: "form_group", label: __("Group / Subgroup"), fieldtype: "Link", options: "AI Form Group",
		get_query() {
			const area = get_dialog()?.get_value("target_area");
			return { filters: Object.assign({ enabled: 1 }, area ? { target_area: area } : {}) };
		} },
	{ fieldname: "description", label: __("Description"), fieldtype: "Small Text" },
];

ai_form_builder.library.context_fields = (defaults) => [
	{ fieldname: "enable_project_configuration", label: __("Project Configurable"), fieldtype: "Check",
		description: __("Projects choose whether to use this form and which fields they show.") },
	{ fieldname: "reference_doctype", label: __("Project DocType"), fieldtype: "Link", options: "DocType",
		default: defaults.reference_doctype, depends_on: "eval:doc.enable_project_configuration",
		mandatory_depends_on: "eval:doc.enable_project_configuration" },
	{ fieldname: "reference_fieldname", label: __("Project Fieldname"), fieldtype: "Data",
		default: defaults.reference_fieldname, depends_on: "eval:doc.enable_project_configuration" },
];

ai_form_builder.library.open_route = ({ route, route_options }) => {
	if (route_options) frappe.route_options = route_options;
	frappe.set_route(...route);
};

ai_form_builder.library.new_form = () => {
	const chooser = new frappe.ui.Dialog({
		title: __("Create New Form"),
		fields: [{ fieldname: "choices", fieldtype: "HTML" }],
	});
	const choices = [
		["ai", __("Create with AI from PDF"), __("Upload the client PDF; AI detects sections and fields for review.")],
		["manual", __("Create Manually with Frappe"), __("Name the form, then add fields with Frappe's form builder. No AI needed.")],
		["existing", __("Use Existing DocType"), __("Put a DocType that already exists into the Form Library.")],
	];
	chooser.fields_dict.choices.$wrapper.html(
		choices.map(([key, label, help]) => `
			<button class="btn btn-default btn-block text-left afb-choice" data-choice="${key}" style="white-space: normal; margin-bottom: var(--margin-sm)">
				<div class="bold">${label}</div><div class="text-muted small">${help}</div>
			</button>`).join("")
	);
	chooser.$wrapper.on("click", ".afb-choice", (event) => {
		const choice = $(event.currentTarget).data("choice");
		chooser.hide();
		if (choice === "ai") return frappe.new_doc("AI Form Template", { source_type: "AI PDF" });
		frappe.call("ai_form_builder.api.forms.get_new_form_defaults").then(({ message }) =>
			choice === "manual" ? ai_form_builder.library.manual_wizard(message) : ai_form_builder.library.existing_wizard(message)
		);
	});
	chooser.show();
};

ai_form_builder.library.manual_wizard = (defaults) => {
	const dialog = new frappe.ui.Dialog({
		title: __("Create Manually"),
		fields: [
			{ fieldname: "template_title", label: __("Form Name"), fieldtype: "Data", reqd: 1,
				description: __("Also the name of the new Frappe DocType.") },
			{ fieldname: "template_code", label: __("Form Code"), fieldtype: "Data", reqd: 1 },
			...ai_form_builder.library.classification_fields(() => dialog),
			{ fieldtype: "Section Break" },
			{ fieldname: "is_submittable", label: __("Is Submittable"), fieldtype: "Check" },
			{ fieldname: "allow_attachments", label: __("Allow Attachments"), fieldtype: "Check", default: 1,
				description: __("Adds an Attachment field.") },
			...ai_form_builder.library.context_fields(defaults),
		],
		primary_action_label: __("Create Form"),
		primary_action(values) {
			frappe.call({ method: "ai_form_builder.api.manual_form.create_manual_form", args: values, freeze: true })
				.then(({ message }) => {
					dialog.hide();
					frappe.show_alert({ message: __("Form created. Add its fields, save, then use Sync Fields."), indicator: "green" });
					ai_form_builder.library.open_route(message);
				});
		},
	});
	dialog.show();
};

ai_form_builder.library.existing_wizard = (defaults) => {
	const dialog = new frappe.ui.Dialog({
		title: __("Use Existing DocType"),
		fields: [
			{ fieldname: "doctype", label: __("Document Type"), fieldtype: "Link", options: "DocType", reqd: 1,
				get_query: () => ({ filters: { istable: 0, issingle: 0 } }),
				change() {
					const value = dialog.get_value("doctype");
					if (value && !dialog.get_value("template_title")) dialog.set_value("template_title", value);
				} },
			{ fieldname: "template_title", label: __("Form Name"), fieldtype: "Data", reqd: 1 },
			{ fieldname: "template_code", label: __("Form Code"), fieldtype: "Data", reqd: 1 },
			...ai_form_builder.library.classification_fields(() => dialog),
			{ fieldtype: "Section Break" },
			...ai_form_builder.library.context_fields(defaults),
		],
		primary_action_label: __("Register Form"),
		primary_action(values) {
			frappe.call({ method: "ai_form_builder.api.forms.register_existing_doctype", args: values, freeze: true })
				.then(({ message }) => {
					dialog.hide();
					frappe.set_route("Form", "AI Form Template", message.template);
				});
		},
	});
	dialog.show();
};

frappe.listview_settings["AI Form Template"] = {
	add_fields: ["status", "source_type", "generated_doctype"],
	get_indicator(doc) {
		const colors = { Published: "green", Generated: "blue", Approved: "blue", Superseded: "gray",
			Disabled: "gray", "Analysis Failed": "red", "Review Required": "orange", Analyzing: "orange" };
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
	primary_action: () => ai_form_builder.library.new_form(),
	onload(listview) {
		listview.page.set_title(__("Forms"));
		// Frappe re-applies the primary action on refresh; keep it labelled "New Form".
		listview.set_primary_action = function () {
			if (this.can_create) this.page.set_primary_action(__("New Form"), () => ai_form_builder.library.new_form(), "add");
		};
		listview.set_primary_action();
	},
};
