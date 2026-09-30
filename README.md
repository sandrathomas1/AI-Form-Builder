### AI Form Builder

AI Form Builder is a standalone Frappe app that converts existing PDF forms into digital forms using AI. It analyzes untrusted PDF templates, provides reviewable data-only field mappings, generates custom DocTypes, and renders saved values onto a fresh copy of the original PDF.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app ai_form_builder
```

PyMuPDF is declared in `pyproject.toml`. Configure the OpenAI model and API key in **AI Form Builder Settings**; the password is never returned to browser code. Coordinates use PDF points with a top-left origin consistently for extraction, mapping, and rendering. The uploaded source PDF is never modified.

### Current MVP workflow

1. Create an **AI Form Template** and attach a PDF.
2. Use **Analyze PDF**. Existing AcroForm widgets are mapped locally first; flat PDFs are rendered only in memory and sent to the configured vision-capable OpenAI model.
3. Use **Review Mapping** to review/edit detected field metadata and coordinates, then save and approve it.
4. Generate a new DocType, or select an existing DocType to map to it.
5. Generate a private completed PDF through the API after saving a document.

Register/report pagination, repeating child-table generation, OCR fallback, and drag/resize mapping are planned extensions, not part of this MVP.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/ai_form_builder
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
