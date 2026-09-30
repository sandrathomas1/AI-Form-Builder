from ai_form_builder.utils.validation import ALLOWED_FIELD_TYPES, sanitize_fieldname


def validate_analysis(payload: dict) -> dict:
	if not isinstance(payload, dict) or not isinstance(payload.get("document"), dict):
		raise ValueError("Analysis must contain a document object")
	fields = payload.get("fields", [])
	if not isinstance(fields, list):
		raise ValueError("Analysis fields must be a list")
	for item in fields:
		if not isinstance(item, dict):
			raise ValueError("Each analysis field must be an object")
		fieldtype = item.get("suggested_fieldtype", "Data")
		if fieldtype not in ALLOWED_FIELD_TYPES:
			raise ValueError(f"Unsupported field type: {fieldtype}")
		item["fieldname"] = sanitize_fieldname(item.get("fieldname") or item.get("label"))
		rect = item.get("rect", {})
		if not all(
			isinstance(rect.get(key), int | float) and rect[key] >= 0 for key in ("x", "y", "width", "height")
		):
			raise ValueError("Field rectangle must contain non-negative numeric coordinates")
		if (
			rect["width"] == 0
			or rect["height"] == 0
			or not isinstance(item.get("page"), int)
			or item["page"] < 1
		):
			raise ValueError("Field rectangle and page must be valid")
	return payload
