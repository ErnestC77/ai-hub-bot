"""Тонкий HTTP-клиент fal.ai queue API. Только транспорт: расчёт кредитов,
резервы и обработка вебхука живут в media_generation_service."""

import httpx

from app.db.models import AiModel

BASE_URL = "https://queue.fal.run"


def extract_result_url(payload: dict) -> str | None:
    """Разные fal-модели кладут URL результата по-разному. Перебираем известные
    формы по порядку; None, если ничего не подошло (по образцу удалённого
    piapi_client.extract_result_url).

    Подтверждённые формы:
    - image-модели: {"images": [{"url": ...}, ...]}
    - video-модели: {"video": {"url": ...}}

    PLACEHOLDER: перед продакшн-запуском уточнить формы ответа всех 8 моделей
    каталога (fal-ai/*) и дополнить перебор.
    """
    images = payload.get("images") or []
    if images and isinstance(images[0], dict) and images[0].get("url"):
        return images[0]["url"]

    video = payload.get("video") or {}
    if isinstance(video, dict) and video.get("url"):
        return video["url"]

    return None


class FalClient:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Key {self._api_key}", "Content-Type": "application/json"}

    async def _submit(self, provider_model_id: str, body: dict, webhook_url: str) -> str:
        # Эндпоинт собирается из provider_model_id (как у OpenRouter в фазе 2):
        # модельные ID не хардкодятся в бизнес-логике.
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{BASE_URL}/{provider_model_id}",
                params={"fal_webhook": webhook_url},
                headers=self._headers(),
                json=body,
            )
            response.raise_for_status()
        return response.json()["request_id"]

    async def submit_image(
        self, model: AiModel, prompt: str, *, image_url: str | None = None, webhook_url: str
    ) -> str:
        body: dict = {"prompt": prompt}
        if image_url is not None:
            body["image_url"] = image_url
        return await self._submit(model.provider_model_id, body, webhook_url)

    async def submit_video(
        self, model: AiModel, prompt: str, *, duration_seconds: int, webhook_url: str
    ) -> str:
        # PLACEHOLDER: имя поля длительности ("duration") уточнить перед
        # продакшн-запуском для каждой video-модели каталога.
        body = {"prompt": prompt, "duration": duration_seconds}
        return await self._submit(model.provider_model_id, body, webhook_url)
