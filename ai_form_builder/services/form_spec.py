"""The form spec: one JSON document that is the whole form.

A spec form needs no DocType. Its fields, its grids (repeating rows) and the
printed page are all described here; records of every spec form are stored in
the one generic DocType ``AI Form Record``. The format is documented in
``ai_form_builder/docs/FORM_SPEC.md``.

Shape (every key below is the complete vocabulary; anything else is dropped):

	{
	  "title": "Concrete Pour Checklist",
	  "page": {"size": "A4", "orientation": "portrait", "margins_mm": [10, 10, 10, 10], "font_size_pt": 9},
	  "fields": [{"name", "label", "type", "options", "mandatory", "default", "sample", "section"}],
	  "grids": [{"name", "label", "section", "columns": [{"name", "label", "type", "width", "options"}],
	             "fixed_rows": [{"<column>": "pre-printed text"}], "blank_rows": 5, "allow_add": true}],
	  "pages": [{"blocks": [
	      {"type": "table", "widths": [30, 70], "rows": [[{"text", "field", "colspan", "rowspan", "bold", "align", "bg"}]]},
	      {"type": "grid", "grid": "<grid name>"},
	      {"type": "text", "text": "...", "bold": true, "align": "center", "size_pt": 12},
	      {"type": "spacer", "height_mm": 4}
	  ]}]
	}
"""

import copy
import re

FIELD_TYPES = ("Data", "Text", "Int", "Float", "Date", "Time", "Datetime", "Check", "Select", "Signature")
BLOCK_TYPES = ("table", "grid", "text", "spacer")
ALIGNS = ("left", "center", "right")
PAGE_SIZES = ("A4", "A3", "Letter", "Legal")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,61}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
DEFAULT_SECTION = "Details"
# Frappe field type each spec type is shown as in Desk and in project configuration.
FRAPPE_TYPES = {
	"Data": "Data",
	"Text": "Small Text",
	"Int": "Int",
	"Float": "Float",
	"Date": "Date",
	"Time": "Time",
	"Datetime": "Datetime",
	"Check": "Check",
	"Select": "Select",
	"Signature": "Signature",
}


class SpecError(ValueError):
	"""The spec cannot be used; ``errors`` lists every problem found."""

	def __init__(self, errors):
		self.errors = list(errors)
		super().__init__("; ".join(self.errors[:10]) + (" …" if len(self.errors) > 10 else ""))


def scrub(value: str) -> str:
	"""A safe field name from any label (``"Inspected By:"`` -> ``inspected_by``)."""
	name = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
	if not name:
		return ""
	if not name[0].isalpha():
		name = "f_" + name
	return name[:62]


def _text(value):
	if value is None:
		return ""
	return str(value)


def _int(value, default=None, low=None, high=None):
	try:
		number = int(value)
	except (TypeError, ValueError):
		return default
	if low is not None and number < low:
		return default
	if high is not None and number > high:
		return high
	return number


def _options(value):
	if isinstance(value, str):
		value = value.splitlines()
	if not isinstance(value, list | tuple):
		return []
	return [str(item).strip() for item in value if str(item or "").strip()]


def _cell(cell):
	if cell is None:
		return {"text": ""}
	if not isinstance(cell, dict):
		return {"text": _text(cell)}
	out = {}
	if cell.get("text") not in (None, ""):
		out["text"] = _text(cell["text"])
	if cell.get("field"):
		out["field"] = str(cell["field"])
	for key in ("colspan", "rowspan"):
		span = _int(cell.get(key), 1, 1, 50)
		if span and span > 1:
			out[key] = span
	if cell.get("bold"):
		out["bold"] = True
	if cell.get("align") in ALIGNS:
		out["align"] = cell["align"]
	if cell.get("bg") and HEX_RE.match(str(cell["bg"])):
		out["bg"] = cell["bg"]
	if "text" not in out and "field" not in out:
		out["text"] = ""
	return out


