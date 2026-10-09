// Review a spec form before publishing: the client's sheet beside our print
// (filled with sample values), and editors for the fields, the grids and the
// page layout. Saving writes the spec onto the AI Form Template only.
frappe.pages["afb-form-review"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Review Form"), single_column: true });
	wrapper.afbr = { page, state: null };
};

frappe.pages["afb-form-review"].on_page_show = function (wrapper) {
	const name = frappe.get_route()[1];
	if (!name) {
		$(wrapper).find(".layout-main-section").html(`<p class="text-muted">${__("Open this page from a form in the Form Library.")}</p>`);
		return;
	}
	afbr_load(wrapper, name);
};

const AFBR_METHOD = "ai_form_builder.api.spec_forms.";

function afbr_load(wrapper, name) {
	frappe.call({ method: AFBR_METHOD + "get_review", args: { template_name: name } }).then(({ message }) => {
		wrapper.afbr.state = message;
		afbr_draw(wrapper);
		if (message.status === "Analyzing") setTimeout(() => frappe.get_route()[1] === name && afbr_load(wrapper, name), 5000);
	});
}

function afbr_draw(wrapper) {
	const { page, state } = wrapper.afbr;
	const esc = frappe.utils.escape_html;
	const spec = state.spec || {};
	page.set_title(state.title);
	page.set_indicator(__(state.status), { Published: "green", "Review Required": "orange", "Analysis Failed": "red", Analyzing: "blue" }[state.status] || "gray");
	page.clear_primary_action();
	page.clear_secondary_action();
	page.clear_menu();
	page.clear_inner_toolbar();
	const main = $(wrapper).find(".layout-main-section").empty();

	if (state.status === "Analyzing") {
		main.html(`<div class="afb-card"><p>${__("AI is reading the sheet. This page refreshes by itself.")}</p></div>`);
		return;
	}
	if (state.editable) {
		page.set_primary_action(__("Save"), () => afbr_save(wrapper));
		page.set_secondary_action(__("Publish"), () =>
			frappe.confirm(__("Publish this form? It is stored as data only: no DocType is created."), () =>
				afbr_save(wrapper).then(() =>
					frappe.call({ method: AFBR_METHOD + "publish", args: { template_name: state.name }, freeze: true }).then(() => {
						frappe.show_alert({ message: __("Published"), indicator: "green" });
						afbr_load(wrapper, state.name);
					})
				)
			)
		);
		page.add_menu_item(__("Read the sheet again (AI)"), () =>
			frappe.confirm(__("Replace this spec with a new reading of the sheet?"), () =>
				frappe.call({ method: AFBR_METHOD + "reanalyze", args: { template_name: state.name } }).then(() => afbr_load(wrapper, state.name))
			)
		);
	}
	page.add_inner_button(__("Refresh preview"), () => afbr_preview(wrapper, afbr_collect(wrapper)));
	page.add_menu_item(__("Export form (JSON)"), () =>
		frappe.call({ method: AFBR_METHOD + "export_spec", args: { template_name: state.name } }).then(({ message }) => {
			const blob = new Blob([JSON.stringify(message, null, 1)], { type: "application/json" });
			const link = document.createElement("a");
			link.href = URL.createObjectURL(blob);
			link.download = `${state.code}.form.json`;
			link.click();
		})
	);
	page.add_menu_item(__("Open template record"), () => frappe.set_route("Form", "AI Form Template", state.name));

	const problems = (state.errors || []).map((e) => `<li>${esc(e)}</li>`).join("");
	const unplaced = (state.unplaced || []).length
		? `<p class="text-muted">${__("Not printed on the sheet (entry only)")}: ${state.unplaced.map(esc).join(", ")}</p>`
		: "";
	const source = state.source
		? state.source_kind === "PDF"
			? `<iframe class="afbr-frame" src="${encodeURI(state.source)}#view=FitH"></iframe>`
			: `<p><a href="${encodeURI(state.source)}" target="_blank" rel="noopener">${__("Download the client's {0} sheet", [esc(state.source_kind || "")])}</a></p>`
		: "";
	main.html(`
		<div class="afbr">
			<div class="afbr-left">
				<div class="afbr-tabs">
					<button class="btn btn-xs btn-default active" data-tab="print">${__("Our print (sample values)")}</button>
					<button class="btn btn-xs btn-default" data-tab="source">${__("Client sheet")}</button>
				</div>
				<div class="afbr-pane" data-pane="print"><iframe class="afbr-frame afbr-preview"></iframe></div>
				<div class="afbr-pane" data-pane="source" hidden>${source}</div>
			</div>
			<div class="afbr-right">
				${problems ? `<div class="afb-card afbr-errors"><b>${__("To fix before publishing")}</b><ul>${problems}</ul></div>` : ""}
				${unplaced}
				<div class="afb-card">
					<label class="afbr-label">${__("Title printed on the sheet")}</label>
					<input class="form-control afbr-title" value="${esc(spec.title || "")}" ${state.editable ? "" : "disabled"}>
				</div>
				<div class="afb-card"><div class="afb-card-title">${__("Fields")}</div><div class="afbr-fields"></div>
					${state.editable ? `<button class="btn btn-xs btn-default afbr-add-field">${__("Add field")}</button>` : ""}</div>
				<div class="afb-card"><div class="afb-card-title">${__("Grids (repeating rows)")}</div><div class="afbr-grids"></div></div>
				<div class="afb-card"><div class="afb-card-title">${__("Page layout (advanced)")}</div>
					<p class="text-muted small">${__("Pages, boxes and page settings as JSON. A cell shows a field with {\"field\": \"name\"}.")}</p>
					<textarea class="form-control afbr-layout" rows="14" spellcheck="false" ${state.editable ? "" : "disabled"}></textarea></div>
			</div>
		</div>`);
	main.find(".afbr-layout").val(JSON.stringify({ page: spec.page || {}, pages: spec.pages || [] }, null, 1));
	main.find(".afbr-tabs button").on("click", (event) => {
		const tab = $(event.currentTarget).data("tab");
		main.find(".afbr-tabs button").removeClass("active");
		$(event.currentTarget).addClass("active");
		main.find(".afbr-pane").each((_i, pane) => (pane.hidden = $(pane).data("pane") !== tab));
	});
	afbr_fields(wrapper, spec.fields || []);
	afbr_grids(wrapper, spec.grids || []);
	main.find(".afbr-add-field").on("click", () => {
		const fields = afbr_collect(wrapper).fields;
		fields.push({ name: `field_${fields.length + 1}`, label: __("New field"), type: "Data" });
		afbr_fields(wrapper, fields);
	});
	afbr_preview(wrapper, spec);
}

