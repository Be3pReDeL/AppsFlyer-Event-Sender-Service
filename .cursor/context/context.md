# Project Context

## Статус разработки

### Завершённые задачи
- [x] **Bootstrap**: базовая структура проекта, конфигурация, health endpoints, Docker
- [x] **Bugfix**: Исправлен lru_cache в get_settings() и resource leak в _check_redis()
- [x] **Endpoint'ы + auth + валидация**: Реализованы /v1/track/registration и /v1/track/purchase с token и HMAC auth

### В ожидании
- [ ] Очередь Redis Streams + базовый worker
- [ ] AppsFlyer client + mapper по докам Context7
- [ ] Надёжность (retry/backoff/DLQ/dedup/pending reclaim)
- [ ] Observability + hardening + финальная документация и тесты

---

## Архитектура

```
Keitaro → API (FastAPI) → Redis Streams → Worker → AppsFlyer API
```

### Компоненты
1. **API Service** (`app/main.py`, `app/api/`)
   - FastAPI с lifespan events
   - Health endpoints: `/health/live`, `/health/ready`
   - Конфигурация через pydantic-settings

2. **Worker Service** (`app/worker/run.py`)
   - Заглушка, будет читать из Redis Streams Consumer Group
   - Graceful shutdown через signal handlers

3. **Redis**
   - Streams: `events:main`, `events:dlq`
   - Dedup keys: `dedup:<event_id>` с TTL
   - Rate limit buckets

### Структура проекта
```
app/
├── main.py           # FastAPI приложение с lifespan
├── api/
│   ├── health.py     # Health check endpoints
│   ├── routes.py     # Tracking endpoints (registration/purchase)
│   ├── auth.py       # Token и HMAC аутентификация
│   └── schemas.py    # Pydantic модели запросов/ответов
├── core/
│   ├── config.py     # Settings через pydantic-settings
│   ├── logging.py    # Structlog с маскированием
│   └── exceptions.py # Custom exceptions
├── queue/            # Redis Streams (пусто)
├── appsflyer/        # AppsFlyer client (пусто)
└── worker/
    └── run.py        # Worker entry point
tests/
├── conftest.py       # Fixtures
├── test_health.py    # Health endpoint tests
├── test_auth.py      # Authentication tests
└── test_routes.py    # Tracking endpoints tests
docs/
├── references.md     # Использованная документация
├── decisions.md      # Архитектурные решения
└── appsflyer_api.md  # AppsFlyer API spec
docker/
├── Dockerfile.api
└── Dockerfile.worker
```

---

## Ключевые решения

1. **Redis Streams** — простота деплоя, Consumer Groups, pending entries
2. **Token auth** как базовый режим — совместимость с Keitaro
3. **Lifespan context manager** — рекомендуемый подход FastAPI
4. **Structlog** — JSON-логи с маскированием sensitive данных

---

## Конфигурация (ENV)

Основные переменные (см. `.env.example`):
- `APP_ENV`, `DEBUG` — окружение
- `AUTH_MODE`, `API_TOKENS` — аутентификация
- `REDIS_URL`, `STREAM_MAIN`, `STREAM_DLQ` — очередь
- `APPSFLYER_BASE_URL`, `APPSFLYER_DEV_KEY` — AppsFlyer
- `LOG_LEVEL`, `LOG_FORMAT` — логирование

---

## Источники документации (Context7)

| Библиотека | Context7 ID | Использовано |
|------------|-------------|--------------|
| FastAPI | `/websites/fastapi_tiangolo` | Lifespan, DI |
| Redis-py | `/redis/redis-py` | Streams, Consumer Groups |
| Pydantic Settings | `/pydantic/pydantic-settings` | ENV config |

---

## Исправленные проблемы

1. **get_settings() lru_cache**: Убран `@lru_cache` для корректной работы с тестами и динамическими ENV изменениями
2. **Redis resource leak**: Добавлен `try-finally` в `_check_redis()` для гарантированного закрытия connection pool

---

## Реализованные фичи (Этап 2)

### Аутентификация (`app/api/auth.py`)
- **Token-based auth**: query-параметр `?token=<value>`
  - Поддержка нескольких токенов через `API_TOKENS` (comma-separated)
  - Автоматическое маскирование в логах
- **HMAC auth**: `?key=<id>&ts=<timestamp>&sig=<signature>`
  - Подпись: `HMAC_SHA256(secret, canonical_query + ts)`
  - Защита от timestamp skew (±300 sec)
  - Constant-time signature comparison
  - TODO: Replay protection через Redis

### API Endpoints (`app/api/routes.py`)
- `GET/POST /v1/track/registration` — регистрация пользователя
- `GET/POST /v1/track/purchase` — покупка (обязательные: revenue, currency)
- Автогенерация `event_id` если не передан
- Возврат 202 Accepted с event_id и queued_at

### Валидация (`app/api/schemas.py`)
- **RegistrationRequest**: appsflyer_id, customer_user_id, platform, registration_method
- **PurchaseRequest**: revenue (≥0), currency (3 chars), product_id, order_id, quantity
- **TrackingResponse**: status, event_id, queued_at
- Автонормализация: platform → lowercase, currency → uppercase

### Тесты (23 passed)
- `test_auth.py`: token/HMAC валидация, invalid/expired/missing parameters
- `test_routes.py`: GET/POST endpoints, validation, auth enforcement

## Следующие шаги

1. Реализовать Redis Streams producer — постановка событий в очередь
2. Реализовать Redis Streams consumer — чтение событий worker'ом
3. Добавить дедупликацию через Redis keys