def _block(block):
	if not isinstance(block, dict):
		return None
	kind = block.get("type")
	if kind == "table":
		rows = [[_cell(cell) for cell in row] for row in block.get("rows") or () if isinstance(row, list)]
		out = {"type": "table", "rows": [row for row in rows if row]}
		widths = [w for w in (block.get("widths") or ()) if isinstance(w, int | float) and w > 0]
		if widths:
			out["widths"] = widths
		return out
	if kind == "grid":
		return {"type": "grid", "grid": str(block.get("grid") or "")}
	if kind == "text":
		out = {"type": "text", "text": _text(block.get("text"))}
		if block.get("bold"):
			out["bold"] = True
		if block.get("align") in ALIGNS:
			out["align"] = block["align"]
		size = block.get("size_pt")
		if isinstance(size, int | float) and 5 <= size <= 30:
			out["size_pt"] = size
		return out
	if kind == "spacer":
		height = block.get("height_mm")
		return {
			"type": "spacer",
			"height_mm": height if isinstance(height, int | float) and 0 < height <= 100 else 4,
		}
	return None


def normalise(raw: dict) -> dict:
	"""Keep only the documented vocabulary, in a stable shape.

	Lenient on purpose: AI output and hand edits both pass through here before
	``validate`` decides whether the result is usable.
	"""
	raw = copy.deepcopy(raw) if isinstance(raw, dict) else {}
	page = raw.get("page") if isinstance(raw.get("page"), dict) else {}
	margins = page.get("margins_mm")
	if not (
		isinstance(margins, list) and len(margins) == 4 and all(isinstance(m, int | float) for m in margins)
	):
		margins = [10, 10, 10, 10]
	spec = {
		"title": _text(raw.get("title")).strip(),
		"page": {
			"size": page.get("size") if page.get("size") in PAGE_SIZES else "A4",
			"orientation": "landscape" if page.get("orientation") == "landscape" else "portrait",
			"margins_mm": [max(0, min(40, m)) for m in margins],
			"font_size_pt": page.get("font_size_pt")
			if isinstance(page.get("font_size_pt"), int | float) and 5 <= page["font_size_pt"] <= 16
			else 9,
		},
		"fields": [],
		"grids": [],
		"pages": [],
	}
	for field in raw.get("fields") or ():
		if not isinstance(field, dict):
			continue
		name = field.get("name") or scrub(field.get("label"))
		item = {
			"name": str(name or ""),
			"label": _text(field.get("label")).strip() or str(name or ""),
			"type": field.get("type") if field.get("type") in FIELD_TYPES else "Data",
		}
		options = _options(field.get("options"))
		if item["type"] == "Select":
			item["options"] = options
		for key in ("default", "sample", "section"):
			if field.get(key) not in (None, ""):
				item[key] = _text(field[key])
		if field.get("mandatory"):
			item["mandatory"] = True
		spec["fields"].append(item)
	for grid in raw.get("grids") or ():
		if not isinstance(grid, dict):
			continue
		name = grid.get("name") or scrub(grid.get("label"))
		columns = []
		for column in grid.get("columns") or ():
			if not isinstance(column, dict):
				continue
			cname = column.get("name") or scrub(column.get("label"))
			col = {
				"name": str(cname or ""),
				"label": _text(column.get("label")).strip() or str(cname or ""),
				"type": column.get("type") if column.get("type") in FIELD_TYPES else "Data",
				"width": column.get("width")
				if isinstance(column.get("width"), int | float) and column["width"] > 0
				else 10,
			}
			if col["type"] == "Select":
				col["options"] = _options(column.get("options"))
			columns.append(col)
		fixed = []
		for row in grid.get("fixed_rows") or ():
			if isinstance(row, dict):
				fixed.append({str(k): _text(v) for k, v in row.items() if v not in (None, "")})
		item = {
			"name": str(name or ""),
			"label": _text(grid.get("label")).strip() or str(name or ""),
			"columns": columns,
			"fixed_rows": fixed,
			"blank_rows": _int(grid.get("blank_rows"), 0, 0, 200) or 0,
			"allow_add": grid.get("allow_add") is not False,
		}
		if grid.get("section"):
			item["section"] = _text(grid["section"])
		spec["grids"].append(item)
	for page in raw.get("pages") or ():
		blocks = page.get("blocks") if isinstance(page, dict) else page
		if not isinstance(blocks, list):
			continue
		spec["pages"].append({"blocks": [b for b in (_block(block) for block in blocks) if b]})
	return spec


