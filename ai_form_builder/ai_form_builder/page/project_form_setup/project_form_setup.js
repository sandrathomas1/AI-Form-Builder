frappe.pages["project-form-setup"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Project Form Setup"), single_column: true });
	const options = frappe.route_options || {};
	frappe.route_options = null;
	const type = page.add_field({ label: __("Project Type"), fieldtype: "Link", options: "DocType", fieldname: "reference_doctype", change: load });
	const reference = page.add_field({ label: __("Project"), fieldtype: "Dynamic Link", options: "reference_doctype", fieldname: "reference_name", change: load });
	const body = $("<div class='project-form-setup' style='padding: var(--padding-md) 0'></div>").appendTo(page.body);
	const esc = frappe.utils.escape_html;

	frappe.call("ai_form_builder.api.forms.get_new_form_defaults").then(({ message }) => {
		type.set_value(options.reference_doctype || message.reference_doctype || "");
		if (options.reference_name) return reference.set_value(options.reference_name);
		if (message.docuflow_installed) {
			frappe.call("ai_form_builder.integrations.docuflow.get_context").then(({ message: context }) => {
				if (context.active_project) reference.set_value(context.active_project);
			});
		}
	});

	function load() {
		if (!type.get_value() || !reference.get_value()) return body.html(`<p class="text-muted">${__("Choose a project to set up its forms.")}</p>`);
		frappe.call({
			method: "ai_form_builder.api.project_configuration.get_project_forms",
			args: { reference_doctype: type.get_value(), reference_name: reference.get_value() },
		}).then(({ message }) => render(message || []));
	}

	function render(forms) {
		body.empty();
		if (!forms.length) {
			body.html(`<p class="text-muted">${__("No project-configurable forms are published for this project type yet.")}</p>`);
			return;
		}
		let area = null, group = null;
		forms.forEach((form) => {
			if (form.area !== area) {
				area = form.area;
				group = null;
				body.append(`<h4 style="margin-top: var(--margin-lg)">${esc(area || __("No Area"))}</h4>`);
			}
			if (form.group !== group) {
				group = form.group;
				body.append(`<h6 class="text-muted" style="margin: var(--margin-md) 0 var(--margin-xs)">${esc(group)}</h6>`);
			}
			const row = $(`
				<div class="flex align-center justify-between" style="padding: var(--padding-xs) 0; border-bottom: 1px solid var(--border-color)">
					<label class="flex align-center" style="gap: var(--margin-sm); margin: 0">
						<input type="checkbox" ${form.enabled ? "checked" : ""}>
						<span>${esc(form.template_title)}</span>
						<span class="text-muted small">${esc(form.template_code || "")}</span>
					</label>
					<span class="flex align-center" style="gap: var(--margin-sm)">
						<span class="text-muted small">${form.enabled ? esc(__("Profile: {0}", [form.field_profile ? form.field_profile.split(" - ").pop() : __("Project fields")])) : ""}</span>
						<button class="btn btn-xs btn-default" ${form.enabled ? "" : "disabled"}>${__("Configure")}</button>
					</span>
				</div>`).appendTo(body);
			row.find("input").on("change", (event) =>
				frappe.call({
					method: "ai_form_builder.api.project_configuration.set_form_enabled",
					args: { reference_doctype: type.get_value(), reference_name: reference.get_value(), form_template: form.name, enabled: event.target.checked ? 1 : 0 },
				}).then(load)
			);
			row.find("button").on("click", () => configure(form));
		});
	}

	function configure(form) {
		frappe.call({
			method: "ai_form_builder.api.project_configuration.get_form_configuration",
			args: { reference_doctype: type.get_value(), reference_name: reference.get_value(), form_template: form.name },
		}).then(({ message }) => edit_fields(form, message));
	}

	function edit_fields(form, doc) {
		const master = doc.fields.map((row) => Object.assign({}, row));
		const dialog = new frappe.ui.Dialog({
			title: `${form.template_title} · ${reference.get_value()}`,
			size: "large",
			fields: [
				{ fieldname: "field_profile", label: __("Field Profile"), fieldtype: "Select",
					options: [""].concat((doc.profiles || []).map((p) => p.name)).join("\n"), default: doc.field_profile || "",
					description: __("Shared settings for this form. Changes below are saved as this project's own overrides."),
					change: () => apply_profile(dialog.get_value("field_profile")) },
				{ fieldname: "fields", fieldtype: "Table", label: __("Fields"), cannot_add_rows: true, cannot_delete_rows: true, in_place_edit: true, data: doc.fields,
					fields: [
						{ fieldname: "field_label", label: __("Field"), fieldtype: "Data", read_only: 1, in_list_view: 1, columns: 3 },
						{ fieldname: "enabled", label: __("Show"), fieldtype: "Check", in_list_view: 1, columns: 1 },
						{ fieldname: "mandatory", label: __("Required"), fieldtype: "Check", in_list_view: 1, columns: 1 },
						{ fieldname: "read_only", label: __("Read Only"), fieldtype: "Check", in_list_view: 1, columns: 1 },
						{ fieldname: "label_override", label: __("Project Label"), fieldtype: "Data", in_list_view: 1, columns: 3 },
						{ fieldname: "fieldname", label: __("Fieldname"), fieldtype: "Data", read_only: 1, hidden: 1 },
					] },
			],
			primary_action_label: __("Save"),
			primary_action(values) {
				doc.field_profile = values.field_profile || null;
				doc.fields = grid().get_data().map(({ fieldname, field_label, enabled, mandatory, read_only, label_override }) =>
					({ fieldname, field_label, enabled, mandatory: enabled ? mandatory : 0, read_only, label_override }));
				delete doc.profiles;
				frappe.call({ method: "ai_form_builder.api.project_configuration.save_form_configuration", args: { configuration: doc }, freeze: true })
					.then(() => { dialog.hide(); load(); });
			},
		});
		const grid = () => dialog.fields_dict.fields.grid;
		const set_rows = (rows) => { grid().df.data = rows; grid().refresh(); };
		function apply_profile(profile) {
			if (!profile) return set_rows(master.map((row) => Object.assign({}, row)));
			frappe.db.get_doc("AI Form Field Profile", profile).then((p) => {
				const rules = Object.fromEntries(p.fields.map((row) => [row.fieldname, row]));
				set_rows(master.map((row) => {
					const rule = rules[row.fieldname];
					return rule ? Object.assign({}, row, { enabled: rule.enabled, mandatory: rule.mandatory, read_only: rule.read_only, label_override: rule.label_override }) : Object.assign({}, row);
				}));
			});
		}
		dialog.add_custom_action(__("Select All"), () => { grid().get_data().forEach((row) => (row.enabled = 1)); grid().refresh(); });
		dialog.add_custom_action(__("Reset to Master"), () => {
			if (!doc.name) return frappe.show_alert({ message: __("Save this configuration before resetting it."), indicator: "orange" });
			frappe.confirm(__("Reset every field setting to the master form? Saved document values are not changed."), () =>
				frappe.call({ method: "ai_form_builder.api.project_configuration.reset_configuration_to_master", args: { configuration_name: doc.name } })
					.then(({ message }) => {
						Object.assign(doc, message);
						master.splice(0, master.length, ...message.fields.map((row) => Object.assign({}, row)));
						// Clearing the profile re-renders the grid from the reset master rows.
						dialog.set_value("field_profile", "").then(() => set_rows(message.fields));
					}));
		});
		dialog.show();
	}
};
