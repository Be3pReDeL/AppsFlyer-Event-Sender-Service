"""Authentication module - token and HMAC-based auth."""

import hashlib
import hmac
import time
from typing import Annotated

from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPBearer

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)


async def verify_token_auth(
    token: Annotated[str | None, Query()] = None,
    settings: Settings = Depends(get_settings),
) -> str:
    """Verify token-based authentication from query parameter.

    Args:
        token: Token from query parameter
        settings: Application settings

    Returns:
        The validated token (for logging purposes)

    Raises:
        AuthenticationError: If token is invalid or missing
    """
    if not token:
        logger.warning("auth_failed", reason="missing_token")
        raise AuthenticationError("Missing token parameter")

    valid_tokens = settings.get_api_tokens_list()
    if not valid_tokens:
        logger.error("auth_config_error", reason="no_tokens_configured")
        raise AuthenticationError("Authentication not configured")

    if token not in valid_tokens:
        logger.warning("auth_failed", reason="invalid_token")
        raise AuthenticationError("Invalid token")

    logger.debug("auth_success", method="token")
    return token


async def verify_hmac_auth(
    request: Request,
    key: Annotated[str | None, Query()] = None,
    ts: Annotated[str | None, Query()] = None,
    sig: Annotated[str | None, Query()] = None,
    settings: Settings = Depends(get_settings),
) -> str:
    """Verify HMAC-based authentication from query parameters.

    Args:
        request: FastAPI request object
        key: Public key identifier
        ts: Timestamp (unix seconds)
        sig: HMAC signature
        settings: Application settings

    Returns:
        The public key identifier

    Raises:
        AuthenticationError: If HMAC verification fails
    """
    if not all([key, ts, sig]):
        logger.warning("hmac_auth_failed", reason="missing_parameters")
        raise AuthenticationError("Missing HMAC parameters (key, ts, sig)")

    # Get HMAC keys
    hmac_keys = settings.get_hmac_keys()
    if not hmac_keys:
        logger.error("auth_config_error", reason="no_hmac_keys_configured")
        raise AuthenticationError("HMAC authentication not configured")

    if key not in hmac_keys:
        logger.warning("hmac_auth_failed", reason="invalid_key", key=key)
        raise AuthenticationError("Invalid key")

    secret = hmac_keys[key]

    # Verify timestamp
    try:
        timestamp = int(ts)
    except ValueError:
        logger.warning("hmac_auth_failed", reason="invalid_timestamp", ts=ts)
        raise AuthenticationError("Invalid timestamp format") from None

    current_time = int(time.time())
    time_diff = abs(current_time - timestamp)

    if time_diff > settings.auth_ts_skew_seconds:
        logger.warning(
            "hmac_auth_failed",
            reason="timestamp_expired",
            time_diff=time_diff,
            allowed_skew=settings.auth_ts_skew_seconds,
        )
        raise AuthenticationError("Timestamp expired or invalid")

    # Build canonical query string (exclude sig parameter)
    query_params = dict(request.query_params)
    query_params.pop("sig", None)

    # Sort parameters for canonical form
    canonical_query = "&".join(
        f"{k}={v}" for k, v in sorted(query_params.items())
    )

    # Compute HMAC (canonical_query already contains ts, no need to append again)
    message = canonical_query.encode()
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison
    if not hmac.compare_digest(sig, expected_sig):
        logger.warning("hmac_auth_failed", reason="signature_mismatch")
        raise AuthenticationError("Invalid signature")

    # TODO: Add replay protection using Redis
    # Store sig in Redis with TTL = auth_ts_skew_seconds * 2

    logger.debug("auth_success", method="hmac", key=key)
    return key


async def get_current_auth(
    request: Request,
    settings: Settings = Depends(get_settings),
    token: Annotated[str | None, Query()] = None,
    key: Annotated[str | None, Query()] = None,
    ts: Annotated[str | None, Query()] = None,
    sig: Annotated[str | None, Query()] = None,
) -> dict[str, str]:
    """Main authentication dependency - supports both token and HMAC modes.

    Args:
        request: FastAPI request object
        settings: Application settings
        token: Token for token-based auth
        key: Public key for HMAC auth
        ts: Timestamp for HMAC auth
        sig: Signature for HMAC auth

    Returns:
        Dict with auth method and identifier

    Raises:
        AuthenticationError: If authentication fails
    """
    if settings.auth_mode == "token":
        await verify_token_auth(token, settings)
        return {"method": "token", "identifier": "***"}  # Masked for security

    elif settings.auth_mode == "hmac":
        validated_key = await verify_hmac_auth(request, key, ts, sig, settings)
        return {"method": "hmac", "identifier": validated_key}

    else:
        logger.error("auth_config_error", reason="invalid_auth_mode", mode=settings.auth_mode)
        raise AuthenticationError("Invalid authentication mode configured")


async def get_proxy_auth(
    token: Annotated[str | None, Query()] = None,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Token auth for proxy endpoints (works regardless of auth_mode)."""
    await verify_token_auth(token, settings)
    return {"method": "proxy", "identifier": "***"}


async def verify_admin_token(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    settings: Settings = Depends(get_settings),
) -> str:
    """Verify admin token from X-Admin-Token header."""
    if not x_admin_token:
        logger.warning("admin_auth_failed", reason="missing_admin_token")
        raise AuthenticationError("Missing X-Admin-Token header")

    valid_admin_tokens = settings.get_admin_tokens_list()
    if not valid_admin_tokens:
        logger.error("admin_auth_config_error", reason="no_admin_tokens_configured")
        raise AuthenticationError("Admin authentication not configured")

    if x_admin_token not in valid_admin_tokens:
        logger.warning("admin_auth_failed", reason="invalid_admin_token")
        raise AuthenticationError("Invalid admin token")

    logger.debug("admin_auth_success")
    return "***"
