# Project Context

## Статус разработки

### Завершённые задачи
- [x] **Bootstrap**: базовая структура проекта, конфигурация, health endpoints, Docker
- [x] **Bugfix**: Исправлен lru_cache в get_settings() и resource leak в _check_redis()
- [x] **Endpoint'ы + auth + валидация**: Реализованы /v1/track/registration и /v1/track/purchase с token и HMAC auth
- [x] **Очередь Redis Streams + базовый worker**: Producer, Consumer, InternalEvent model, дедупликация

### В ожидании
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
│   ├── exceptions.py # Custom exceptions
│   └── models.py     # InternalEvent model
├── queue/
│   ├── producer.py   # EventProducer для Redis Streams
│   └── consumer.py   # EventConsumer с Consumer Groups
├── appsflyer/        # AppsFlyer client (пусто)
└── worker/
    └── run.py        # Worker с processing loop
tests/
├── conftest.py       # Fixtures
├── test_health.py    # Health endpoint tests (3)
├── test_auth.py      # Authentication tests (8)
├── test_routes.py    # Tracking endpoints tests (12)
├── test_queue.py     # Queue producer/consumer tests (10)
└── test_integration.py # End-to-end integration tests (2)
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
3. **HMAC signature duplicate timestamp**: Исправлено дублирование timestamp в HMAC подписи
   - `canonical_query` уже содержал `ts=<value>`
   - Код ошибочно добавлял `ts` повторно → `...&ts=123123`
   - Теперь: `message = canonical_query` (без дублирования)

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

## Реализованные фичи (Этап 3)

### Модель данных (`app/core/models.py`)
- **InternalEvent**: внутренняя модель события для очереди
  - `event_type`, `event_id`, `received_at`, `payload`, `attempt`, `source_meta`
  - Методы сериализации: `to_stream_fields()`, `from_stream_fields()`

### Producer (`app/queue/producer.py`)
- **EventProducer**:
  - `enqueue()` — добавление события в Redis Stream через `xadd`
  - `check_duplicate()` — проверка дедупликации через Redis key `dedup:<event_id>`
  - `mark_processed()` — установка dedup key с TTL (7 дней)
  - `move_to_dlq()` — перенос события в DLQ stream с причиной и last_error

### Consumer (`app/queue/consumer.py`)
- **EventConsumer**:
  - `ensure_consumer_group()` — создание Consumer Group (mkstream=True)
  - `read_events()` — чтение через `xreadgroup` с блокировкой
  - `ack_message()` — подтверждение обработки через `xack`
  - `get_pending_messages()` — получение зависших сообщений через `xautoclaim`

### Worker (`app/worker/run.py`)
- Подключение к Redis с проверкой connectivity
- Создание Consumer Group при старте
- Processing loop: чтение → обработка → ack
- Graceful shutdown через signal handlers (SIGTERM, SIGINT)
- Пока заглушка отправки в AppsFlyer (sleep 0.1s)

### Интеграция в API (`app/api/routes.py`)
- Dependency injection для Redis и Producer
- Проверка дубликатов перед постановкой в очередь
- Возврат статуса "Duplicate event" при повторной отправке
- Автоматическая постановка в `events:main` stream

### Тесты (35 passed)
- `test_queue.py`: 10 тестов producer/consumer
- `test_integration.py`: 2 integration теста (producer→consumer, dedup flow)
- Все существующие тесты обновлены для моков Redis/Producer

## Следующие шаги

1. Получить AppsFlyer API спецификацию через Context7
2. Реализовать AppsFlyer client с httpx
3. Реализовать mapper: InternalEvent → AppsFlyer request
