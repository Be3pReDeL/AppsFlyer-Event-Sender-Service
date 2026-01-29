# Project Context

## Статус разработки

### Завершённые задачи
- [x] **Bootstrap**: базовая структура проекта, конфигурация, health endpoints, Docker
- [x] **Bugfix**: Исправлен lru_cache в get_settings() и resource leak в _check_redis()
- [x] **Endpoint'ы + auth + валидация**: Реализованы /v1/track/registration и /v1/track/purchase с token и HMAC auth
- [x] **Очередь Redis Streams + базовый worker**: Producer, Consumer, InternalEvent model, дедупликация
- [x] **AppsFlyer client + mapper**: HTTP client, mapper, интеграция с worker
- [x] **Надёжность (retry/backoff/DLQ/pending reclaim)**: Retry logic с exponential backoff + jitter, DLQ после MAX_ATTEMPTS, reclaim pending messages

### В ожидании
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
├── appsflyer/
│   ├── models.py     # AppsFlyer API models
│   ├── mapper.py     # InternalEvent → AppsFlyer mapping
│   └── client.py     # HTTP client с httpx
└── worker/
    └── run.py        # Worker с processing loop
tests/
├── conftest.py       # Fixtures
├── test_health.py    # Health endpoint tests (3)
├── test_auth.py      # Authentication tests (8)
├── test_routes.py    # Tracking endpoints tests (12)
├── test_queue.py     # Queue producer/consumer tests (10)
├── test_integration.py # End-to-end integration tests (2)
├── test_mapper.py    # AppsFlyer mapper tests (7)
├── test_appsflyer_client.py # AppsFlyer client tests (8)
├── test_models.py    # InternalEvent serialization tests (2)
└── test_redis_unavailable.py # Redis failure tests (2)
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
| AppsFlyer API | `/websites/dev_appsflyer_hc_reference` | S2S Events API |

---

## Исправленные проблемы

1. **get_settings() lru_cache**: Убран `@lru_cache` для корректной работы с тестами и динамическими ENV изменениями
2. **Redis resource leak**: Добавлен `try-finally` в `_check_redis()` для гарантированного закрытия connection pool
3. **HMAC signature duplicate timestamp**: Исправлено дублирование timestamp в HMAC подписи
   - `canonical_query` уже содержал `ts=<value>`
   - Код ошибочно добавлял `ts` повторно → `...&ts=123123`
   - Теперь: `message = canonical_query` (без дублирования)
4. **InternalEvent serialization**: Неправильная сериализация payload/source_meta
   - `model_dump_json(include={"payload"})` создавал `{"payload": {...}}`
   - При десериализации получалась неправильная структура
   - Исправлено на `json.dumps(self.payload)` — правильная сериализация
5. **Redis unavailability handling**: AttributeError при недоступности Redis
   - Если Redis не подключился: `app.state.redis = None`
   - `_get_redis()` возвращал None без проверки → AttributeError в endpoint'ах
   - Теперь: проверка в `_get_redis()` с HTTPException 503
6. **TOCTOU race condition в дедупликации**: Конкурентные запросы могли оба пройти проверку дубликата
   - Последовательность: `check_duplicate()` → `enqueue()` → `mark_processed()`
   - Между check и mark был gap, где concurrent запрос мог пройти проверку
   - Решение: атомарная операция `check_and_mark_if_new()` через Redis `SET NX`
   - Теперь: одна операция check-and-set, гарантия идемпотентности
7. **Inconsistent backoff calculation**: Разные retry delays для первой попытки
   - AppsFlyerError: backoff с текущим attempt → increment
   - Unexpected error: increment → backoff с новым attempt
   - Результат: unexpected error ждал 2x дольше (attempt=0: 1s vs attempt=1: 2s)
   - Решение: единообразная логика — increment attempt → calculate backoff → sleep
   - Теперь: консистентные retry delays независимо от типа ошибки

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

## Реализованные фичи (Этап 4)

### AppsFlyer API Documentation (`docs/appsflyer_api.md`)
- Endpoint: `POST https://api2.appsflyer.com/inappevent/{app_id}`
- Аутентификация: Header `authentication: <dev_key>`
- Обязательные поля: `appsflyer_id`, `event_name`
- События: `af_complete_registration`, `af_purchase`
- Коды ответов: 200 (success), 400/401/403 (non-retryable), 429/5xx (retryable)

### AppsFlyer Models (`app/appsflyer/models.py`)
- **AppsFlyerRequest**: request model для S2S API
  - appsflyer_id, event_name, event_value, customer_user_id, platform, event_time
- **AppsFlyerResponse**: response model

