from abc import ABC, abstractmethod


class BaseAIProvider(ABC):
	@abstractmethod
	def analyze_document(self, document: dict) -> dict:
		"""Return data-only structured analysis. Never executable content."""
