from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from ai_form_builder.services.pdf_analyzer import PDFAnalyzer


def test_acroform_analysis_uses_existing_widgets_without_ai():
	with TemporaryDirectory() as directory:
		path = Path(directory) / "form.pdf"
		pdf = fitz.open()
		page = pdf.new_page()
		widget = fitz.Widget()
		widget.field_name = "company"
		widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
		widget.rect = fitz.Rect(10, 20, 180, 40)
		page.add_widget(widget)
		pdf.save(path)
		pdf.close()
		inspection = PDFAnalyzer().inspect(str(path))
		analysis = PDFAnalyzer().acroform_analysis(inspection)
		assert analysis["fields"][0]["fieldname"] == "company"
		assert analysis["fields"][0]["rect"]["x"] == 10
