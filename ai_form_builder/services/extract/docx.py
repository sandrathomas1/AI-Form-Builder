"""Word sheet -> draft spec, read from the document XML (no extra library)."""

import zipfile
from xml.etree import ElementTree

from ai_form_builder.services.extract.fields import mark_fields

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _attr(element, path, name="val"):
	found = element.find(path) if element is not None else None
	return found.get(W + name) if found is not None else None


def _paragraph_text(paragraph) -> str:
	parts = []
	for node in paragraph.iter():
		if node.tag == W + "t" and node.text:
			parts.append(node.text)
		elif node.tag == W + "tab":
			parts.append("\t")
		elif node.tag in (W + "br", W + "cr") and node.get(W + "type") != "page":
			parts.append("\n")
	return "".join(parts)


def _is_bold(paragraph) -> bool:
	runs = [
		run for run in paragraph.iter(W + "r") if "".join(t.text or "" for t in run.iter(W + "t")).strip()
	]
	return bool(runs) and all(run.find(f"{W}rPr/{W}b") is not None for run in runs)


def _align(paragraph):
	value = _attr(paragraph, f"{W}pPr/{W}jc")
	return {"center": "center", "right": "right", "end": "right"}.get(value)


def _page_break(paragraph) -> bool:
	return any(br.get(W + "type") == "page" for br in paragraph.iter(W + "br"))


def _table(table) -> dict:
	widths = [int(col.get(W + "w") or 0) for col in table.findall(f"{W}tblGrid/{W}gridCol")]
	grid_rows = []
	open_merges = {}
	for tr in table.findall(W + "tr"):
		row, column = [], 0
		for tc in tr.findall(W + "tc"):
			properties = tc.find(W + "tcPr")
			span = int(_attr(properties, W + "gridSpan") or 1)
			merge = properties.find(W + "vMerge") if properties is not None else None
			if merge is not None and merge.get(W + "val") != "restart":
				anchor = open_merges.get(column)
				if anchor is not None:
					anchor["rowspan"] = anchor.get("rowspan", 1) + 1
				column += span
				continue
			paragraphs = tc.findall(W + "p")
			cell = {"text": "\n".join(_paragraph_text(p) for p in paragraphs).strip()}
			if span > 1:
				cell["colspan"] = span
			if paragraphs and _is_bold(paragraphs[0]):
				cell["bold"] = True
			align = _align(paragraphs[0]) if paragraphs else None
			if align:
				cell["align"] = align
			fill = _attr(properties, W + "shd", "fill")
			if fill and fill.lower() not in ("auto", "ffffff") and len(fill) == 6:
				cell["bg"] = f"#{fill.upper()}"
			if merge is not None:
				open_merges[column] = cell
			else:
				open_merges.pop(column, None)
			row.append(cell)
			column += span
		if row:
			grid_rows.append(row)
	block = {"type": "table", "rows": grid_rows}
	if widths and all(widths):
		block["widths"] = widths
	return block


def read_document(path: str) -> dict:
	with zipfile.ZipFile(path) as archive:
		root = ElementTree.fromstring(archive.read("word/document.xml"))
	body = root.find(W + "body")
	pages, blocks, title = [], [], ""
	landscape = _attr(body, f"{W}sectPr/{W}pgSz", "orient") == "landscape"
	for element in list(body) if body is not None else ():
		if element.tag == W + "tbl":
			blocks.append(_table(element))
		elif element.tag == W + "p":
			text = _paragraph_text(element).strip()
			if text:
				block = {"type": "text", "text": text}
				if _is_bold(element):
					block["bold"] = True
					title = title or text
				align = _align(element)
				if align:
					block["align"] = align
				blocks.append(block)
			if _page_break(element) and blocks:
				pages.append({"blocks": blocks})
				blocks = []
	if blocks:
		pages.append({"blocks": blocks})
	spec = {
		"title": title,
		"page": {"size": "A4", "orientation": "landscape" if landscape else "portrait"},
		"fields": [],
		"grids": [],
		"pages": pages,
	}
	return mark_fields(spec)
