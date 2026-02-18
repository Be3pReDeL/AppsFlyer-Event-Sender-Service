# References

Документация и источники, использованные при разработке сервиса.

## Библиотеки и фреймворки

### FastAPI
- **Источник**: Context7 MCP - `/websites/fastapi_tiangolo`
- **Дата обращения**: 2026-01-29
- **Использовано**: Lifespan events, dependency injection, health endpoints

### Redis-py (async)
- **Источник**: Context7 MCP - `/redis/redis-py`
- **Дата обращения**: 2026-01-29
- **Использовано**: Redis Streams, Consumer Groups (xreadgroup, xadd, xack, xautoclaim)

### Pydantic Settings
- **Источник**: Context7 MCP - `/pydantic/pydantic-settings`
- **Дата обращения**: 2026-01-29
- **Использовано**: Конфигурация через environment variables и .env файлы

## AppsFlyer API
- **Источник**: Context7 MCP - `/websites/dev_appsflyer_hc_reference`
- **Дата обращения**: 2026-01-29
- **Использовано**: S2S Events API endpoint, authentication, request/response models
- **Документация**: `docs/appsflyer_api.md`
