"""Turn an uploaded client sheet into a draft form spec.

Excel and Word sheets are read structurally (cells, merges, widths, shading)
into a draft layout without any AI call; the AI then only decides which boxes
are filled in. A PDF has no reliable structure to read, so the model reads it
directly.
"""

import os

KINDS = {".pdf": "PDF", ".xlsx": "Excel", ".xlsm": "Excel", ".docx": "Word"}
ACCEPTED = tuple(KINDS)


def kind_of(filename: str) -> str | None:
	return KINDS.get(os.path.splitext(filename or "")[1].lower())


def draft(path: str, kind: str) -> dict | None:
	"""A draft spec read straight from the file, or None for a PDF."""
	if kind == "Excel":
		from ai_form_builder.services.extract.xlsx import read_workbook

		return read_workbook(path)
	if kind == "Word":
		from ai_form_builder.services.extract.docx import read_document

		return read_document(path)
	return None
