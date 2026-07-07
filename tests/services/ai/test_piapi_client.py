import httpx
import pytest
import respx

from app.services.ai.piapi_client import PiAPIClient, extract_result_url


@respx.mock
async def test_create_task_returns_task_id():
    respx.post("https://api.piapi.ai/api/v1/task").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": {"task_id": "49638cd2-4689-4f33-9336-164a8f6b1111", "status": "pending"},
            },
        )
    )
    client = PiAPIClient(api_key="sk-test")
    task_id = await client.create_task(
        model="Qubico/flux1-dev",
        task_type="txt2img",
        input_={"prompt": "a bear"},
        webhook_url="https://example.com/webhook",
    )
    assert task_id == "49638cd2-4689-4f33-9336-164a8f6b1111"

    request = respx.calls.last.request
    assert request.headers["x-api-key"] == "sk-test"
    import json
    body = json.loads(request.content)
    assert body["model"] == "Qubico/flux1-dev"
    assert body["task_type"] == "txt2img"
    assert body["input"] == {"prompt": "a bear"}
    assert body["config"]["webhook_config"]["endpoint"] == "https://example.com/webhook"


@respx.mock
async def test_get_task_completed_with_image_url():
    respx.get("https://api.piapi.ai/api/v1/task/abc-123").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": {
                    "task_id": "abc-123",
                    "status": "completed",
                    "output": {"image_url": "https://cdn.example.com/out.png"},
                    "error": {"code": 0, "message": ""},
                },
            },
        )
    )
    client = PiAPIClient(api_key="sk-test")
    result = await client.get_task("abc-123")
    assert result.status == "completed"
    assert result.result_url == "https://cdn.example.com/out.png"
    assert result.error_message is None


@respx.mock
async def test_get_task_failed_with_error_message():
    respx.get("https://api.piapi.ai/api/v1/task/abc-456").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": {
                    "task_id": "abc-456",
                    "status": "failed",
                    "output": None,
                    "error": {"code": 10000, "message": "content policy violation"},
                },
            },
        )
    )
    client = PiAPIClient(api_key="sk-test")
    result = await client.get_task("abc-456")
    assert result.status == "failed"
    assert result.result_url is None
    assert result.error_message == "content policy violation"


def test_extract_result_url_flat_image_url():
    assert extract_result_url({"output": {"image_url": "https://x/a.png"}}) == "https://x/a.png"


def test_extract_result_url_image_urls_array():
    assert extract_result_url({"output": {"image_urls": ["https://x/a.png", "https://x/b.png"]}}) == "https://x/a.png"


def test_extract_result_url_video_url():
    assert extract_result_url({"output": {"video_url": "https://x/a.mp4"}}) == "https://x/a.mp4"


def test_extract_result_url_nested_luma_shape():
    data = {"output": {"generation": {"video": {"url": "https://x/a.mp4", "url_no_watermark": "https://x/b.mp4"}}}}
    assert extract_result_url(data) == "https://x/b.mp4"


def test_extract_result_url_none_when_missing():
    assert extract_result_url({"output": None}) is None
    assert extract_result_url({"output": {}}) is None
