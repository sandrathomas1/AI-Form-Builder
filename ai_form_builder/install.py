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


def link_initial_area(area_name, external_app, external_reference, routes):
	"""Point a seeded area at the external app's routes, filling blanks only.

	An administrator who already set routes keeps them.
	"""
	doc = frappe.get_doc("AI Form Area", area_name)
	if doc.external_route_prefixes:
		return
	reference = doc.external_reference or external_reference
	if (doc.external_app and doc.external_app != external_app) or not routes.get(reference):
		return
	doc.external_app = external_app
	doc.external_reference = reference
	doc.external_route_prefixes = routes[reference]
	doc.show_in_external_app = 1
	doc.save(ignore_permissions=True)


def seed_initial_areas():
	"""Create missing initial areas/groups; never overwrite what an admin changed."""
	from ai_form_builder.integrations import docuflow

	external_app = docuflow.APP if docuflow.is_installed() else None
	routes = docuflow.DEFAULT_AREA_ROUTES if external_app else {}
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
					"show_in_external_app": 1 if routes.get(area["external_reference"]) else 0,
					"external_route_prefixes": routes.get(area["external_reference"]),
				}
			).insert(ignore_permissions=True)
		elif routes.get(area["external_reference"]):
			link_initial_area(area["area_name"], external_app, area["external_reference"], routes)
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
