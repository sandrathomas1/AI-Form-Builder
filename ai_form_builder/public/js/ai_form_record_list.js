// Records of spec forms open on the form page (drawn from the form's spec),
// not on the raw value/row tables of AI Form Record.
frappe.listview_settings["AI Form Record"] = {
	get_form_link(doc) {
		return `/app/afb-form/${encodeURIComponent(doc.name)}`;
	},
	primary_action() {
		const filters = {};
		for (const [field, , value] of (cur_list?.filter_area?.get() || []).map((f) => [f[1], f[2], f[3]])) {
			filters[field] = value;
		}
		if (filters.form_template) {
			frappe.route_options = { template: filters.form_template, reference_name: filters.reference_name };
			frappe.set_route("afb-form");
			return;
		}
		frappe.msgprint(__("Start a record from the form in the Form Library, or filter this list by Form first."));
	},
};
