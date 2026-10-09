"""Which model reads client sheets, and with which key.

AI Form Builder Settings win. When their key is blank and Docuflow is
installed, the enabled provider in Docuflow's Copilot configuration
(``DCMS LLM Provider Config``) is used: only its rows are read, no Docuflow
code is imported.
"""

import frappe
from frappe import _

DEFAULT_MODELS = {"Anthropic": "claude-opus-5-5", "OpenAI": "gpt-5"}
COPILOT_DOCTYPE = "DCMS LLM Provider Config"


def get_config() -> dict:
	settings = frappe.get_single("AI Form Builder Settings")
	if settings.get("api_key"):
		provider = settings.ai_provider or "Anthropic"
		return {
			"provider": provider,
			"api_key": settings.get_password("api_key"),
			"model": settings.ai_model or DEFAULT_MODELS.get(provider),
			"source": "AI Form Builder Settings",
		}
	if frappe.db.exists("DocType", COPILOT_DOCTYPE):
		rows = frappe.get_all(
			COPILOT_DOCTYPE, filters={"is_enabled": 1}, fields=["name", "provider", "default_model"]
		)
		rows.sort(key=lambda row: row.provider != "anthropic")
		for row in rows:
			provider = {"anthropic": "Anthropic", "openai": "OpenAI"}.get(row.provider)
			key = frappe.utils.password.get_decrypted_password(
				COPILOT_DOCTYPE, row.name, "api_key", raise_exception=False
			)
			if provider and key:
				return {
					"provider": provider,
					"api_key": key,
					"model": row.default_model or DEFAULT_MODELS[provider],
					"source": "Docuflow Copilot",
				}
	return {"provider": None, "api_key": None, "model": None, "source": None}


def get_provider():
	config = get_config()
	if not config["api_key"]:
		frappe.throw(
			_(
				"No AI key is configured. Add one in AI Form Builder Settings (or enable a provider in Docuflow's Copilot settings)."
			)
		)
	if config["provider"] == "OpenAI":
		from ai_form_builder.integrations.openai_provider import OpenAIProvider

		return OpenAIProvider(config["api_key"], config["model"])
	from ai_form_builder.integrations.anthropic_provider import AnthropicProvider

	return AnthropicProvider(config["api_key"], config["model"])
