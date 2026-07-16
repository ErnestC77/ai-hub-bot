import json

import httpx
import pytest
import respx

from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel
from app.services.ai.fal_client import FalClient, extract_result_url


def _model(code="flux_dev", *, provider_model_id="fal-ai/flux/dev",
           provider_model_id_edit: str | None = None,
           category=ModelCategory.image) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=category, code=code, display_name=code,
        provider_model_id=provider_model_id, provider_model_id_edit=provider_model_id_edit,
        tier=ModelTier.standard,
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
async def test_submit_image_with_image_url_and_edit_route_hits_edit_endpoint():
    # image_url задан + provider_model_id_edit задан -> запрос идёт на edit-маршрут
    # (i2i), а не на t2i-маршрут -- иначе пользователя списывают по цене edit,
    # а сервер тихо игнорирует фото (billing-критичный баг).
    edit_route = respx.post(host="queue.fal.run", path="/fal-ai/flux-pro/kontext").mock(
        return_value=httpx.Response(200, json={"request_id": "req-edit"})
    )
    t2i_route = respx.post(
        host="queue.fal.run", path="/fal-ai/flux-pro/kontext/text-to-image"
    ).mock(return_value=httpx.Response(200, json={"request_id": "req-t2i"}))
    client = FalClient(api_key="k")

    request_id = await client.submit_image(
        _model(
            provider_model_id="fal-ai/flux-pro/kontext/text-to-image",
            provider_model_id_edit="fal-ai/flux-pro/kontext",
        ),
        "make it night",
        image_url="https://cdn.example.com/in.png",
        webhook_url="https://backend.example.com/api/fal/webhook?secret=s",
    )

    assert request_id == "req-edit"
    assert edit_route.called
    assert not t2i_route.called


@respx.mock
async def test_submit_image_with_image_url_and_no_edit_route_falls_back_to_provider_model_id():
    # provider_model_id_edit не задан (единственный маршрут, напр. qwen_image) ->
    # используем provider_model_id даже при наличии image_url.
    route = respx.post(host="queue.fal.run", path="/fal-ai/qwen/image-edit").mock(
        return_value=httpx.Response(200, json={"request_id": "req-single-route"})
    )
    client = FalClient(api_key="k")

    request_id = await client.submit_image(
        _model(provider_model_id="fal-ai/qwen/image-edit", provider_model_id_edit=None),
        "make it night",
        image_url="https://cdn.example.com/in.png",
        webhook_url="https://backend.example.com/api/fal/webhook?secret=s",
    )

    assert request_id == "req-single-route"
    assert route.called


@respx.mock
async def test_submit_image_without_image_url_never_uses_edit_route():
    # Без image_url это t2i-запрос -- обязан идти на provider_model_id, даже
    # если у модели настроен provider_model_id_edit.
    t2i_route = respx.post(
        host="queue.fal.run", path="/fal-ai/flux-pro/kontext/text-to-image"
    ).mock(return_value=httpx.Response(200, json={"request_id": "req-t2i"}))
    edit_route = respx.post(host="queue.fal.run", path="/fal-ai/flux-pro/kontext").mock(
        return_value=httpx.Response(200, json={"request_id": "req-edit"})
    )
    client = FalClient(api_key="k")

    request_id = await client.submit_image(
        _model(
            provider_model_id="fal-ai/flux-pro/kontext/text-to-image",
            provider_model_id_edit="fal-ai/flux-pro/kontext",
        ),
        "a bear",
        webhook_url="https://backend.example.com/api/fal/webhook?secret=s",
    )

    assert request_id == "req-t2i"
    assert t2i_route.called
    assert not edit_route.called


@respx.mock
async def test_submit_video_includes_provider_params():
    route = respx.post(host="queue.fal.run", path="/fal-ai/kling-video/v2/master").mock(
        return_value=httpx.Response(200, json={"request_id": "req-125"})
    )
    client = FalClient(api_key="k")

    request_id = await client.submit_video(
        _model(code="kling", provider_model_id="fal-ai/kling-video/v2/master",
               category=ModelCategory.video),
        "a bear runs", provider_params={"duration": "10"},
        webhook_url="https://backend.example.com/api/fal/webhook?secret=s",
    )

    assert request_id == "req-125"
    body = json.loads(route.calls.last.request.content)
    assert body == {"prompt": "a bear runs", "duration": "10"}


@respx.mock
async def test_submit_video_merges_provider_params_preserving_types():
    """Типы обязаны пережить merge: Kling ждёт duration СТРОКОЙ "10",
    Wan -- num_frames числом. Прежний код слал {"duration": <int>} --
    Veo такой запрос отвергает, Wan молча игнорирует."""
    route = respx.post(host="queue.fal.run", path="/fal-ai/kling").mock(
        return_value=httpx.Response(200, json={"request_id": "req-1"})
    )
    client = FalClient("k")
    await client.submit_video(
        _model(provider_model_id="fal-ai/kling"), "a cube",
        provider_params={"duration": "10"}, webhook_url="https://wh",
    )
    body = json.loads(route.calls.last.request.content)
    assert body == {"prompt": "a cube", "duration": "10"}
    assert isinstance(body["duration"], str)


@respx.mock
async def test_submit_video_without_params_sends_only_prompt():
    """Опций нет (Ovi) -- шлём голый промпт, а не выдуманные поля."""
    route = respx.post(host="queue.fal.run", path="/fal-ai/ovi").mock(
        return_value=httpx.Response(200, json={"request_id": "req-1"})
    )
    await FalClient("k").submit_video(
        _model(provider_model_id="fal-ai/ovi"), "a cube", webhook_url="https://wh"
    )
    assert json.loads(route.calls.last.request.content) == {"prompt": "a cube"}


@respx.mock
async def test_submit_image_merges_params_and_keeps_edit_route():
    """Опции не должны сломать выбор i2i-маршрута (сделан прошлым планом)."""
    edit = respx.post(host="queue.fal.run", path="/fal-ai/kontext").mock(
        return_value=httpx.Response(200, json={"request_id": "req-edit"})
    )
    await FalClient("k").submit_image(
        _model(provider_model_id="fal-ai/kontext/text-to-image",
               provider_model_id_edit="fal-ai/kontext"),
        "make it night", image_url="https://img",
        provider_params={"image_size": {"width": 2048, "height": 2048}},
        webhook_url="https://wh",
    )
    body = json.loads(edit.calls.last.request.content)
    assert body["image_url"] == "https://img"
    assert body["image_size"] == {"width": 2048, "height": 2048}


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


def test_extract_result_url_survives_non_list_images():
    assert extract_result_url({"images": 42}) is None
    assert extract_result_url({"images": True}) is None
    assert extract_result_url({"images": {"nested": "oops"}}) is None


def test_extract_result_url_survives_non_dict_items_in_images_list():
    assert extract_result_url({"images": ["not-a-dict"]}) is None
    assert extract_result_url({"images": [None]}) is None


def test_extract_result_url_survives_none_payload():
    assert extract_result_url(None) is None


def test_extract_result_url_survives_non_dict_payload():
    assert extract_result_url("not-a-dict") is None
    assert extract_result_url([1, 2, 3]) is None
