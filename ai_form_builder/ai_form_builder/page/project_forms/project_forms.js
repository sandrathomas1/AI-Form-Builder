// Forms enabled for one project, as the current user may use them.
frappe.pages["project-forms"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Project Forms"), single_column: true });
	const options = frappe.route_options || {};
	frappe.route_options = null;
	const type = page.add_field({ label: __("Project Type"), fieldtype: "Link", options: "DocType", fieldname: "reference_doctype", change: load });
	const reference = page.add_field({ label: __("Project"), fieldtype: "Dynamic Link", options: "reference_doctype", fieldname: "reference_name", change: load });
	const body = $("<div style='padding: var(--padding-md) 0'></div>").appendTo(page.body);
	const esc = frappe.utils.escape_html;

	frappe.call("ai_form_builder.integrations.docuflow.get_context").then(({ message }) => {
		type.set_value(options.reference_doctype || message.reference_doctype || "");
		reference.set_value(options.reference_name || message.active_project || "");
	});

	function load() {
		if (!type.get_value() || !reference.get_value()) return body.html(`<p class="text-muted">${__("Choose a project.")}</p>`);
		frappe.call({
			method: "ai_form_builder.api.forms.get_enabled_forms",
			args: { reference_doctype: type.get_value(), reference_name: reference.get_value() },
		}).then(({ message }) => render(message || []));
	}

	function render(forms) {
		body.empty();
		if (!forms.length) return body.html(`<p class="text-muted">${__("No forms are enabled for this project.")}</p>`);
		let area = null, group = null;
		forms.forEach((form) => {
			if (form.area !== area) {
				area = form.area; group = null;
				body.append(`<h4 style="margin-top: var(--margin-lg)">${esc(area || __("No Area"))}</h4>`);
			}
			if (form.group !== group) {
				group = form.group;
				body.append(`<h6 class="text-muted" style="margin: var(--margin-md) 0 var(--margin-xs)">${esc(group)}</h6>`);
			}
			const context = form.reference_fieldname ? { [form.reference_fieldname]: reference.get_value() } : {};
			const row = $(`
				<div class="flex align-center justify-between" style="padding: var(--padding-xs) 0; border-bottom: 1px solid var(--border-color)">
					<span>${esc(form.title)} <span class="text-muted small">${esc(form.code || "")}</span></span>
					<span class="flex" style="gap: var(--margin-xs)">
						<button class="btn btn-xs btn-default afb-list">${__("View")}</button>
						${form.can_create ? `<button class="btn btn-xs btn-primary afb-new">${__("New")}</button>` : ""}
					</span>
				</div>`).appendTo(body);
			row.find(".afb-list").on("click", () => frappe.set_route("List", form.doctype, context));
			row.find(".afb-new").on("click", () => frappe.new_doc(form.doctype, context));
		});
	}
};
