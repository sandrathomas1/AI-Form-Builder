"""Claude reads the client sheet and returns a form spec (structured output)."""

import base64
import json

import anthropic
import frappe
from frappe import _

from ai_form_builder.services import form_spec
from ai_form_builder.services.extract import prompt

# Models that take the server-side refusal fallback ("default" routing).
FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 64000


class AnthropicProvider:
	def __init__(self, api_key: str, model: str):
		self.client = anthropic.Anthropic(api_key=api_key, timeout=900, max_retries=2)
		self.model = model

	def _ask(self, messages: list) -> tuple[dict, list]:
		kwargs = {
			"model": self.model,
			"max_tokens": MAX_TOKENS,
			"system": prompt.SYSTEM,
			"messages": messages,
			"output_config": {
				"effort": "high",
				"format": {"type": "json_schema", "schema": form_spec.LLM_SCHEMA},
			},
		}
		if self.model in FALLBACK_MODELS:
			kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")
		try:
			with self.client.beta.messages.stream(**kwargs) as stream:
				message = stream.get_final_message()
		except anthropic.AuthenticationError:
			frappe.throw(_("The Anthropic API key was rejected."))
		except anthropic.BadRequestError as error:
			frappe.throw(_("The AI request was refused: {0}").format(error.message))
		except anthropic.RateLimitError:
			frappe.throw(_("The AI provider is rate limiting requests. Try again in a minute."))
		except anthropic.APIConnectionError:
			frappe.throw(_("Could not reach the AI provider."))
		if message.stop_reason == "refusal":
			frappe.throw(_("The AI declined to read this document."))
		if message.stop_reason == "max_tokens":
			frappe.throw(_("The sheet is too large to read in one pass. Split it into smaller files."))
		text = next((block.text for block in message.content if block.type == "text"), "")
		try:
			return json.loads(text), message.content
		except json.JSONDecodeError as error:
			raise ValueError("The AI returned invalid JSON") from error

	def generate_spec(self, kind: str, path: str, title=None, draft=None, hints=None) -> dict:
		content = []
		if kind == "PDF":
			with open(path, "rb") as handle:
				data = base64.standard_b64encode(handle.read()).decode()
			content.append(
				{
					"type": "document",
					"source": {"type": "base64", "media_type": "application/pdf", "data": data},
				}
			)
		content.append({"type": "text", "text": prompt.instructions(kind, title, draft, hints)})
		messages = [{"role": "user", "content": content}]
		payload, reply = self._ask(messages)
		spec = form_spec.from_llm(payload)
		errors = form_spec.validate(spec)
		if errors:
			# One repair round: the model sees its own answer and the problems.
			messages += [
				{"role": "assistant", "content": reply},
				{"role": "user", "content": prompt.repair(errors)},
			]
			payload, _reply = self._ask(messages)
			spec = form_spec.from_llm(payload)
		return spec