### AppsFlyer Mapper (`app/appsflyer/mapper.py`)
- **AppsFlyerMapper.map_event()**: конвертация InternalEvent → AppsFlyerRequest
- Event name mapping: `registration` → `af_complete_registration`, `purchase` → `af_purchase`
- Revenue mapping: `revenue` → `af_revenue` (string), `currency` → `af_currency`
- Platform normalization: `ios/iphone/ipad` → `iOS`, `android` → `Android`
- Device IDs: `advertising_id`, `idfa`, `android_id` → `device_ids` object
- Custom data: merge `custom_data` dict в `event_value`

### AppsFlyer Client (`app/appsflyer/client.py`)
- **AppsFlyerClient**: async HTTP client с httpx
- Строгие таймауты (connect/read/write/pool)
- Headers: `authentication: <dev_key>`, `Content-Type: application/json`
- Обработка ответов:
  - 2xx → success
  - 429 → retryable (с Retry-After header)
  - 4xx → non-retryable (DLQ)
  - 5xx → retryable
  - Timeout/Network → retryable
- Error classification через AppsFlyerError.retryable

### Worker Integration (`app/worker/run.py`)
- Инициализация AppsFlyerClient при старте
- Processing: map_event() → send_event() → ack()
- Обработка AppsFlyerError (retryable vs non-retryable)
- Логирование успеха/ошибок с event_id

### Configuration
- Добавлено `APPSFLYER_APP_ID` (для iOS: id123, для Android: com.app.name)
- Обновлён `.env.example` и `docker-compose.yml`

### Тесты (54 passed)
- `test_mapper.py`: 7 тестов mapper (registration, purchase, platform normalization, custom data)
- `test_appsflyer_client.py`: 8 тестов client (success, errors, timeout, network)
- Все тесты используют respx для мокирования HTTP запросов

## Исправленные баги (Этап 4+)

### Bug 5: Дублирование определений `_get_redis`/`_get_producer` (Keitaro POST refactor)
**Файл**: `app/api/routes.py`
**Описание**: Функции `_get_redis` и `_get_producer` были определены дважды:
- Первые определения (строки 28-51): с правильной проверкой `redis is None` → HTTPException 503
- Вторые определения (строки 247-257): без проверки безопасности

Вторые определения затеняли первые, что приводило к обходу проверки на доступность Redis и вызывало AttributeError вместо корректной обработки ошибки 503.

**Исправление**: Удалены дублирующиеся определения (строки 247-257). Оставлены оригинальные определения с проверкой безопасности.

**Тесты**: `test_tracking_endpoint_redis_unavailable`, `test_tracking_endpoint_redis_available`

## Реализованные фичи (Этап 5: Надёжность)

### Worker Retry Logic (`app/worker/run.py`)
- **Exponential backoff с jitter**:
  - Формула: `delay = base * (2^attempt)` с cap на `BACKOFF_MAX_SECONDS`
  - Jitter: ±25% для предотвращения thundering herd
  - Минимальная задержка: 0.1s
- **MAX_ATTEMPTS check**: события с `attempt >= MAX_ATTEMPTS` → DLQ
- **Retryable errors** (5xx, 429, timeout, network):
  - Sleep backoff
  - Increment attempt
  - Re-enqueue в main stream
  - Ack original message
- **Non-retryable errors** (4xx, mapping errors):
  - Immediate move to DLQ
  - Ack message
- **mark_processed()**: устанавливает dedup key после успешной отправки

### Reclaim Pending Messages
- **Периодическая проверка**: каждые 30 секунд в processing loop
- **xautoclaim**: reclaim messages idle > `PENDING_CLAIM_MS` (60s по умолчанию)
- **Обработка**: reclaimed messages обрабатываются так же как новые
- **Защита от зависания**: события не теряются если worker падает

### Dead Letter Queue (DLQ)
- **Причины попадания в DLQ**:
  - `max_attempts_exceeded` — исчерпаны попытки отправки
  - `non_retryable_appsflyer_error` — 4xx ошибка от AppsFlyer
  - `mapping_error` — ошибка валидации/маппинга события
- **Метаданные**: `dlq_reason`, `last_error` (обрезано до 500 символов)
- **Stream**: `events:dlq` (конфигурируемо)

### Тесты (64 passed)
- **test_worker_retry.py**: 9 новых тестов
  - Exponential backoff calculation
  - MAX_ATTEMPTS → DLQ
  - Retryable errors → re-enqueue
  - Non-retryable errors → DLQ
  - Mapping errors → DLQ
  - Successful processing → mark_processed + ack
  - Pending messages reclaim
  - 429 rate limit handling
  - Unexpected errors retry

## Следующие шаги

1. Финальная документация (README.md, API examples)
2. Rate limiting implementation
3. Smoke/load test
4. Docker Compose verification
