frappe.ui.form.on("AI Form Template", {
	setup(frm) {
		frm.set_query("form_group", () => ({
			filters: Object.assign({ enabled: 1 }, frm.doc.target_area ? { target_area: frm.doc.target_area } : {}),
		}));
		frm.set_query("target_area", () => ({ filters: { enabled: 1 } }));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		const doc = frm.doc;
		const call = (method, args, after) =>
			frappe.call({ method, args: Object.assign({ template_name: doc.name }, args || {}), freeze: true })
				.then(({ message }) => (after ? after(message) : frm.reload_doc()));
		const open = ({ route, route_options }) => {
			if (route_options) frappe.route_options = route_options;
			frappe.set_route(...route);
		};
		const locked = ["Published", "Superseded"].includes(doc.status);

		// Spec forms: the form is data (spec_json); no DocType is ever generated.
		if ((doc.storage_mode || "Spec") === "Spec" && !doc.generated_doctype) {
			const form = __("Form");
			frm.add_custom_button(__("Review Form"), () => frappe.set_route("afb-form-review", doc.name), form);
			if (doc.status === "Published") {
				frm.add_custom_button(__("Records"), () => frappe.set_route("List", "AI Form Record", { form_template: doc.name }), form);
				frm.add_custom_button(__("Create Revision"), () =>
					call("ai_form_builder.api.forms.create_revision", {}, (name) => frappe.set_route("Form", "AI Form Template", name)),
					__("Revision"));
			}
			if (doc.enable_project_configuration && doc.status === "Published") {
				frm.add_custom_button(__("Project Setup"), () => frappe.set_route("project-form-setup"), form);
			}
			if (["Uploaded", "Analysis Failed", "Review Required"].includes(doc.status) && doc.source_pdf) {
				frm.add_custom_button(__("Read Sheet (AI)"), () => call("ai_form_builder.api.template.analyze_template"));
			}
			if (locked) frm.set_intro(__("This revision is {0}; use Create Revision to change it.", [__(doc.status)]));
			return;
		}

		// Existing AI workflow, until the DocType exists.
		if (doc.source_type === "AI PDF" && !doc.generated_doctype) {
			frm.add_custom_button(__("Analyze PDF"), () => call("ai_form_builder.api.template.analyze_template"));
			frm.add_custom_button(__("Review Mapping"), () => frappe.set_route("form-mapping-editor", doc.name));
			frm.add_custom_button(__("Approve Mapping"), () => call("ai_form_builder.api.template.approve_mapping"));
			frm.add_custom_button(__("Generate DocType"), () =>
				frappe.prompt(
					{ label: __("DocType Name"), fieldname: "doctype_name", fieldtype: "Data", reqd: 1, default: doc.template_title },
					(values) => call("ai_form_builder.api.generator.generate_doctype", { doctype_name: values.doctype_name })
				)
			);
			return;
		}
		if (!doc.generated_doctype) return;

		const form = __("Form");
		frm.add_custom_button(__("Open"), () => frappe.set_route("List", doc.generated_doctype), form);
		frm.add_custom_button(__("Edit with Frappe"), () => call("ai_form_builder.api.forms.get_edit_route", {}, open), form);
		frm.add_custom_button(__("Sync Fields"), () =>
			call("ai_form_builder.api.forms.sync_fields", {}, (summary) => {
				const parts = ["added", "updated", "orphaned", "restored"]
					.filter((key) => summary[key]?.length)
					.map((key) => `${__(frappe.utils.to_title_case(key))}: ${summary[key].join(", ")}`);
				frappe.show_alert({ message: parts.join("<br>") || __("Fields are already in sync."), indicator: "green" }, 8);
				frm.reload_doc();
			}), form);
		if (doc.source_pdf && !locked) {
			frm.add_custom_button(__("Map PDF"), () => frappe.set_route("form-mapping-editor", doc.name), form);
		}
		frm.add_custom_button(__("Configure Workflow"), () => call("ai_form_builder.api.forms.get_workflow_route", {}, open), form);
		if (doc.enable_project_configuration) {
			frm.add_custom_button(__("Project Setup"), () => frappe.set_route("project-form-setup"), form);
		}

		const revision = __("Revision");
		if (!locked && doc.status !== "Disabled") {
			frm.add_custom_button(__("Publish"), () =>
				frappe.confirm(
					doc.previous_revision
						? __("Publish this revision? Earlier revisions become Superseded; their records keep their own mapping.")
						: __("Publish this form so projects can use it?"),
					() => call("ai_form_builder.api.forms.publish")
				), revision);
		}
		if (["Published", "Generated"].includes(doc.status)) {
			frm.add_custom_button(__("Create Revision"), () =>
				call("ai_form_builder.api.forms.create_revision", {}, (name) => frappe.set_route("Form", "AI Form Template", name)),
				revision);
		}
		if (locked) {
			frm.set_intro(__("This revision is {0}. Its PDF mapping is frozen; use Create Revision to change it.", [__(doc.status)]));
		}
	},
});
