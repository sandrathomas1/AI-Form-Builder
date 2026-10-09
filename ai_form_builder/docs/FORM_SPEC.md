# Form spec

A **spec form** is a form that is data: one JSON document stored on its
`AI Form Template` (`spec_json`). Publishing it creates no DocType, no Client
Script and needs no migrate, so forms made on a production site never have to
go through git. Records of every spec form are rows of the one
`AI Form Record` DocType (`values` + `rows` child tables).

Code: `services/form_spec.py` (format, validation, LLM schema),
`services/spec_renderer.py` (print), `services/spec_service.py` (store,
analyse, publish, export/import), `services/extract/` (PDF / Excel / Word).

## Flow

1. Form Library panel → **Create from the client's sheet (AI)** → upload PDF,
   `.xlsx` or `.docx`.
2. Analysis (background, `long` queue): Excel/Word cells are read exactly
   (text, merges, widths, shading) into a draft; the model then decides which
   boxes are filled in. A PDF is read by the model directly. Without an AI key
   an Excel/Word draft is still usable; a PDF needs a key.
3. `/app/afb-form-review/<form>`: our print (sample values) beside the client
   sheet; edit fields, grids, layout JSON; **Publish**.
4. `/app/afb-form?template=<form>&reference_name=<project>`: fill a record;
   `/app/afb-form/<record>` reopens it; **Download PDF** files the print on the
   record.

AI key: AI Form Builder Settings (Anthropic or OpenAI); when blank, the enabled
provider row of Docuflow's `DCMS LLM Provider Config` is read (no Docuflow code
is imported).

## Format

```json
{
  "title": "CONCRETE POUR CHECKLIST",
  "page": {"size": "A4", "orientation": "portrait", "margins_mm": [10, 10, 10, 10], "font_size_pt": 9},
  "fields": [
    {"name": "project_no", "label": "Project No.", "type": "Data", "mandatory": true, "section": "Header"},
    {"name": "result", "label": "Result", "type": "Select", "options": ["Accepted", "Rejected"]}
  ],
  "grids": [
    {"name": "checks", "label": "Checks", "section": "Checklist",
     "columns": [{"name": "item", "label": "Item", "type": "Data", "width": 70},
                 {"name": "ok", "label": "OK", "type": "Check", "width": 30}],
     "fixed_rows": [{"item": "Formwork clean"}], "blank_rows": 6, "allow_add": true}
  ],
  "pages": [{"blocks": [
    {"type": "text", "text": "CONCRETE POUR CHECKLIST", "bold": true, "align": "center", "size_pt": 12},
    {"type": "table", "widths": [25, 75], "rows": [[{"text": "Project No.", "bold": true}, {"field": "project_no"}]]},
    {"type": "grid", "grid": "checks"},
    {"type": "spacer", "height_mm": 4}
  ]}]
}
```

- Field / column types: Data, Text, Int, Float, Date, Time, Datetime, Check,
  Select, Signature.
- Cell keys: `text`, `field`, `colspan`, `rowspan`, `bold`, `align`
  (left/center/right), `bg` (hex).
- `fixed_rows` are printed on the blank sheet; their text is re-imposed on
  save and cannot be changed from the form.
- A record keeps `spec_snapshot`: a later revision never changes how an old
  record prints.
- Move a form between sites with **Export form (JSON)** on the review page and
  `api/spec_forms.import_spec`.

Forms created before spec forms keep `storage_mode = DocType` and the old
DocType-per-form path unchanged.
