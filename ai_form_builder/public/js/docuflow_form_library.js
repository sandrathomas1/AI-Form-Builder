// Form Library panel for Docuflow's /d app.
//
// Added to Docuflow's page by ai_form_builder (after_request hook); Docuflow's
// own files are not changed. Which routes show the panel is configuration:
// every AI Form Area with "Show Form Library in External App" and its route
// prefixes. A new area needs no code here.
(() => {
	if (window.__afbFormLibrary) return;
	window.__afbFormLibrary = true;

	const API = "/api/method/";
	const state = { config: null, area: null, project: null, path: null, open: false, forms: [], loading: false };
	const esc = (value) =>
		String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

	// ---------------------------------------------------------------- server
	function serverMessage(data) {
		try {
			const messages = JSON.parse(data._server_messages || "[]").map((m) => JSON.parse(m).message);
			if (messages.length) return messages.join("\n").replace(/<[^>]+>/g, "");
		} catch (e) {
			/* fall through */
		}
		return data.exception ? String(data.exception).split(":").slice(1).join(":").trim() : "";
	}

	async function call(method, args = {}) {
		const body = new URLSearchParams();
		Object.entries(args).forEach(([key, value]) => {
			if (value === undefined || value === null) return;
			body.append(key, typeof value === "object" ? JSON.stringify(value) : String(value));
		});
		const response = await fetch(API + method, {
			method: "POST",
			credentials: "same-origin",
			headers: {
				Accept: "application/json",
				"Content-Type": "application/x-www-form-urlencoded",
				"X-Frappe-CSRF-Token": window.csrf_token || "",
			},
			body,
		});
		const data = await response.json().catch(() => ({}));
		if (!response.ok) throw new Error(serverMessage(data) || response.statusText);
		return data.message; // undefined when the method returned None
	}

	async function upload(file) {
		const data = new FormData();
		data.append("file", file, file.name);
		data.append("is_private", "1");
		const response = await fetch(API + "upload_file", {
			method: "POST",
			credentials: "same-origin",
			headers: { Accept: "application/json", "X-Frappe-CSRF-Token": window.csrf_token || "" },
			body: data,
		});
		const json = await response.json().catch(() => ({}));
		if (!response.ok || !json.message) throw new Error(serverMessage(json) || "Upload failed");
		return json.message.file_url;
	}

	// ---------------------------------------------------------------- context
	function areaFor(path) {
		let best = null;
		for (const area of state.config.areas) {
			for (const prefix of area.prefixes || []) {
				if ((path === prefix || path.startsWith(prefix + "/")) && (!best || prefix.length > best.length)) {
					best = { area: area.name, length: prefix.length };
				}
			}
		}
		return best ? best.area : null;
	}

	// The project Docuflow's top bar shows. Docuflow keeps it in localStorage
	// under "dcms:active-project:<user_id cookie>" (useGlobalProject.js); read
	// only, never written from here.
	function docuflowProject() {
		try {
			const cookies = new URLSearchParams(document.cookie.split("; ").join("&"));
			const user = cookies.get("user_id");
			return localStorage.getItem(`dcms:active-project:${user && user !== "Guest" ? user : "anon"}`) || null;
		} catch (e) {
			return null;
		}
	}

	function syncProject() {
		state.project = projectFromPath(window.location.pathname) || docuflowProject() || state.project;
	}

	function projectFromPath(path) {
		const match = path.match(/^\/(?:d|docuflow)\/projects\/([^/?#]+)/);
		return match ? decodeURIComponent(match[1]) : null;
	}

	function onRouteChange() {
		const path = window.location.pathname.replace(/\/+$/, "");
		if (path === state.path) return;
		state.path = path;
		const urlProject = projectFromPath(path);
		syncProject();
		state.area = areaFor(path);
		// Shown in a configured area, or on a project page (all areas).
		state.visible = Boolean(state.area || urlProject);
		renderLauncher();
		if (state.open) state.visible ? loadForms() : closePanel();
	}

	// ---------------------------------------------------------------- launcher + panel
	let launcher, panel, overlay;

	function areaLabel() {
		return state.area || "Project";
	}

	function renderLauncher() {
		if (!launcher) {
			launcher = document.createElement("button");
			launcher.type = "button";
			launcher.className = "afbdf-launcher";
			launcher.addEventListener("click", () => (state.open ? closePanel() : openPanel()));
			document.body.appendChild(launcher);
		}
		launcher.hidden = !state.visible;
		launcher.innerHTML = `<span class="afbdf-launcher-icon" aria-hidden="true">＋</span><span>${esc(areaLabel())} forms</span>`;
		launcher.setAttribute("aria-label", `${areaLabel()} forms`);
	}

	function openPanel() {
		state.open = true;
		syncProject();
		if (!panel) {
			panel = document.createElement("aside");
			panel.className = "afbdf-panel";
			panel.setAttribute("role", "dialog");
			panel.setAttribute("aria-label", "Forms");
			document.body.appendChild(panel);
			panel.addEventListener("click", onPanelClick);
			panel.addEventListener("change", onPanelChange);
		}
		panel.hidden = false;
		loadForms();
	}

	function closePanel() {
		state.open = false;
		if (panel) panel.hidden = true;
	}

	async function loadForms() {
		state.loading = true;
		renderPanel();
		try {
			const result = (await call("ai_form_builder.integrations.docuflow.get_area_forms", { area: state.area, project: state.project })) || {};
			state.forms = result.forms || [];
			state.projectTitle = result.project_title;
			state.error = null;
		} catch (error) {
			state.forms = [];
			state.error = error.message;
		}
		state.loading = false;
		renderPanel();
	}

	function statusPill(form) {
		if (!form.status) return "";
		const tone = { Published: "green", Generated: "blue", Approved: "blue", Draft: "gray" }[form.status] || "orange";
		return `<span class="afbdf-pill afbdf-${tone}">${esc(form.status)}</span>`;
	}

	function formRow(form) {
		const manage = state.config.can_manage;
		const actions = [];
		if (form.new_url) actions.push(`<a class="afbdf-btn afbdf-primary" href="${esc(form.new_url)}" target="_blank" rel="noopener">New</a>`);
		if (form.list_url) actions.push(`<a class="afbdf-btn" href="${esc(form.list_url)}" target="_blank" rel="noopener">Records</a>`);
		if (manage) {
			if (form.is_spec && form.review_url)
				actions.push(`<a class="afbdf-btn" href="${esc(form.review_url)}" target="_blank" rel="noopener" title="Check the fields and the print against the client's sheet">${form.status === "Published" ? "View form" : "Review &amp; publish"}</a>`);
			if (form.edit_url) actions.push(`<a class="afbdf-btn" href="${esc(form.edit_url)}" target="_blank" rel="noopener" title="Add and arrange fields in Frappe's Form Builder">Edit fields</a>`);
			if (form.doctype) actions.push(`<button type="button" class="afbdf-btn" data-action="sync" data-template="${esc(form.form_template)}" title="Pick up fields added in Form Builder, then publish">Sync &amp; publish</button>`);
			if (form.configure_url && form.enabled) actions.push(`<a class="afbdf-btn" href="${esc(form.configure_url)}" target="_blank" rel="noopener" title="Show, hide or require fields for this project">Project fields</a>`);
			if (!form.doctype && !form.is_spec) actions.push(`<a class="afbdf-btn" href="${esc(form.template_url)}" target="_blank" rel="noopener">Review AI fields</a>`);
		}
		const toggle =
			manage && (form.doctype || (form.is_spec && form.status === "Published"))
				? `<label class="afbdf-toggle" title="${state.project ? "Use this form on the project" : "Choose a project first"}">
						<input type="checkbox" data-action="enable" data-template="${esc(form.form_template)}" ${form.enabled ? "checked" : ""} ${state.project ? "" : "disabled"}>
						<span>Use on project</span></label>`
				: "";
		return `
			<li class="afbdf-form">
				<div class="afbdf-form-head">
					<div><div class="afbdf-form-title">${esc(form.title)}</div>
					<div class="afbdf-muted">${esc(form.code || "")}${state.area ? "" : ` · ${esc(form.area || "")}`}</div></div>
					${manage ? statusPill(form) : ""}
				</div>
				${toggle}
				<div class="afbdf-actions">${actions.join("")}</div>
			</li>`;
	}

	function renderPanel() {
		if (!panel || panel.hidden) return;
		const manage = state.config.can_manage;
		const project = state.project
			? `<span class="afbdf-muted">Project</span> <b>${esc(state.project)}</b>${state.projectTitle && state.projectTitle !== state.project ? ` · ${esc(state.projectTitle)}` : ""}`
			: `<span class="afbdf-warn">Choose a project in the top bar to use forms.</span>`;
		let body;
		if (state.loading) body = `<p class="afbdf-muted afbdf-pad">Loading…</p>`;
		else if (state.error) body = `<p class="afbdf-error afbdf-pad">${esc(state.error)}</p>`;
		else if (!state.forms.length)
			body = `<p class="afbdf-muted afbdf-pad">${manage ? `No ${esc(state.area || "")} forms yet. Use <b>Create new form</b> below.` : "No forms are enabled for this project yet."}</p>`;
		else {
			const groups = {};
			state.forms.forEach((form) => (groups[form.group || "Other"] = groups[form.group || "Other"] || []).push(form));
			body = Object.entries(groups)
				.map(([group, forms]) => `<h4 class="afbdf-group">${esc(group)}</h4><ul class="afbdf-list">${forms.map(formRow).join("")}</ul>`)
				.join("");
		}
		panel.innerHTML = `
			<header class="afbdf-head">
				<div><div class="afbdf-title">${esc(areaLabel())} forms</div><div class="afbdf-sub">${project}</div></div>
				<button type="button" class="afbdf-icon" data-action="close" aria-label="Close">×</button>
			</header>
			<div class="afbdf-body">${body}</div>
			${manage ? `<footer class="afbdf-foot"><button type="button" class="afbdf-btn afbdf-primary afbdf-wide" data-action="create">＋ Create new form</button></footer>` : ""}`;
	}

	async function onPanelClick(event) {
		const target = event.target.closest("[data-action]");
		if (!target) return;
		const action = target.dataset.action;
		if (action === "close") return closePanel();
		if (action === "create") return openCreate();
		if (action === "sync") {
			target.disabled = true;
			target.textContent = "Syncing…";
			try {
				const summary = (await call("ai_form_builder.api.forms.sync_fields", { template_name: target.dataset.template })) || {};
				const form = state.forms.find((f) => f.form_template === target.dataset.template);
				if (form && !["Published", "Superseded"].includes(form.status)) {
					await call("ai_form_builder.api.forms.publish", { template_name: target.dataset.template });
				}
				toast(summary.added?.length ? `Added ${summary.added.length} field(s): ${summary.added.join(", ")}` : "Fields are up to date.");
			} catch (error) {
				toast(error.message, true);
			}
			loadForms();
		}
	}

	async function onPanelChange(event) {
		const target = event.target.closest('[data-action="enable"]');
		if (!target || !state.project) return;
		try {
			await call("ai_form_builder.api.project_configuration.set_form_enabled", {
				reference_doctype: state.config.reference_doctype,
				reference_name: state.project,
				form_template: target.dataset.template,
				enabled: target.checked ? 1 : 0,
			});
			toast(target.checked ? `Enabled for ${state.project}.` : `Removed from ${state.project}.`);
		} catch (error) {
			target.checked = !target.checked;
			toast(error.message, true);
		}
		loadForms();
	}

	function toast(message, isError) {
		const note = document.createElement("div");
		note.className = "afbdf-toast" + (isError ? " afbdf-toast-error" : "");
		note.textContent = message;
		document.body.appendChild(note);
		setTimeout(() => note.remove(), isError ? 7000 : 4000);
	}

	// ---------------------------------------------------------------- create new form
	const METHODS = [
		["manual", "Create manually (no code)", "Name the form, then add fields with Frappe's drag-and-drop Form Builder. No AI needed."],
		["ai", "Create from the client's sheet (AI)", "Upload the client's PDF, Excel or Word sheet. AI reads its boxes and tables; you review and publish. No DocType is created."],
		["existing", "Use an existing DocType", "Put a DocType that already exists into this area's forms."],
	];

	const SHEET_TYPES =
		".pdf,.xlsx,.xlsm,.docx,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

	function modal(html) {
		closeModal();
		overlay = document.createElement("div");
		overlay.className = "afbdf-overlay";
		overlay.innerHTML = `<div class="afbdf-modal" role="dialog" aria-modal="true">${html}</div>`;
		overlay.addEventListener("click", (event) => {
			if (event.target === overlay || event.target.closest('[data-action="cancel"]')) closeModal();
		});
		document.body.appendChild(overlay);
		overlay.querySelector("input, select, button")?.focus();
		return overlay.querySelector(".afbdf-modal");
	}

	function closeModal() {
		overlay?.remove();
		overlay = null;
	}

	function openCreate() {
		const box = modal(`
			<h3 class="afbdf-modal-title">Create new form</h3>
			<p class="afbdf-muted">${state.area ? `The form is filed under <b>${esc(state.area)}</b>.` : "Choose how to start."}</p>
			<div class="afbdf-methods">${METHODS.map(
				([key, label, help]) => `<button type="button" class="afbdf-method" data-method="${key}"><b>${esc(label)}</b><span>${esc(help)}</span></button>`
			).join("")}</div>
			<div class="afbdf-modal-foot"><button type="button" class="afbdf-btn" data-action="cancel">Cancel</button></div>`);
		box.addEventListener("click", (event) => {
			const method = event.target.closest("[data-method]")?.dataset.method;
			if (method) openMethod(method);
		});
	}

	function areaOptions() {
		return state.config.areas
			.map((area) => `<option value="${esc(area.name)}" ${area.name === state.area ? "selected" : ""}>${esc(area.name)}</option>`)
			.join("");
	}

	function groupOptions(area) {
		return (
			`<option value="">—</option>` +
			state.config.groups
				.filter((group) => group.target_area === area)
				.map((group) => `<option value="${esc(group.name)}">${esc(group.label)}</option>`)
				.join("")
		);
	}

	function commonFields() {
		const area = state.area || state.config.areas[0]?.name;
		return `
			<label class="afbdf-field"><span>Form name *</span><input name="template_title" required maxlength="61" placeholder="e.g. Concrete Inspection Request"></label>
			<label class="afbdf-field"><span>Form code *</span><input name="template_code" required maxlength="140" placeholder="e.g. QA-CIR-001"></label>
			<div class="afbdf-row">
				<label class="afbdf-field"><span>Area</span><select name="target_area">${areaOptions()}</select></label>
				<label class="afbdf-field"><span>Group</span><select name="form_group">${groupOptions(area)}</select></label>
			</div>`;
	}

	function projectOption() {
		return state.project
			? `<label class="afbdf-check"><input type="checkbox" name="enable_for_project" checked> Use it on project <b>${esc(state.project)}</b> straight away</label>`
			: "";
	}

	function openMethod(method) {
		const titles = { manual: "Create manually (no code)", ai: "Create from the client's sheet (AI)", existing: "Use an existing DocType" };
		let fields = "";
		if (method === "manual") {
			fields = `${commonFields()}
				<label class="afbdf-field"><span>Description</span><textarea name="description" rows="2"></textarea></label>
				<label class="afbdf-check"><input type="checkbox" name="allow_attachments" checked> Allow attachments</label>
				<label class="afbdf-check"><input type="checkbox" name="is_submittable"> Is submittable (records are submitted and then locked)</label>
				<label class="afbdf-check"><input type="checkbox" name="enable_project_configuration" checked> Project configurable (each project picks its fields)</label>
				${projectOption()}`;
		} else if (method === "ai") {
			fields = `${commonFields()}
				<label class="afbdf-field"><span>Client sheet (PDF, Excel or Word) *</span><input type="file" name="pdf" accept="${SHEET_TYPES}" required></label>
				<label class="afbdf-check"><input type="checkbox" name="enable_project_configuration" checked> Project configurable (each project picks its fields)</label>
				${projectOption()}`;
		} else {
			fields = `
				<label class="afbdf-field"><span>Document type *</span><input name="doctype" list="afbdf-doctypes" required autocomplete="off" placeholder="Start typing a DocType name"></label>
				<datalist id="afbdf-doctypes"></datalist>
				${commonFields()}
				<label class="afbdf-check"><input type="checkbox" name="enable_project_configuration"> Project configurable (the DocType must already have a <code>${esc(state.config.reference_fieldname)}</code> field)</label>
				${projectOption()}`;
		}
		const box = modal(`
			<form class="afbdf-form-create" novalidate>
				<h3 class="afbdf-modal-title">${esc(titles[method])}</h3>
				${fields}
				<p class="afbdf-error" data-role="error" hidden></p>
				<div class="afbdf-modal-foot">
					<button type="button" class="afbdf-btn" data-action="back">Back</button>
					<button type="submit" class="afbdf-btn afbdf-primary">${method === "existing" ? "Add form" : method === "ai" ? "Upload and analyse" : "Create form"}</button>
				</div>
			</form>`);
		const form = box.querySelector("form");
		form.querySelector('[data-action="back"]').addEventListener("click", openCreate);
		form.target_area.addEventListener("change", () => (form.form_group.innerHTML = groupOptions(form.target_area.value)));
		if (method === "existing") wireDoctypeSearch(form);
		form.addEventListener("submit", (event) => {
			event.preventDefault();
			submitMethod(method, form);
		});
	}

	function wireDoctypeSearch(form) {
		let timer;
		form.doctype.addEventListener("input", () => {
			clearTimeout(timer);
			timer = setTimeout(async () => {
				const results = await call("frappe.desk.search.search_link", {
					doctype: "DocType",
					txt: form.doctype.value,
					filters: { istable: 0, issingle: 0 },
					page_length: 15,
				}).catch(() => []);
				form.querySelector("#afbdf-doctypes").innerHTML = (results || []).map((row) => `<option value="${esc(row.value)}">`).join("");
				if (!form.template_title.value) form.template_title.placeholder = form.doctype.value;
			}, 250);
		});
	}

	async function submitMethod(method, form) {
		const error = form.querySelector('[data-role="error"]');
		const submit = form.querySelector('button[type="submit"]');
		const value = (name) => (form[name]?.value || "").trim();
		const checked = (name) => (form[name]?.checked ? 1 : 0);
		error.hidden = true;
		const required = ["template_title", "template_code", ...(method === "existing" ? ["doctype"] : [])];
		const missing = required.filter((name) => !value(name));
		if (method === "ai" && !form.pdf.files.length) missing.push("pdf");
		if (missing.length) {
			error.textContent = "Fill in the fields marked *.";
			error.hidden = false;
			return;
		}
		submit.disabled = true;
		const base = {
			template_title: value("template_title"),
			template_code: value("template_code"),
			target_area: value("target_area"),
			form_group: value("form_group"),
			enable_project_configuration: checked("enable_project_configuration"),
		};
		try {
			if (method === "manual") {
				submit.textContent = "Creating…";
				const result = await call("ai_form_builder.api.manual_form.create_manual_form", {
					...base,
					description: value("description"),
					is_submittable: checked("is_submittable"),
					allow_attachments: checked("allow_attachments"),
				});
				await enableIfAsked(form, result.template, base.enable_project_configuration);
				showNextSteps({
					title: `${base.template_title} is created`,
					steps: [
						"Open Form Builder and drag in the fields you need (sections, columns, tables, signatures…), then press Save.",
						"Come back here and press Sync & publish on the form.",
					],
					primary: { label: "Open Form Builder", href: `/app/doctype/${encodeURIComponent(result.doctype)}` },
				});
			} else if (method === "ai") {
				submit.textContent = "Uploading…";
				const url = await upload(form.pdf.files[0]);
				submit.textContent = "Creating…";
				const created = await call("ai_form_builder.api.template.create_template_from_upload", { ...base, source_pdf: url });
				await call("ai_form_builder.api.template.analyze_template", { template_name: created.name });
				await enableIfAsked(form, created.name, base.enable_project_configuration);
				showNextSteps({
					title: `${base.template_title}: AI is reading the sheet`,
					steps: [
						"Open the review page: compare our print with the client's sheet and correct any field.",
						"Press Publish. The form is saved as data only (no DocType), then appears here with New and Records.",
					],
					primary: { label: "Review form", href: `/app/afb-form-review/${encodeURIComponent(created.name)}` },
				});
			} else {
				submit.textContent = "Adding…";
				const result = await call("ai_form_builder.api.forms.register_existing_doctype", {
					...base,
					doctype: value("doctype"),
					reference_doctype: base.enable_project_configuration ? state.config.reference_doctype : null,
					reference_fieldname: base.enable_project_configuration ? state.config.reference_fieldname : null,
				});
				await enableIfAsked(form, result.template, base.enable_project_configuration);
				closeModal();
				toast(`${base.template_title} added.`);
			}
			loadForms();
		} catch (err) {
			error.textContent = err.message || "Something went wrong.";
			error.hidden = false;
			submit.disabled = false;
			submit.textContent = method === "existing" ? "Add form" : method === "ai" ? "Upload and analyse" : "Create form";
		}
	}

	async function enableIfAsked(form, template, projectConfigurable) {
		if (!state.project || !projectConfigurable || !form.enable_for_project?.checked) return;
		await call("ai_form_builder.api.project_configuration.set_form_enabled", {
			reference_doctype: state.config.reference_doctype,
			reference_name: state.project,
			form_template: template,
			enabled: 1,
		});
	}

	function showNextSteps({ title, steps, primary }) {
		modal(`
			<h3 class="afbdf-modal-title">${esc(title)}</h3>
			<ol class="afbdf-steps">${steps.map((step) => `<li>${esc(step)}</li>`).join("")}</ol>
			<div class="afbdf-modal-foot">
				<button type="button" class="afbdf-btn" data-action="cancel">Done</button>
				<a class="afbdf-btn afbdf-primary" href="${esc(primary.href)}" target="_blank" rel="noopener">${esc(primary.label)}</a>
			</div>`);
	}

	// ---------------------------------------------------------------- boot
	async function boot() {
		try {
			state.config = await call("ai_form_builder.integrations.docuflow.get_bridge_config");
		} catch (error) {
			return; // not logged in yet, or no access: stay invisible
		}
		if (!state.config || !state.config.enabled) return;
		state.project = state.config.active_project || null;
		syncProject();
		window.addEventListener("dcms:project-change", (event) => {
			state.project = event.detail?.project || null;
			if (state.open) loadForms();
		});
		window.addEventListener("popstate", onRouteChange);
		for (const method of ["pushState", "replaceState"]) {
			const original = history[method];
			history[method] = function (...args) {
				const result = original.apply(this, args);
				setTimeout(onRouteChange, 0);
				return result;
			};
		}
		document.addEventListener("keydown", (event) => {
			if (event.key !== "Escape") return;
			if (overlay) closeModal();
			else if (state.open) closePanel();
		});
		onRouteChange();
	}

	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
	else boot();
})();
