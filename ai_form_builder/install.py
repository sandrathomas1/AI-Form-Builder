import frappe

# Initial configuration only: areas and groups are ordinary records an
# administrator can rename, disable or extend. No code depends on these names.
INITIAL_AREAS = [
	{
		"area_name": "Quality",
		"area_code": "QUALITY",
		"sequence": 10,
		"external_reference": "quality",
		"groups": [("QA", 10), ("QC", 20)],
	},
	{
		"area_name": "HSE",
		"area_code": "HSE",
		"sequence": 20,
		"external_reference": "hse",
		"groups": [("Inspections", 10), ("Permits", 20), ("Safety", 30)],
	},
]


def after_install():
	for role in ("AI Form Builder Manager", "AI Form Builder User"):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
	seed_initial_areas()


def seed_initial_areas():
	"""Create missing initial areas/groups; never overwrite what an admin changed."""
	from ai_form_builder.integrations import docuflow

	external_app = docuflow.APP if docuflow.is_installed() else None
	for area in INITIAL_AREAS:
		if not frappe.db.exists("AI Form Area", area["area_name"]):
			frappe.get_doc(
				{
					"doctype": "AI Form Area",
					"area_name": area["area_name"],
					"area_code": area["area_code"],
					"sequence": area["sequence"],
					"enabled": 1,
					"external_app": external_app,
					"external_reference": area["external_reference"] if external_app else None,
				}
			).insert(ignore_permissions=True)
		for group_name, sequence in area["groups"]:
			if not frappe.db.exists("AI Form Group", group_name):
				frappe.get_doc(
					{
						"doctype": "AI Form Group",
						"group_name": group_name,
						"target_area": area["area_name"],
						"sequence": sequence,
						"enabled": 1,
					}
				).insert(ignore_permissions=True)
