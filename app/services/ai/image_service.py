import asyncio
import base64
from io import BytesIO

import httpx
from openai import AsyncOpenAI
from PIL import Image

from app.db.models import ModelConfig
from app.services.ai.base import AIError, AIProvider, AIResult
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider

_clients: dict[str, AsyncOpenAI] = {}


def _get_client(purpose: KeyPurpose) -> AsyncOpenAI:
    api_key = get_key_manager().get_key(Provider.OPENAI, purpose)
    client = _clients.get(api_key)
    if client is None:
        client = AsyncOpenAI(api_key=api_key)
        _clients[api_key] = client
    return client


def _upscale_2x(raw: bytes) -> str:
    """CPU-bound -- запускается в отдельном потоке через asyncio.to_thread."""
    img = Image.open(BytesIO(raw)).convert("RGB")
    upscaled = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    buf = BytesIO()
    upscaled.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode()


async def _upscale_to_data_uri(image_url: str) -> str:
    """"4K"-тир -- реальный 2x Lanczos-апскейл результата, отдаём как data URI
    (без отдельного файлового хранилища, которого у нас пока нет)."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(image_url)
        response.raise_for_status()
        raw = response.content
    encoded = await asyncio.to_thread(_upscale_2x, raw)
    return f"data:image/jpeg;base64,{encoded}"


class ImageProvider(AIProvider):
    """Генерация картинок. max_output_tokens не применим — игнорируется."""

    async def generate(
        self, model: ModelConfig, prompt: str, max_output_tokens: int, extra: dict | None = None
    ) -> AIResult:
        extra = extra or {}
        try:
            client = _get_client(KeyPurpose(model.key_purpose))
            response = await client.images.generate(
                model=model.model_code,
                prompt=prompt,
                n=1,
                size=extra.get("size", "1024x1024"),
                quality=extra.get("quality", "standard"),
                response_format="url",
            )
            url = response.data[0].url if response.data else None
            if not url:
                raise AIError("empty image response")

            if extra.get("resolution") == "4k":
                url = await _upscale_to_data_uri(url)

            return AIResult(answer=url, input_tokens=0, output_tokens=0)
        except AIError:
            raise
        except Exception as exc:
            raise AIError("Image API error") from exc
