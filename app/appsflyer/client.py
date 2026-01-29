"""AppsFlyer API client using httpx."""

import time

import httpx

from app.appsflyer.models import AppsFlyerRequest, AppsFlyerResponse
from app.core.config import Settings
from app.core.exceptions import AppsFlyerError
from app.core.logging import get_logger
from app.core.metrics import record_appsflyer_latency, record_appsflyer_request

logger = get_logger(__name__)


class AppsFlyerClient:
    """HTTP client for AppsFlyer S2S API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.appsflyer_base_url.rstrip("/")
        self.dev_key = settings.appsflyer_dev_key
        self.default_app_id = settings.appsflyer_default_app_id
        self.timeout = httpx.Timeout(
            connect=settings.appsflyer_timeout_seconds,
            read=settings.appsflyer_timeout_seconds,
            write=settings.appsflyer_timeout_seconds,
            pool=settings.appsflyer_timeout_seconds,
        )

    async def send_event(
        self,
        request: AppsFlyerRequest,
        event_id: str,
        app_id: str | None = None,
    ) -> AppsFlyerResponse:
        """Send event to AppsFlyer API.

        Args:
            request: AppsFlyer request model
            event_id: Internal event ID for logging
            app_id: AppsFlyer app ID (uses default if not provided)

        Returns:
            AppsFlyer response model

        Raises:
            AppsFlyerError: If request fails
        """
        # Use provided app_id or fallback to default
        target_app_id = app_id or self.default_app_id
        if not target_app_id:
            raise AppsFlyerError(
                "AppsFlyer app_id not configured and not provided in request",
                status_code=None,
                retryable=False,
            )

        # Build URL
        url = f"{self.base_url}/inappevent/{target_app_id}"

        # Build headers
        headers = {
            "authentication": self.dev_key,
            "Content-Type": "application/json",
        }

        # Build request body
        body = request.model_dump(exclude_none=True)

        logger.info(
            "appsflyer_request_start",
            event_id=event_id,
            event_name=request.event_name,
            url=url,
        )

        start_time = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json=body,
                    headers=headers,
                )

                latency = time.monotonic() - start_time

                # Log response
                logger.info(
                    "appsflyer_response",
                    event_id=event_id,
                    status_code=response.status_code,
                    latency_ms=int(latency * 1000),
                )

                # Record metrics
                record_appsflyer_request(request.event_name, response.status_code)
                record_appsflyer_latency(request.event_name, latency)

                # Handle response (may raise AppsFlyerError)
                return self._handle_response(response, event_id, request.event_name)

        except AppsFlyerError:
            # Re-raise AppsFlyerError from _handle_response without wrapping
            raise

        except httpx.TimeoutException as e:
            logger.warning(
                "appsflyer_timeout",
                event_id=event_id,
                error=str(e),
                timeout=self.settings.appsflyer_timeout_seconds,
            )
            raise AppsFlyerError(
                "Request timeout",
                status_code=None,
                retryable=True,
            ) from e

        except httpx.NetworkError as e:
            logger.warning(
                "appsflyer_network_error",
                event_id=event_id,
                error=str(e),
            )
            raise AppsFlyerError(
                f"Network error: {e}",
                status_code=None,
                retryable=True,
            ) from e

        except Exception as e:
            logger.error(
                "appsflyer_unexpected_error",
                event_id=event_id,
                error=str(e),
            )
            raise AppsFlyerError(
                f"Unexpected error: {e}",
                status_code=None,
                retryable=False,
            ) from e

    def _handle_response(
        self,
        response: httpx.Response,
        event_id: str,
        event_name: str = "unknown",
    ) -> AppsFlyerResponse:
        """Handle AppsFlyer API response.

        Args:
            response: HTTP response
            event_id: Internal event ID for logging
            event_name: Event name for metrics

        Returns:
            Parsed AppsFlyer response

        Raises:
            AppsFlyerError: If response indicates error
        """
        status_code = response.status_code

        # Success responses (2xx)
        if 200 <= status_code < 300:
            try:
                # Try to parse JSON response
                data = response.json()
                if isinstance(data, dict):
                    return AppsFlyerResponse(
                        status=data.get("status", "success"),
                        message=data.get("message"),
                    )
                # Response might be just "OK" string
                return AppsFlyerResponse(status="success", message=str(data))
            except Exception:
                # If parsing fails, treat as success
                return AppsFlyerResponse(status="success", message=response.text[:100])

        # Rate limiting (429)
        if status_code == 429:
            retry_after = response.headers.get("Retry-After")
            logger.warning(
                "appsflyer_rate_limited",
                event_id=event_id,
                retry_after=retry_after,
            )
            raise AppsFlyerError(
                "Rate limit exceeded",
                status_code=429,
                retryable=True,
                details={"retry_after": retry_after},
            )

        # Client errors (4xx) - generally non-retryable
        if 400 <= status_code < 500:
            error_detail = self._extract_error_detail(response)
            logger.warning(
                "appsflyer_client_error",
                event_id=event_id,
                status_code=status_code,
                error=error_detail,
            )
            # 4xx errors are not retryable (except 429 handled above)
            raise AppsFlyerError(
                f"Client error: {error_detail}",
                status_code=status_code,
                retryable=False,
            )

        # Server errors (5xx) - retryable
        if status_code >= 500:
            error_detail = self._extract_error_detail(response)
            logger.warning(
                "appsflyer_server_error",
                event_id=event_id,
                status_code=status_code,
                error=error_detail,
            )
            raise AppsFlyerError(
                f"Server error: {error_detail}",
                status_code=status_code,
                retryable=True,
            )

        # Unexpected status code
        raise AppsFlyerError(
            f"Unexpected status code: {status_code}",
            status_code=status_code,
            retryable=False,
        )

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        """Extract error details from response.

        Args:
            response: HTTP response

        Returns:
            Error detail string
        """
        try:
            data = response.json()
            if isinstance(data, dict):
                return data.get("message") or data.get("error") or response.text[:200]
            return str(data)[:200]
        except Exception:
            return response.text[:200]


def get_client(settings: Settings) -> AppsFlyerClient:
    """Factory function to create AppsFlyerClient instance."""
    return AppsFlyerClient(settings)
