"""Тонкий HTTP-клиент fal.ai queue API. Только транспорт: расчёт кредитов,
резервы и обработка вебхука живут в media_generation_service."""

import httpx

from app.db.models import AiModel

BASE_URL = "https://queue.fal.run"


def extract_result_url(payload: dict | None) -> str | None:
    """Разные fal-модели кладут URL результата по-разному. Перебираем известные
    формы по порядку; None, если ничего не подошло (по образцу удалённого
    piapi_client.extract_result_url).

    Подтверждённые формы (image -> {"images":[{"url"}]}, video -> {"video":{"url"}})
    плюс защитный набор запасных форм, чтобы непокрытая модель не давала None
    (что вело бы к рефанду успешной генерации, аудит I2). Непойманная форма
    логируется на error в handle_fal_webhook -> дополняем перебор по факту.

    Вызывается напрямую на непроверенном теле вебхука без обёртки try/except,
    поэтому обязана не бросать исключения ни при каких «мусорных» входных
    данных (None, не-dict, не-list и т.п.) — каждый шаг разбора проверяется
    isinstance перед использованием.
    """
    if not isinstance(payload, dict):
        return None

    # 1. Списки объектов с url: images / video / audio / files (элементы -- dict).
    for key in ("images", "video", "audio", "files"):
        val = payload.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict) and isinstance(val[0].get("url"), str):
            return val[0]["url"]

    # 2. Вложенный объект с url: video / image / audio.
    for key in ("video", "image", "audio"):
        val = payload.get(key)
        if isinstance(val, dict) and isinstance(val.get("url"), str):
            return val["url"]

    # 3. Плоские url-поля.
    for key in ("video_url", "image_url", "audio_url", "url"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val

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
        self, model: AiModel, prompt: str, *, image_url: str | None = None,
        provider_params: dict | None = None, webhook_url: str,
    ) -> str:
        body: dict = {"prompt": prompt}
        # У некоторых fal-моделей t2i и i2i -- разные маршруты (проверено по
        # схеме fal 2026-07-15): fal-ai/flux-pro/kontext требует image_url
        # (required: ["prompt","image_url"]), его t2i-версия -- отдельный
        # /text-to-image эндпоинт без этого поля; nano-banana аналогично
        # разделяется на .../edit. provider_model_id_edit = None у моделей
        # с единственным маршрутом -- тогда используем provider_model_id как обычно.
        if image_url is not None:
            body["image_url"] = image_url
            endpoint = model.provider_model_id_edit or model.provider_model_id
        else:
            endpoint = model.provider_model_id
        # Параметры опций приходят из model_options.provider_params как есть:
        # адаптер НЕ знает про resolution/duration/num_frames -- контракты
        # у моделей несводимы, и знание о них живёт в БД, а не в коде.
        if provider_params:
            body.update(provider_params)
        return await self._submit(endpoint, body, webhook_url)

    async def submit_video(
        self, model: AiModel, prompt: str, *, provider_params: dict | None = None,
        webhook_url: str,
    ) -> str:
        body: dict = {"prompt": prompt}
        if provider_params:
            body.update(provider_params)
        return await self._submit(model.provider_model_id, body, webhook_url)
