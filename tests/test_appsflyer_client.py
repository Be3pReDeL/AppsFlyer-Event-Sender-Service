"""Tests for AppsFlyer client."""

import json

import httpx
import pytest
import respx

from app.appsflyer.client import AppsFlyerClient
from app.appsflyer.models import AppsFlyerRequest
from app.core.config import Settings
from app.core.exceptions import AppsFlyerError


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        appsflyer_base_url="https://api3.appsflyer.com",
        appsflyer_dev_key="test-dev-key",
        appsflyer_default_app_id="com.test.app",
        appsflyer_timeout_seconds=5.0,
    )


@pytest.fixture
def client(settings: Settings) -> AppsFlyerClient:
    """Create AppsFlyer client."""
    return AppsFlyerClient(settings)


@pytest.fixture
def sample_request() -> AppsFlyerRequest:
    """Create sample AppsFlyer request."""
    return AppsFlyerRequest(
        appsflyer_id="af-device-123",
        event_name="af_purchase",
        event_value={"af_revenue": "9.99", "af_currency": "USD"},
        customer_user_id="user-456",
        platform="iOS",
    )


@pytest.mark.asyncio
@respx.mock
async def test_send_event_success(
    client: AppsFlyerClient,
    sample_request: AppsFlyerRequest,
) -> None:
    """Test successful event send."""
    # Mock successful response
    respx.post("https://api3.appsflyer.com/inappevent/com.test.app").mock(
        return_value=httpx.Response(
            200,
            json={"status": "success", "message": "Event received successfully."},
        )
    )

    response = await client.send_event(sample_request, "test_event_123")

    assert response.status == "success"
    assert response.message == "Event received successfully."


@pytest.mark.asyncio
@respx.mock
async def test_send_event_payload_format(
    client: AppsFlyerClient,
    sample_request: AppsFlyerRequest,
) -> None:
    """Test that payload uses AppsFlyer field names and stringified event value."""
    route = respx.post("https://api3.appsflyer.com/inappevent/com.test.app").mock(
        return_value=httpx.Response(200, json={"status": "success", "message": "OK"})
    )

    await client.send_event(sample_request, "test_event_payload_001")

    assert route.called
    sent_request = route.calls[0].request
    payload = json.loads(sent_request.content.decode())

    assert payload["appsflyer_id"] == "af-device-123"
    assert payload["eventName"] == "af_purchase"
    assert isinstance(payload["eventValue"], str)
    assert json.loads(payload["eventValue"]) == sample_request.event_value
    assert "event_name" not in payload
    assert "event_value" not in payload

    assert sent_request.headers.get("authentication") == "test-dev-key"
    assert sent_request.headers.get("accept") == "application/json"
    assert sent_request.headers.get("content-type") == "application/json"


@pytest.mark.asyncio
@respx.mock
async def test_send_event_empty_event_value_serializes_to_empty_string(
    client: AppsFlyerClient,
) -> None:
    """Test empty event_value is sent as empty string."""
    request = AppsFlyerRequest(
        appsflyer_id="af-device-empty",
        event_name="af_complete_registration",
        event_value={},
    )

    route = respx.post("https://api3.appsflyer.com/inappevent/com.test.app").mock(
        return_value=httpx.Response(200, json={"status": "success", "message": "OK"})
    )

    await client.send_event(request, "test_event_payload_002")

    assert route.called
    payload = json.loads(route.calls[0].request.content.decode())
    assert payload["eventName"] == "af_complete_registration"
    assert payload["eventValue"] == ""


@pytest.mark.asyncio
@respx.mock
async def test_send_event_success_ok_string(
    client: AppsFlyerClient,
    sample_request: AppsFlyerRequest,
) -> None:
    """Test successful response with 'OK' string."""
    respx.post("https://api3.appsflyer.com/inappevent/com.test.app").mock(
        return_value=httpx.Response(200, text='"OK"')
    )

    response = await client.send_event(sample_request, "test_event_456")

    assert response.status == "success"


@pytest.mark.asyncio
@respx.mock
async def test_send_event_400_bad_request(
    client: AppsFlyerClient,
    sample_request: AppsFlyerRequest,
) -> None:
    """Test 400 Bad Request (non-retryable)."""
    respx.post("https://api3.appsflyer.com/inappevent/com.test.app").mock(
        return_value=httpx.Response(
            400,
            json={"status": "error", "message": "Missing mandatory fields"},
        )
    )

    with pytest.raises(AppsFlyerError) as exc_info:
        await client.send_event(sample_request, "test_event_789")

    error = exc_info.value
    assert error.status_code == 400
    assert error.retryable is False
    assert "Missing mandatory fields" in error.message


@pytest.mark.asyncio
@respx.mock
async def test_send_event_401_unauthorized(
    client: AppsFlyerClient,
    sample_request: AppsFlyerRequest,
) -> None:
    """Test 401 Unauthorized (non-retryable)."""
    respx.post("https://api3.appsflyer.com/inappevent/com.test.app").mock(
        return_value=httpx.Response(401, json={"status": "error", "message": "Invalid dev_key"})
    )

    with pytest.raises(AppsFlyerError) as exc_info:
        await client.send_event(sample_request, "test_event")

    error = exc_info.value
    assert error.status_code == 401
    assert error.retryable is False


@pytest.mark.asyncio
@respx.mock
async def test_send_event_429_rate_limit(
    client: AppsFlyerClient,
    sample_request: AppsFlyerRequest,
) -> None:
    """Test 429 Rate Limit (retryable)."""
    respx.post("https://api3.appsflyer.com/inappevent/com.test.app").mock(
        return_value=httpx.Response(
            429,
            headers={"Retry-After": "60"},
            json={"status": "error", "message": "Rate limit exceeded"},
        )
    )

    with pytest.raises(AppsFlyerError) as exc_info:
        await client.send_event(sample_request, "test_event")

    error = exc_info.value
    assert error.status_code == 429
    assert error.retryable is True
    assert error.details.get("retry_after") == "60"


@pytest.mark.asyncio
@respx.mock
async def test_send_event_500_server_error(
    client: AppsFlyerClient,
    sample_request: AppsFlyerRequest,
) -> None:
    """Test 500 Internal Server Error (retryable)."""
    respx.post("https://api3.appsflyer.com/inappevent/com.test.app").mock(
        return_value=httpx.Response(500, json={"status": "error", "message": "Internal error"})
    )

    with pytest.raises(AppsFlyerError) as exc_info:
        await client.send_event(sample_request, "test_event")

    error = exc_info.value
    assert error.status_code == 500
    assert error.retryable is True


@pytest.mark.asyncio
@respx.mock
async def test_send_event_timeout(
    client: AppsFlyerClient,
    sample_request: AppsFlyerRequest,
) -> None:
    """Test timeout error (retryable)."""
    respx.post("https://api3.appsflyer.com/inappevent/com.test.app").mock(
        side_effect=httpx.TimeoutException("Connection timeout")
    )

    with pytest.raises(AppsFlyerError) as exc_info:
        await client.send_event(sample_request, "test_event")

    error = exc_info.value
    assert error.status_code is None
    assert error.retryable is True
    assert "timeout" in error.message.lower()


@pytest.mark.asyncio
@respx.mock
async def test_send_event_network_error(
    client: AppsFlyerClient,
    sample_request: AppsFlyerRequest,
) -> None:
    """Test network error (retryable)."""
    respx.post("https://api3.appsflyer.com/inappevent/com.test.app").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    with pytest.raises(AppsFlyerError) as exc_info:
        await client.send_event(sample_request, "test_event")

    error = exc_info.value
    assert error.retryable is True
