// One entry page for every spec form: the form is drawn from its spec at
// runtime, so a new form never needs a DocType or any code.
//   /app/afb-form/<record>                         open a record
//   /app/afb-form?template=<form>&reference_name=  start a new record
frappe.pages["afb-form"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Form"), single_column: true });
	wrapper.afb = { page, groups: [], state: null };
	$(wrapper).find(".layout-main-section").addClass("afb-entry");
};

frappe.pages["afb-form"].on_page_show = function (wrapper) {
	const name = frappe.get_route()[1];
	const query = frappe.utils.get_query_params();
	const options = frappe.route_options || {};
	frappe.route_options = null;
	const args = name
		? { name }
		: { form_template: query.template || options.template, reference_name: query.reference_name || options.reference_name };
	if (!args.name && !args.form_template) {
		$(wrapper).find(".layout-main-section").html(`<p class="text-muted">${__("Open a form from the Form Library.")}</p>`);
		return;
	}
	frappe.call({ method: "ai_form_builder.api.records.get_form", args, freeze: true }).then(({ message }) => draw(wrapper, message));
};

const AFB_TYPES = {
	Data: "Data", Text: "Small Text", Int: "Int", Float: "Float", Date: "Date", Time: "Time",
	Datetime: "Datetime", Check: "Check", Select: "Select", Signature: "Signature",
};

function afb_df(field, rule, value, can_write) {
	const df = {
		fieldname: field.name,
		label: (rule && rule.label_override) || field.label || field.name,
		fieldtype: AFB_TYPES[field.type] || "Data",
		reqd: rule ? (rule.enabled && rule.mandatory ? 1 : 0) : field.mandatory ? 1 : 0,
		read_only: !can_write || (rule && rule.read_only) ? 1 : 0,
		default: value,
	};
	if (field.type === "Select") df.options = ["", ...(field.options || [])].join("\n");
	if (field.type === "Check") df.default = ["1", 1, true].includes(value) ? 1 : 0;
	return df;
}

function draw(wrapper, state) {
	const { page } = wrapper.afb;
	wrapper.afb.state = state;
	wrapper.afb.groups = [];
	const esc = frappe.utils.escape_html;
	page.set_title(state.title);
	page.set_indicator(__(state.status), { Draft: "orange", Completed: "green", Cancelled: "red" }[state.status] || "gray");
	page.clear_primary_action();
	page.clear_secondary_action();
	page.clear_menu();
	const main = $(wrapper).find(".layout-main-section").empty();
	const project = state.reference_name
		? `<span class="text-muted">${__("Project")}</span> <b>${esc(state.reference_name)}</b> · `
		: "";
	$(`<div class="afb-entry-head">${project}<span class="text-muted">${__("Form")}</span> ${esc(state.code || "")}
		${state.revision ? ` · ${__("Rev")} ${esc(state.revision)}` : ""}${state.name ? ` · <b>${esc(state.name)}</b>` : ""}</div>`).appendTo(main);

	// Record details card
	const head = new frappe.ui.FieldGroup({
		fields: [{ fieldname: "record_date", fieldtype: "Date", label: __("Record date"), default: state.record_date, read_only: state.can_write ? 0 : 1 }],
		body: $(`<div class="afb-card"></div>`).appendTo(main),
	});
	head.make();
	wrapper.afb.head = head;

	const fields = Object.fromEntries((state.spec.fields || []).map((f) => [f.name, f]));
	const grids = Object.fromEntries((state.spec.grids || []).map((g) => [g.name, g]));
	const rules = state.rules || {};
	for (const section of state.sections) {
		const dfs = [];
		for (const name of section.fields) {
			const rule = rules[name];
			if (rule && !rule.enabled) continue;
			dfs.push(afb_df(fields[name], rule, state.values[name], state.can_write));
		}
		for (const name of section.grids) {
			const grid = grids[name];
			const rule = rules[name];
			if (rule && !rule.enabled) continue;
			const fixed = (grid.fixed_rows || []).length;
			dfs.push({
				fieldname: name,
				label: (rule && rule.label_override) || grid.label,
				fieldtype: "Table",
				cannot_add_rows: !state.can_write || !grid.allow_add,
				cannot_delete_rows: !state.can_write,
				in_place_edit: true,
				read_only: state.can_write ? 0 : 1,
				description: fixed ? __("The first {0} rows are printed on the sheet; their printed text cannot be changed.", [fixed]) : "",
				data: (state.grids[name] || []).map((row) => ({ ...row })),
				fields: grid.columns.map((column) => ({
					...afb_df(column, null, undefined, state.can_write),
					in_list_view: 1,
					columns: Math.max(1, Math.min(4, Math.round((column.width || 10) / 12))),
				})),
			});
		}
		if (!dfs.length) continue;
		const card = $(`<div class="afb-card"><div class="afb-card-title">${esc(section.label)}</div></div>`).appendTo(main);
		const group = new frappe.ui.FieldGroup({ fields: dfs, body: $("<div>").appendTo(card) });
		group.make();
		wrapper.afb.groups.push({ group, section });
	}

	if (state.can_write) {
		page.set_primary_action(__("Save"), () => afb_save(wrapper, "Draft"));
		page.set_secondary_action(__("Complete"), () => afb_save(wrapper, "Completed"));
	}
	if (state.name) {
		page.add_menu_item(__("Download PDF"), () => afb_pdf(state.name));
		page.add_inner_button(__("Download PDF"), () => afb_pdf(state.name));
		page.add_menu_item(__("Open record"), () => frappe.set_route("Form", "AI Form Record", state.name));
	}
	page.add_menu_item(__("All records of this form"), () =>
		frappe.set_route("List", "AI Form Record", { form_template: state.form_template, ...(state.reference_name ? { reference_name: state.reference_name } : {}) })
	);
}

function afb_collect(wrapper) {
	const { state } = wrapper.afb;
	const values = {};
	const grids = {};
	for (const { group, section } of wrapper.afb.groups) {
		const data = group.get_values(true) || {};
		for (const name of section.fields) if (name in data) values[name] = data[name] ?? "";
		for (const name of section.grids) {
			if (!(name in data)) continue;
			const columns = (state.spec.grids.find((g) => g.name === name) || {}).columns || [];
			grids[name] = (data[name] || []).map((row) => Object.fromEntries(columns.map((c) => [c.name, row[c.name] ?? ""])));
		}
	}
	return { values, grids };
}

function afb_save(wrapper, status) {
	const { state } = wrapper.afb;
	const { values, grids } = afb_collect(wrapper);
	const data = {
		form_template: state.form_template,
		reference_name: state.reference_name,
		record_date: wrapper.afb.head.get_value("record_date"),
		status,
		values,
		grids,
	};
	frappe
		.call({ method: "ai_form_builder.api.records.save", args: { data, name: state.name }, freeze: true, freeze_message: __("Saving…") })
		.then(({ message }) => {
			frappe.show_alert({ message: status === "Completed" ? __("Completed") : __("Saved"), indicator: "green" });
			if (message !== state.name) frappe.set_route("afb-form", message);
			else frappe.pages["afb-form"].on_page_show(wrapper);
		});
}

function afb_pdf(name) {
	frappe
		.call({ method: "ai_form_builder.api.records.download_pdf", args: { name }, freeze: true, freeze_message: __("Printing…") })
		.then(({ message }) => message && window.open(message, "_blank"));
}
