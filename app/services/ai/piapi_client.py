from dataclasses import dataclass

import httpx

BASE_URL = "https://api.piapi.ai/api/v1"


@dataclass
class PiAPITaskResult:
    task_id: str
    status: str  # "pending" | "processing" | "completed" | "failed"
    result_url: str | None
    error_message: str | None


def extract_result_url(data: dict) -> str | None:
    """Different PiAPI model families nest the result URL differently.
    Tries each known shape in order; returns None if nothing matches."""
    output = data.get("output") or {}

    if url := output.get("image_url"):
        return url
    if urls := output.get("image_urls"):
        return urls[0] if urls else None
    if url := output.get("video_url"):
        return url

    generation = output.get("generation") or {}
    video = generation.get("video") or {}
    if url := video.get("url_no_watermark"):
        return url
    if url := video.get("url"):
        return url

    return None


class PiAPIClient:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key, "Content-Type": "application/json"}

    async def create_task(self, model: str, task_type: str, input_: dict, webhook_url: str) -> str:
        body = {
            "model": model,
            "task_type": task_type,
            "input": input_,
            "config": {"webhook_config": {"endpoint": webhook_url, "secret": ""}},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{BASE_URL}/task", headers=self._headers(), json=body)
            response.raise_for_status()
        return response.json()["data"]["task_id"]

    async def get_task(self, task_id: str) -> PiAPITaskResult:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{BASE_URL}/task/{task_id}", headers=self._headers())
            response.raise_for_status()
        data = response.json()["data"]
        error = data.get("error") or {}
        return PiAPITaskResult(
            task_id=data["task_id"],
            status=data["status"],
            result_url=extract_result_url(data) if data["status"] == "completed" else None,
            error_message=error.get("message") or None,
        )