function afbr_type_select(types, value, disabled) {
	return `<select class="form-control input-xs" data-k="type" ${disabled}>${types
		.map((t) => `<option ${t === value ? "selected" : ""}>${t}</option>`)
		.join("")}</select>`;
}

function afbr_fields(wrapper, fields) {
	const { state } = wrapper.afbr;
	const esc = frappe.utils.escape_html;
	const off = state.editable ? "" : "disabled";
	const rows = fields
		.map(
			(f, i) => `<tr data-i="${i}">
			<td><input class="form-control input-xs" data-k="label" value="${esc(f.label || "")}" ${off}></td>
			<td><input class="form-control input-xs" data-k="name" value="${esc(f.name || "")}" ${off}></td>
			<td>${afbr_type_select(state.field_types, f.type, off)}</td>
			<td><input class="form-control input-xs" data-k="options" placeholder="${__("A / B / C")}" value="${esc((f.options || []).join(" / "))}" ${off}></td>
			<td><input class="form-control input-xs" data-k="section" value="${esc(f.section || "")}" ${off}></td>
			<td class="text-center"><input type="checkbox" data-k="mandatory" ${f.mandatory ? "checked" : ""} ${off}></td>
			<td>${state.editable ? `<button class="btn btn-xs btn-link afbr-del" title="${__("Remove")}">×</button>` : ""}</td>
		</tr>`
		)
		.join("");
	const box = $(wrapper).find(".afbr-fields").html(`
		<table class="table table-sm afbr-table"><thead><tr>
			<th>${__("Label")}</th><th>${__("Name")}</th><th>${__("Type")}</th><th>${__("Options")}</th><th>${__("Section")}</th><th>${__("Req.")}</th><th></th>
		</tr></thead><tbody>${rows}</tbody></table>`);
	box.data("hidden", fields.map((f) => ({ default: f.default, sample: f.sample })));
	box.find(".afbr-del").on("click", (event) => {
		const keep = afbr_collect(wrapper).fields.filter((_f, i) => i !== $(event.currentTarget).closest("tr").data("i"));
		afbr_fields(wrapper, keep);
	});
}

