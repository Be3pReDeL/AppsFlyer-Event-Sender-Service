# Project Context

## Статус разработки

### Завершённые задачи
- [x] **Bootstrap**: базовая структура проекта, конфигурация, health endpoints, Docker
- [x] **Bugfix**: Исправлен lru_cache в get_settings() и resource leak в _check_redis()

### В ожидании
- [ ] Endpoint'ы + auth + валидация + маскирование секретов
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
│   └── health.py     # Health check endpoints
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
└── test_health.py    # Health endpoint tests
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

## Следующие шаги

1. Реализовать `/v1/track/registration` и `/v1/track/purchase` endpoints
2. Добавить token-based аутентификацию
3. Добавить валидацию входных данных (Pydantic schemas)
4. Реализовать маскирование токенов в логах
