import json

import httpx
import pytest
import respx

from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel
from app.services.ai.fal_client import FalClient, extract_result_url


def _model(code="flux_dev", *, provider_model_id="fal-ai/flux/dev",
           category=ModelCategory.image) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=category, code=code, display_name=code,
        provider_model_id=provider_model_id, tier=ModelTier.standard,
        cost_unit=CostUnit.image, min_credits=0, recommended_credits=100,
    )


@respx.mock
async def test_submit_image_posts_prompt_and_returns_request_id():
    route = respx.post(host="queue.fal.run", path="/fal-ai/flux/dev").mock(
        return_value=httpx.Response(200, json={"request_id": "req-123"})
    )
    client = FalClient(api_key="fal-test-key")

    request_id = await client.submit_image(
        _model(), "a bear",
        webhook_url="https://backend.example.com/api/fal/webhook?secret=s",
    )

    assert request_id == "req-123"
    request = route.calls.last.request
    assert request.headers["authorization"] == "Key fal-test-key"
    # webhook уходит query-параметром fal_webhook, не в теле
    assert request.url.params["fal_webhook"] == "https://backend.example.com/api/fal/webhook?secret=s"
    assert json.loads(request.content) == {"prompt": "a bear"}


@respx.mock
async def test_submit_image_includes_image_url_for_edit():
    route = respx.post(host="queue.fal.run", path="/fal-ai/flux-kontext/pro").mock(
        return_value=httpx.Response(200, json={"request_id": "req-124"})
    )
    client = FalClient(api_key="k")

    await client.submit_image(
        _model(provider_model_id="fal-ai/flux-kontext/pro"), "make it night",
        image_url="https://cdn.example.com/in.png",
        webhook_url="https://backend.example.com/api/fal/webhook?secret=s",
    )

    body = json.loads(route.calls.last.request.content)
    assert body == {"prompt": "make it night", "image_url": "https://cdn.example.com/in.png"}


@respx.mock
async def test_submit_video_includes_duration():
    route = respx.post(host="queue.fal.run", path="/fal-ai/kling-video/v2/master").mock(
        return_value=httpx.Response(200, json={"request_id": "req-125"})
    )
    client = FalClient(api_key="k")

    request_id = await client.submit_video(
        _model(code="kling", provider_model_id="fal-ai/kling-video/v2/master",
               category=ModelCategory.video),
        "a bear runs", duration_seconds=10,
        webhook_url="https://backend.example.com/api/fal/webhook?secret=s",
    )

    assert request_id == "req-125"
    body = json.loads(route.calls.last.request.content)
    assert body == {"prompt": "a bear runs", "duration": 10}


@respx.mock
async def test_submit_raises_on_http_error():
    respx.post(host="queue.fal.run", path="/fal-ai/flux/dev").mock(
        return_value=httpx.Response(401, json={"detail": "invalid key"})
    )
    client = FalClient(api_key="bad")

    with pytest.raises(httpx.HTTPStatusError):
        await client.submit_image(
            _model(), "a bear", webhook_url="https://b/api/fal/webhook?secret=s"
        )


def test_extract_result_url_image_shape():
    payload = {"images": [{"url": "https://x/a.png"}, {"url": "https://x/b.png"}]}
    assert extract_result_url(payload) == "https://x/a.png"


def test_extract_result_url_video_shape():
    assert extract_result_url({"video": {"url": "https://x/a.mp4"}}) == "https://x/a.mp4"


def test_extract_result_url_none_when_unknown_shape():
    assert extract_result_url({}) is None
    assert extract_result_url({"images": []}) is None
    assert extract_result_url({"video": {}}) is None
    assert extract_result_url({"unexpected": {"url": "https://x/a.png"}}) is None
