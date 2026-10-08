import re

import frappe
from frappe import _
from frappe.model import data_fieldtypes, table_fields

ALLOWED_FIELD_TYPES = {
	"Data",
	"Small Text",
	"Text",
	"Long Text",
	"Text Editor",
	"Date",
	"Datetime",
	"Time",
	"Int",
	"Float",
	"Currency",
	"Percent",
	"Select",
	"Check",
	"Link",
	"Dynamic Link",
	"Signature",
	"Attach",
	"Attach Image",
	"Table",
	"Section Break",
	"Column Break",
}
# Fields synced from a Frappe DocType may use any value type Frappe itself
# allows; the narrower set above still governs what AI analysis may suggest.
SYNCED_FIELD_TYPES = ALLOWED_FIELD_TYPES | set(data_fieldtypes) | set(table_fields)
FIELDNAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,139}$")


def sanitize_fieldname(value: str) -> str:
	fieldname = frappe.scrub(value or "")
	if not FIELDNAME_RE.match(fieldname):
		frappe.throw(
			_(
				"Fieldname must begin with a letter and contain only lowercase letters, numbers, and underscores."
			)
		)
	return fieldname


def validate_mapping(field, page_count: int | None = None):
	field.fieldname = sanitize_fieldname(field.fieldname)
	if field.final_fieldtype and field.final_fieldtype not in SYNCED_FIELD_TYPES:
		frappe.throw(_("Unsupported Frappe field type: {0}").format(field.final_fieldtype))
	if field.suggested_fieldtype and field.suggested_fieldtype not in ALLOWED_FIELD_TYPES:
		frappe.throw(_("Unsupported suggested field type: {0}").format(field.suggested_fieldtype))
	if page_count and not 1 <= int(field.page_number or 0) <= page_count:
		frappe.throw(_("Field {0} has an invalid page number.").format(field.label))
	for coordinate in ("x", "y", "width", "height"):
		value = float(getattr(field, coordinate) or 0)
		if value < 0 or (coordinate in {"width", "height"} and value == 0):
			frappe.throw(_("Field {0} has invalid {1}.").format(field.label, coordinate))
	if (
		field.final_fieldtype == "Link"
		and field.link_target
		and not frappe.db.exists("DocType", field.link_target)
	):
		frappe.throw(_("Link target {0} does not exist.").format(field.link_target))
	if field.final_fieldtype == "Select" and not (field.options or "").strip():
		frappe.throw(_("Select field {0} requires options.").format(field.label))