def validate(spec: dict) -> list[str]:
	"""Every reason the spec cannot be published; an empty list means usable."""
	errors = []
	if not spec.get("title"):
		errors.append("The form has no title.")
	names = set()
	for field in spec.get("fields") or ():
		name = field.get("name") or ""
		if not NAME_RE.match(name):
			errors.append(f"Field name {name!r} must start with a letter and use only a-z, 0-9 and _.")
		elif name in names:
			errors.append(f"Field name {name!r} is used twice.")
		names.add(name)
		if field.get("type") == "Select" and not field.get("options"):
			errors.append(f"Select field {name!r} has no options.")
	grid_names = set()
	for grid in spec.get("grids") or ():
		name = grid.get("name") or ""
		if not NAME_RE.match(name):
			errors.append(f"Grid name {name!r} must start with a letter and use only a-z, 0-9 and _.")
		elif name in names or name in grid_names:
			errors.append(f"Grid name {name!r} is already used by a field or another grid.")
		grid_names.add(name)
		if not grid.get("columns"):
			errors.append(f"Grid {name!r} has no columns.")
		column_names = set()
		for column in grid.get("columns") or ():
			cname = column.get("name") or ""
			if not NAME_RE.match(cname):
				errors.append(f"Column {cname!r} of grid {name!r} has an invalid name.")
			elif cname in column_names:
				errors.append(f"Column {cname!r} appears twice in grid {name!r}.")
			column_names.add(cname)
			if column.get("type") == "Select" and not column.get("options"):
				errors.append(f"Select column {cname!r} of grid {name!r} has no options.")
		for row in grid.get("fixed_rows") or ():
			unknown = set(row) - column_names
			if unknown:
				errors.append(
					f"Pre-printed row of grid {name!r} names unknown columns: {', '.join(sorted(unknown))}."
				)
	if not spec.get("pages"):
		errors.append("The form has no printed page.")
	for number, page in enumerate(spec.get("pages") or (), 1):
		if not page.get("blocks"):
			errors.append(f"Page {number} is empty.")
		for block in page.get("blocks") or ():
			if block["type"] == "grid" and block.get("grid") not in grid_names:
				errors.append(f"Page {number} prints grid {block.get('grid')!r}, which is not defined.")
			if block["type"] == "table":
				if not block.get("rows"):
					errors.append(f"Page {number} has a table with no rows.")
				for row in block.get("rows") or ():
					for cell in row:
						if cell.get("field") and cell["field"] not in names:
							errors.append(
								f"Page {number} prints field {cell['field']!r}, which is not defined."
							)
	return errors


def clean(raw: dict) -> dict:
	"""Normalise and validate; raise SpecError when the spec is unusable."""
	spec = normalise(raw)
	errors = validate(spec)
	if errors:
		raise SpecError(errors)
	return spec


def field_map(spec: dict) -> dict:
	return {field["name"]: field for field in spec.get("fields") or ()}


def grid_map(spec: dict) -> dict:
	return {grid["name"]: grid for grid in spec.get("grids") or ()}


def placed_fields(spec: dict) -> set:
	"""Names of the fields the printed page shows."""
	placed = set()
	for page in spec.get("pages") or ():
		for block in page.get("blocks") or ():
			for row in block.get("rows") or ():
				for cell in row:
					if cell.get("field"):
						placed.add(cell["field"])
	return placed


def form_sections(spec: dict) -> list[dict]:
	"""The entry form: cards in the order the sheet first uses them.

	Each card is ``{"label", "fields": [names], "grids": [names]}``. A field or
	grid without a section joins the default card.
	"""
	sections, by_label = [], {}

	def card(label):
		label = label or DEFAULT_SECTION
		if label not in by_label:
			by_label[label] = {"label": label, "fields": [], "grids": []}
			sections.append(by_label[label])
		return by_label[label]

	for field in spec.get("fields") or ():
		card(field.get("section"))["fields"].append(field["name"])
	for grid in spec.get("grids") or ():
		card(grid.get("section"))["grids"].append(grid["name"])
	return sections


def sample_value(field: dict) -> str:
	"""What the review preview prints in a box nobody has filled yet."""
	if field.get("sample"):
		return field["sample"]
	kind = field.get("type")
	if kind == "Date":
		return "2026-01-31"
	if kind == "Time":
		return "09:30"
	if kind == "Datetime":
		return "2026-01-31 09:30"
	if kind in ("Int", "Float"):
		return "1"
	if kind == "Check":
		return "1"
	if kind == "Select":
		return (field.get("options") or [""])[0]
	if kind == "Signature":
		return ""
	return field.get("label") or ""


