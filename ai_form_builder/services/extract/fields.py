"""Shared heuristics: which boxes of a ruled sheet are filled in.

Used for Excel and Word drafts so a form works even before (or without) the
AI pass: an empty box to the right of a caption becomes a field named after
the caption, and a caption ending in underscores or dots holds its own field.
"""

import re

from ai_form_builder.services.form_spec import scrub

BLANK_TAIL = re.compile(r"[\s:]*[_.…]{3,}\s*$")


def guess_type(label: str) -> str:
	text = (label or "").lower()
	if re.search(r"\bsign(ature|ed)?\b", text):
		return "Signature"
	if re.search(r"\btime\b", text) and "date" not in text:
		return "Time"
	if re.search(r"\bdate\b|\bdated\b", text):
		return "Date"
	if re.search(r"\b(remarks?|comments?|description|observations?|details)\b", text):
		return "Text"
	return "Data"


def _unique(name: str, used: set) -> str:
	base = name or "field"
	candidate, number = base, 2
	while candidate in used:
		candidate = f"{base[:58]}_{number}"
		number += 1
	used.add(candidate)
	return candidate


def mark_fields(spec: dict) -> dict:
	"""Add fields for the empty boxes of every table block, in reading order."""
	used = {field["name"] for field in spec.get("fields") or ()}
	for page in spec.get("pages") or ():
		for block in page.get("blocks") or ():
			if block.get("type") != "table":
				continue
			for row in block.get("rows") or ():
				caption = None
				for cell in row:
					text = (cell.get("text") or "").strip()
					if cell.get("field"):
						caption = None
						continue
					if text and BLANK_TAIL.search(text):
						label = BLANK_TAIL.sub("", text).strip().rstrip(":").strip()
						if label:
							name = _unique(scrub(label), used)
							spec["fields"].append({"name": name, "label": label, "type": guess_type(label)})
							cell["text"] = label + ":"
							cell["field"] = name
							caption = None
							continue
					if text:
						# A shaded box is a column heading, not a caption for the box beside it.
						caption = None if cell.get("bg") else text
						continue
					if caption and not cell.get("bg"):
						label = caption.rstrip(":").strip()
						name = _unique(scrub(label), used)
						spec["fields"].append({"name": name, "label": label, "type": guess_type(label)})
						cell["field"] = name
						cell.pop("text", None)
						caption = None
	return spec
