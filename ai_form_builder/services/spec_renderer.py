"""Print a spec form: HTML laid out like the client's sheet, then wkhtmltopdf.

Every box is a ``<td>`` of a real table row. wkhtmltopdf can split a page only
between table rows (inline-block and floats are atomic to it), so a long grid
flows onto the next page instead of being cut or squeezed.
"""

from html import escape

from ai_form_builder.services import form_spec

BASE_CSS = """
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; color: #000; margin: 0; }
.afb-page { page-break-after: always; }
.afb-page.last { page-break-after: auto; }
table.afb-t { width: 100%; border-collapse: collapse; table-layout: fixed; margin: 0 0 -1px 0; }
table.afb-t td, table.afb-t th { border: 1px solid #000; padding: 2px 4px; vertical-align: top; }
table.afb-t th { background: #e8e8e8; font-weight: bold; text-align: center; vertical-align: middle; }
table.afb-t tr { page-break-inside: avoid; }
thead { display: table-header-group; }
.afb-label { font-weight: normal; }
.afb-value { font-weight: bold; white-space: pre-wrap; }
.afb-grid td { height: 6.5mm; }
.afb-text { margin: 2px 0; white-space: pre-wrap; }
.afb-sign { max-height: 14mm; max-width: 100%; }
.afb-tick { font-family: DejaVu Sans, Arial, sans-serif; }
"""


def _value_html(field: dict | None, value) -> str:
	kind = (field or {}).get("type") or "Data"
	if kind == "Check":
		ticked = str(value or "").strip().lower() in ("1", "true", "yes", "on")
		return f'<span class="afb-tick">{"&#9745;" if ticked else "&#9744;"}</span>'
	if value in (None, ""):
		return ""
	if kind == "Signature":
		text = str(value)
		if text.startswith("data:image/") and ";base64," in text and '"' not in text:
			return f'<img class="afb-sign" src="{text}">'
		return ""
	if kind in ("Date", "Datetime"):
		value = _format_date(value, kind)
	return f'<span class="afb-value">{escape(str(value))}</span>'


def _format_date(value, kind):
	"""Dates print in the site's date format (as the user typed them)."""
	try:
		from frappe.utils import format_datetime, formatdate

		return formatdate(value) if kind == "Date" else format_datetime(value)
	except Exception:
		return value


def _style(cell: dict) -> str:
	parts = []
	if cell.get("bold"):
		parts.append("font-weight:bold")
	if cell.get("align"):
		parts.append(f"text-align:{cell['align']}")
	if cell.get("bg"):
		parts.append(f"background:{cell['bg']}")
	return f' style="{";".join(parts)}"' if parts else ""


def _cell_html(cell: dict, fields: dict, values: dict) -> str:
	spans = "".join(f' {key}="{cell[key]}"' for key in ("colspan", "rowspan") if cell.get(key))
	inner = escape(cell.get("text") or "")
	if cell.get("field"):
		field = fields.get(cell["field"])
		value = _value_html(field, values.get(cell["field"]))
		if inner and value:
			inner = f'<span class="afb-label">{inner}</span> {value}'
		elif value:
			inner = value
	return f"<td{spans}{_style(cell)}>{inner}</td>"


def _colgroup(widths) -> str:
	if not widths:
		return ""
	total = sum(widths) or 1
	return (
		"<colgroup>" + "".join(f'<col style="width:{w * 100 / total:.3f}%">' for w in widths) + "</colgroup>"
	)


def _table_html(block: dict, fields: dict, values: dict) -> str:
	rows = "".join(
		"<tr>" + "".join(_cell_html(cell, fields, values) for cell in row) + "</tr>"
		for row in block.get("rows") or ()
	)
	return f'<table class="afb-t">{_colgroup(block.get("widths"))}<tbody>{rows}</tbody></table>'


def grid_lines(grid: dict, rows: list[dict]) -> list[dict]:
	"""The lines the sheet prints: pre-printed rows, then entered rows, then blanks.

	Entered rows carry the pre-printed text in the same positions, so a
	checklist line keeps its printed description beside the inspector's answer.
	"""
	lines = [dict(row) for row in rows or ()]
	fixed = grid.get("fixed_rows") or []
	for index, printed in enumerate(fixed):
		if index < len(lines):
			lines[index] = {**lines[index], **printed}
		else:
			lines.append(dict(printed))
	while len(lines) < (grid.get("blank_rows") or 0):
		lines.append({})
	return lines