function afbr_grids(wrapper, grids) {
	const { state } = wrapper.afbr;
	const esc = frappe.utils.escape_html;
	const off = state.editable ? "" : "disabled";
	const box = $(wrapper).find(".afbr-grids").empty();
	if (!grids.length) box.html(`<p class="text-muted">${__("This sheet has no repeating rows.")}</p>`);
	grids.forEach((grid, gi) => {
		const columns = grid.columns
			.map(
				(c, ci) => `<tr data-ci="${ci}">
				<td><input class="form-control input-xs" data-k="label" value="${esc(c.label || "")}" ${off}></td>
				<td><input class="form-control input-xs" data-k="name" value="${esc(c.name || "")}" ${off}></td>
				<td>${afbr_type_select(state.field_types, c.type, off)}</td>
				<td><input class="form-control input-xs" data-k="options" value="${esc((c.options || []).join(" / "))}" ${off}></td>
				<td><input class="form-control input-xs" data-k="width" type="number" min="1" value="${esc(c.width || 10)}" ${off}></td>
			</tr>`
			)
			.join("");
		$(`<div class="afbr-grid" data-gi="${gi}">
			<div class="afbr-row">
				<input class="form-control input-xs" data-g="label" value="${esc(grid.label || "")}" ${off}>
				<input class="form-control input-xs" data-g="name" value="${esc(grid.name || "")}" ${off}>
				<input class="form-control input-xs" data-g="section" placeholder="${__("Section")}" value="${esc(grid.section || "")}" ${off}>
				<label class="small">${__("Blank lines")} <input class="form-control input-xs" data-g="blank_rows" type="number" min="0" value="${grid.blank_rows || 0}" ${off}></label>
				<label class="small"><input type="checkbox" data-g="allow_add" ${grid.allow_add ? "checked" : ""} ${off}> ${__("Users may add rows")}</label>
			</div>
			<table class="table table-sm afbr-table"><thead><tr><th>${__("Column")}</th><th>${__("Name")}</th><th>${__("Type")}</th><th>${__("Options")}</th><th>${__("Width")}</th></tr></thead><tbody>${columns}</tbody></table>
			<p class="text-muted small">${__("{0} pre-printed rows", [(grid.fixed_rows || []).length])}</p>
		</div>`)
			.data("fixed", grid.fixed_rows || [])
			.appendTo(box);
	});
}

function afbr_options(text) {
	return (text || "").split("/").map((s) => s.trim()).filter(Boolean);
}

function afbr_collect(wrapper) {
	const main = $(wrapper).find(".layout-main-section");
	const hidden = main.find(".afbr-fields").data("hidden") || [];
	const fields = main.find(".afbr-fields tbody tr").toArray().map((tr, i) => {
		const get = (k) => $(tr).find(`[data-k="${k}"]`);
		const field = {
			label: get("label").val(),
			name: get("name").val(),
			type: get("type").val(),
			options: afbr_options(get("options").val()),
			section: get("section").val(),
			mandatory: get("mandatory").is(":checked"),
		};
		return { ...(hidden[i] || {}), ...field };
	});
	const grids = main.find(".afbr-grid").toArray().map((box) => {
		const g = (k) => $(box).find(`[data-g="${k}"]`);
		return {
			label: g("label").val(),
			name: g("name").val(),
			section: g("section").val(),
			blank_rows: parseInt(g("blank_rows").val() || "0", 10),
			allow_add: g("allow_add").is(":checked"),
			fixed_rows: $(box).data("fixed") || [],
			columns: $(box).find("tbody tr").toArray().map((tr) => {
				const c = (k) => $(tr).find(`[data-k="${k}"]`);
				return { label: c("label").val(), name: c("name").val(), type: c("type").val(), options: afbr_options(c("options").val()), width: parseFloat(c("width").val() || "10") };
			}),
		};
	});
	let layout = {};
	try {
		layout = JSON.parse(main.find(".afbr-layout").val() || "{}");
	} catch (e) {
		frappe.throw(__("The page layout is not valid JSON: {0}", [e.message]));
	}
	return { title: main.find(".afbr-title").val(), page: layout.page, pages: layout.pages, fields, grids };
}

function afbr_preview(wrapper, spec) {
	const { state } = wrapper.afbr;
	frappe.call({ method: AFBR_METHOD + "preview", args: { template_name: state.name, spec } }).then(({ message }) => {
		const frame = $(wrapper).find(".afbr-preview")[0];
		if (frame) frame.srcdoc = message || "";
	});
}

function afbr_save(wrapper) {
	const { state } = wrapper.afbr;
	const spec = afbr_collect(wrapper);
	return frappe
		.call({ method: AFBR_METHOD + "save_spec", args: { template_name: state.name, spec }, freeze: true, freeze_message: __("Saving…") })
		.then(({ message }) => {
			wrapper.afbr.state = message;
			frappe.show_alert({ message: __("Saved"), indicator: "green" });
			afbr_draw(wrapper);
		});
}
