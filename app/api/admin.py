"""Admin API routes for protected runtime configuration updates."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth import verify_admin_token
from app.api.schemas import DevKeyMappingResponse, DevKeyMappingUpsertRequest, ErrorResponse
from app.appsflyer.dev_key_repository import DevKeyRepository
from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/admin", tags=["Admin"])


@router.post(
    "/dev-keys",
    response_model=DevKeyMappingResponse,
    summary="Upsert app_id to dev_key mapping",
    description="Protected endpoint for storing app-specific AppsFlyer dev keys.",
    responses={
        200: {"description": "Mapping updated"},
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Authentication failed"},
    },
)
async def upsert_dev_key_mapping(
    payload: DevKeyMappingUpsertRequest,
    admin_token: Annotated[str, Depends(verify_admin_token)],  # noqa: ARG001
    settings: Annotated[Settings, Depends(get_settings)],
) -> DevKeyMappingResponse:
    """Save or update app_id -> dev_key mapping in persistent DB."""
    app_id = payload.app_id.strip()
    dev_key = payload.dev_key.strip()

    if not app_id:
        raise ValidationError("app_id must not be empty")
    if not dev_key:
        raise ValidationError("dev_key must not be empty")

    repo = DevKeyRepository(
        database_url=settings.appsflyer_dev_key_database_url,
        sqlite_db_path=settings.appsflyer_dev_key_db_path,
    )
    updated_at_raw = await repo.upsert_dev_key(app_id=app_id, dev_key=dev_key)
    updated_at = datetime.fromisoformat(updated_at_raw)

    logger.info("admin_dev_key_mapping_updated", app_id=app_id)
    return DevKeyMappingResponse(
        status="updated",
        app_id=app_id,
        updated_at=updated_at,
    )
