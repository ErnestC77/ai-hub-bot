from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.db.models import ModelConfig


@dataclass
class AIResult:
    answer: str
    input_tokens: int
    output_tokens: int


class AIError(Exception):
    """Внутренние детали ошибки провайдера наружу пользователю не показываются."""


class AIProvider(ABC):
    @abstractmethod
    async def generate(self, model: ModelConfig, prompt: str, max_output_tokens: int) -> AIResult: ...