# JSON schema handed to the model (structured outputs). Non-recursive and with
# every property required (nullable where optional), as structured outputs need.
def _nullable(kind, **extra):
	return {"anyOf": [{"type": kind, **extra}, {"type": "null"}]}


def _object(properties):
	return {
		"type": "object",
		"properties": properties,
		"required": list(properties),
		"additionalProperties": False,
	}


_TYPE_ENUM = {"type": "string", "enum": list(FIELD_TYPES)}
_CELL = _object(
	{
		"text": _nullable("string"),
		"field": _nullable("string"),
		"colspan": _nullable("integer"),
		"rowspan": _nullable("integer"),
		"bold": _nullable("boolean"),
		"align": {"anyOf": [{"type": "string", "enum": list(ALIGNS)}, {"type": "null"}]},
		"bg": _nullable("string"),
	}
)
_FIXED_CELL = _object({"column": {"type": "string"}, "text": {"type": "string"}})
LLM_SCHEMA = _object(
	{
		"title": {"type": "string"},
		"page": _object(
			{
				"size": {"type": "string", "enum": list(PAGE_SIZES)},
				"orientation": {"type": "string", "enum": ["portrait", "landscape"]},
				"margins_mm": {"type": "array", "items": {"type": "number"}},
				"font_size_pt": {"type": "number"},
			}
		),
		"fields": {
			"type": "array",
			"items": _object(
				{
					"name": {"type": "string"},
					"label": {"type": "string"},
					"type": _TYPE_ENUM,
					"options": {"type": "array", "items": {"type": "string"}},
					"mandatory": {"type": "boolean"},
					"sample": {"type": "string"},
					"section": {"type": "string"},
				}
			),
		},
		"grids": {
			"type": "array",
			"items": _object(
				{
					"name": {"type": "string"},
					"label": {"type": "string"},
					"section": {"type": "string"},
					"columns": {
						"type": "array",
						"items": _object(
							{
								"name": {"type": "string"},
								"label": {"type": "string"},
								"type": _TYPE_ENUM,
								"width": {"type": "number"},
								"options": {"type": "array", "items": {"type": "string"}},
							}
						),
					},
					# Rows printed on the blank sheet (e.g. checklist items),
					# as lists of column/text pairs.
					"fixed_rows": {"type": "array", "items": {"type": "array", "items": _FIXED_CELL}},
					"blank_rows": {"type": "integer"},
					"allow_add": {"type": "boolean"},
				}
			),
		},
		"pages": {
			"type": "array",
			"items": _object(
				{
					"blocks": {
						"type": "array",
						"items": _object(
							{
								"type": {"type": "string", "enum": list(BLOCK_TYPES)},
								"widths": {
									"anyOf": [
										{"type": "array", "items": {"type": "number"}},
										{"type": "null"},
									]
								},
								"rows": {
									"anyOf": [
										{"type": "array", "items": {"type": "array", "items": _CELL}},
										{"type": "null"},
									]
								},
								"grid": _nullable("string"),
								"text": _nullable("string"),
								"bold": _nullable("boolean"),
								"align": {
									"anyOf": [{"type": "string", "enum": list(ALIGNS)}, {"type": "null"}]
								},
								"size_pt": _nullable("number"),
								"height_mm": _nullable("number"),
							}
						),
					}
				}
			),
		},
	}
)


def from_llm(payload: dict) -> dict:
	"""Turn the model's schema-shaped answer into the stored spec shape."""
	payload = copy.deepcopy(payload or {})
	for grid in payload.get("grids") or ():
		rows = []
		for row in grid.get("fixed_rows") or ():
			if isinstance(row, list):
				rows.append({cell.get("column"): cell.get("text") for cell in row if isinstance(cell, dict)})
			elif isinstance(row, dict):
				rows.append(row)
		grid["fixed_rows"] = rows
	for page in payload.get("pages") or ():
		for block in page.get("blocks") or () if isinstance(page, dict) else ():
			for key in [k for k, v in block.items() if v is None]:
				del block[key]
			for row in block.get("rows") or ():
				for cell in row:
					for key in [k for k, v in cell.items() if v is None]:
						del cell[key]
	return normalise(payload)
