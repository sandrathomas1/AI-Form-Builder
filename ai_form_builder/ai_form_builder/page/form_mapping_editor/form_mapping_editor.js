frappe.pages["form-mapping-editor"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({parent: wrapper, title: __("Form Mapping Editor"), single_column: true});
	const template_name = frappe.get_route()[1];
	if (!template_name) {
		frappe.msgprint(__("Open this page using Review Mapping from an AI Form Template."));
		return;
	}
	const state = {selected: null, fields: [], sections: []};
	page.set_primary_action(__("Save Mapping"), () => save_mapping());
	page.add_menu_item(__("Open Template"), () => frappe.set_route("Form", "AI Form Template", template_name));

	frappe.call({method: "ai_form_builder.page.form_mapping_editor.form_mapping_editor.get_context", args: {template_name}}).then(({message}) => {
		state.fields = message.fields;
		state.sections = message.sections;
		$(wrapper).html(`
			<div class="afbm-editor">
				<div class="afbm-preview"><iframe title="${frappe.utils.escape_html(message.title)}" src="${encodeURI(message.source_pdf)}#view=FitH"></iframe><div class="afbm-overlays"></div></div>
				<div class="afbm-sidebar"><div class="frappe-control"><button class="btn btn-sm btn-secondary afbm-add">${__("Add Field")}</button></div><div class="afbm-fields"></div><div class="afbm-properties"></div></div>
			</div>`);
		render();
	});

	function render() {
		const list = $(wrapper).find(".afbm-fields").empty();
		const overlays = $(wrapper).find(".afbm-overlays").empty();
		state.fields.forEach((field, index) => {
			const selected = state.selected === index ? "active" : "";
			$(`<button class="afbm-field ${selected}" data-index="${index}"><strong>${frappe.utils.escape_html(field.label || __("Unnamed field"))}</strong><small>${frappe.utils.escape_html(field.final_fieldtype || field.suggested_fieldtype || "Data")} · ${__("Page")} ${field.page_number}</small></button>`).appendTo(list);
			$(`<button aria-label="${frappe.utils.escape_html(field.label)}" class="afbm-rect ${selected}" data-index="${index}" style="left:${field.x}px;top:${field.y}px;width:${field.width}px;height:${field.height}px"></button>`).appendTo(overlays);
		});
		$(wrapper).find(".afbm-field,.afbm-rect").on("click", event => { state.selected = parseInt($(event.currentTarget).data("index"), 10); render(); });
		$(wrapper).find(".afbm-add").on("click", add_field);
		render_properties();
	}

	function render_properties() {
		const target = $(wrapper).find(".afbm-properties").empty();
		const field = state.fields[state.selected];
		if (!field) return target.html(`<p class="text-muted">${__("Select a detected field to edit it.")}</p>`);
		const controls = [
			["label", __("Label"), "Data"], ["fieldname", __("Fieldname"), "Data"], ["final_fieldtype", __("Type"), "Select"], ["options", __("Options (one per line)"), "Small Text"], ["page_number", __("Page"), "Int"],
			["x", "X", "Float"], ["y", "Y", "Float"], ["width", __("Width"), "Float"], ["height", __("Height"), "Float"], ["mandatory", __("Mandatory"), "Check"], ["is_printable", __("Printable"), "Check"], ["ignore_field", __("Ignore"), "Check"]
		];
		controls.forEach(([key, label, type]) => {
			const control = frappe.ui.form.make_control({parent: target, df: {fieldname: key, label, fieldtype: type, options: key === "final_fieldtype" ? "Data\nSmall Text\nText\nLong Text\nDate\nDatetime\nTime\nInt\nFloat\nCurrency\nPercent\nSelect\nCheck\nLink\nSignature\nAttach\nAttach Image" : null}, render_input: true});
			control.set_value(field[key]); control.$input.on("change", () => { field[key] = control.get_value(); render(); });
		});
	}

	function add_field() {
		state.fields.push({label: __("New Field"), fieldname: "new_field", final_fieldtype: "Data", page_number: 1, x: 40, y: 40, width: 160, height: 20, is_printable: 1, horizontal_alignment: "Left", vertical_alignment: "Middle", overflow_strategy: "Wrap Then Shrink"});
		state.selected = state.fields.length - 1; render();
	}

	function save_mapping() {
		frappe.call({method: "ai_form_builder.api.template.save_mapping", args: {template_name, fields: state.fields, sections: state.sections}, freeze: true, freeze_message: __("Saving mapping")}).then(() => frappe.show_alert({message: __("Mapping saved"), indicator: "green"}));
	}
};
