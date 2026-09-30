import fitz


class PDFAnalyzer:
	"""Read untrusted PDFs as data only; coordinates are PDF points from top-left."""

	def inspect(self, path: str) -> dict:
		document = fitz.open(path)
		pages = []
		widgets = []
		for index, page in enumerate(document):
			text = page.get_text("text")
			pages.append(
				{"page": index + 1, "width": page.rect.width, "height": page.rect.height, "text": text}
			)
			for widget in page.widgets() or []:
				rect = widget.rect
				widgets.append(
					{
						"name": widget.field_name,
						"type": str(widget.field_type_string),
						"page": index + 1,
						"rect": {"x": rect.x0, "y": rect.y0, "width": rect.width, "height": rect.height},
					}
				)
		document.close()
		return {"pages": pages, "widgets": widgets, "has_text": any(page["text"].strip() for page in pages)}
