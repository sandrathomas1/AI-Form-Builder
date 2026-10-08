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

### Form Library

Every form is an **AI Form Template** pointing at one Frappe DocType. Open **Forms** and use **New Form**:

1. **Create with AI from PDF**: the existing workflow: attach the PDF, **Analyze PDF**, **Review Mapping**, **Approve Mapping**, **Generate DocType**. AcroForm PDFs are mapped locally without an AI call.
2. **Create Manually with Frappe**: enter the form name, code, area, group, description, *Is Submittable*, *Allow Attachments* (adds an Attachment field) and *Project Configurable*. A Custom DocType is created (no source files, no developer mode) and Frappe's own Form Builder opens. Add fields there and save. Then **Form → Sync Fields** in the library.
3. **Use Existing DocType**: register any existing DocType. Nothing is generated; a standard DocType is never edited (project runtime fields are added as Custom Fields).

Form actions (only those that apply are shown): **Open**, **Edit with Frappe** (Form Builder for custom DocTypes, Customize Form for standard ones), **Sync Fields**, **Map PDF**, **Configure Workflow** (standard Frappe Workflow), **Project Setup**, **Publish**, **Create Revision**.

- **Sync Fields** adds new Frappe fields, updates labels/types, and marks deleted fields *Orphaned* (never removed). PDF coordinates and project settings are kept.
- **Map PDF** works for any form with a PDF attached, AI analysis optional. After the DocType exists the mapping can only place that DocType's fields.
- **Revisions**: a Published revision's mapping is frozen. *Create Revision* makes a Draft copy on the **same DocType**. Publishing it supersedes the earlier revision, moves project settings to it, and stamps new records with it, while existing records keep their own revision and configuration snapshot.

### Areas and groups

**AI Form Area** (Quality, HSE, …) and **AI Form Group** (QA, QC, Safety, …, with optional parent group) are plain configuration records seeded on install. No code refers to their names.

**Add a new area (e.g. Engineering):** create an *AI Form Area* "Engineering", then *AI Form Groups* "Civil", "Mechanical", "Electrical" with that area, then create forms with **New Form** and pick the area and group. No code change.

### Projects

A project-configurable form links to a context record (the *Project DocType* / *Project Fieldname* on the form). The default comes from **AI Form Builder Settings → Form Context**, or from Docuflow's `DCMS Project` when Docuflow is installed. Without a configuration a form behaves exactly as before.

- **Assign a form to a project:** *Project Form Setup* → choose the project → tick the form.
- **Hide fields for one project only:** in *Project Form Setup* press **Configure** on the form, untick *Show* (or set *Required* / *Read Only* / a project label), **Save**. Other projects, the DocType, the PDF mapping and stored values are untouched. Hidden is never deleted.
- **Reusable profiles:** create an *AI Form Field Profile* (e.g. "Basic") for the form, then choose it in **Configure**. The project stores only its own overrides on top of the profile.
- Users open forms from **Project Forms**: forms enabled for the project that their roles permit, with the project pre-filled on new records.

The server enforces the project rules: the form must be enabled for the project, project-required fields are required, a field hidden for the project is never required (whatever other projects or the master say), project read-only fields cannot be changed through the API, and the user must be able to read the project. Each record stores the configuration it was created with (`ai_form_configuration_snapshot`).

DocType Layout in Frappe v15 only holds field order and labels, so the per-project overlay is applied by one shared runtime (`public/js/project_form_runtime.js`) plus the server-side validation above.

### Docuflow

`ai_form_builder/integrations/docuflow.py` is the only Docuflow-aware module and is inert when Docuflow is not installed. It reads Docuflow's `DCMS Project` and the user's active project through Docuflow's public helper; it never writes Docuflow data or changes Docuflow code. Docuflow's sidebars and registers are fixed in its source with no extension hook, so dynamic forms are offered alongside them from **Project Forms** (Desk), while Docuflow's own forms keep working unchanged. Give Docuflow roles access to a dynamic form's DocType with Frappe's Role Permission Manager.

Register/report pagination, child-table PDF placement, OCR fallback, and drag/resize mapping are planned extensions.

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