def _grid_html(grid: dict | None, rows: list[dict]) -> str:
	if not grid:
		return ""
	columns = grid.get("columns") or []
	head = "".join(f"<th>{escape(column.get('label') or '')}</th>" for column in columns)
	fixed = grid.get("fixed_rows") or []

	def cell(index, column, line):
		# Pre-printed text prints like the sheet's own captions; answers print bold.
		if index < len(fixed) and column["name"] in fixed[index]:
			return escape(str(fixed[index][column["name"]]))
		return _value_html(column, line.get(column["name"]))

	body = "".join(
		"<tr>" + "".join(f"<td>{cell(index, column, line)}</td>" for column in columns) + "</tr>"
		for index, line in enumerate(grid_lines(grid, rows))
	)
	widths = [column.get("width") or 10 for column in columns]
	return (
		f'<table class="afb-t afb-grid">{_colgroup(widths)}'
		f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
	)


def _block_html(block: dict, fields: dict, grids: dict, values: dict, grid_rows: dict) -> str:
	kind = block.get("type")
	if kind == "table":
		return _table_html(block, fields, values)
	if kind == "grid":
		return _grid_html(grids.get(block.get("grid")), grid_rows.get(block.get("grid")) or [])
	if kind == "text":
		style = []
		if block.get("bold"):
			style.append("font-weight:bold")
		if block.get("align"):
			style.append(f"text-align:{block['align']}")
		if block.get("size_pt"):
			style.append(f"font-size:{block['size_pt']}pt")
		return f'<div class="afb-text" style="{";".join(style)}">{escape(block.get("text") or "")}</div>'
	if kind == "spacer":
		return f'<div style="height:{block.get("height_mm") or 4}mm"></div>'
	return ""


def render_html(spec: dict, values: dict, grid_rows: dict) -> str:
	"""The whole sheet as one HTML document.

	``values`` maps field name -> value; ``grid_rows`` maps grid name -> list of
	``{column: value}`` rows.
	"""
	fields = form_spec.field_map(spec)
	grids = form_spec.grid_map(spec)
	pages = spec.get("pages") or []
	out = []
	for number, page in enumerate(pages):
		inner = "".join(_block_html(b, fields, grids, values, grid_rows) for b in page.get("blocks") or ())
		cls = "afb-page" + (" last" if number == len(pages) - 1 else "")
		out.append(f'<div class="{cls}">{inner}</div>')
	size = (spec.get("page") or {}).get("font_size_pt") or 9
	return (
		"<!DOCTYPE html><html><head><meta charset='utf-8'>"
		f"<style>{BASE_CSS} body{{font-size:{size}pt;}}</style></head>"
		f"<body>{''.join(out)}</body></html>"
	)


def sample_data(spec: dict) -> tuple[dict, dict]:
	"""Values and grid rows the review preview prints."""
	values = {field["name"]: form_spec.sample_value(field) for field in spec.get("fields") or ()}
	grid_rows = {}
	for grid in spec.get("grids") or ():
		fixed = grid.get("fixed_rows") or []
		rows = []
		for index in range(max(len(fixed), 2)):
			printed = fixed[index] if index < len(fixed) else {}
			rows.append(
				{
					column["name"]: form_spec.sample_value(column)
					for column in grid.get("columns") or ()
					if column["name"] not in printed
				}
			)
		grid_rows[grid["name"]] = rows
	return values, grid_rows


def pdf_options(spec: dict) -> dict:
	page = spec.get("page") or {}
	top, right, bottom, left = page.get("margins_mm") or [10, 10, 10, 10]
	return {
		"page-size": page.get("size") or "A4",
		"orientation": "Landscape" if page.get("orientation") == "landscape" else "Portrait",
		"margin-top": f"{top}mm",
		"margin-right": f"{right}mm",
		"margin-bottom": f"{bottom}mm",
		"margin-left": f"{left}mm",
		"encoding": "UTF-8",
	}


def render_pdf(spec: dict, values: dict, grid_rows: dict) -> bytes:
	from frappe.utils.pdf import get_pdf

	return get_pdf(render_html(spec, values, grid_rows), options=pdf_options(spec))
