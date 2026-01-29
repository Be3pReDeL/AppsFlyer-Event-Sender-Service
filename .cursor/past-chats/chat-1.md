# Разработка приложения по техзаданию
_Exported on 29.01.2026 at 21:42:20 GMT+3 from Cursor (2.4.22)_

---

**User**

Начни разработку приложения на основе файла @.cursor/production/production.md , который содержит полное техническое задание. Используй MCP-сервер context7 для доступа к необходимым документациям. При работе обязательно используй файл @.cursor/context/context.md  для:
	•	сохранения информации, важной для понимания архитектуры и контекста проекта;
	•	использования этой информации при выполнении текущих задач.

Следуй следующему рабочему процессу:
	1.	За один запрос выполняй одну отдельную умеренно крупную задачу, не пытаясь разработать всё приложение сразу.
	2.	В самом начале приступи к работе с проектирования базовой архитектуры приложения, затем постепенно переходи к проектированию и разработке конкретных функций.
	3.	После завершения каждой задачи:
	•	выполняй тестовый билд и исправляй ошибки, если они обнаружатся;
	•	помечай задачу как выполненную в @context.md;
	•	обновляй информацию, важную для понимания контекста проекта, в этом же файле, дополняя его.
	4.	Делай коммит и пуш в Git согласно лучшим практикам. Если репозиторий ещё не создан — создай его.

---

**Cursor**

Начну с изучения технического задания и текущего контекста проекта.

Прочитаю существующие файлы и проверю структуру MCP Context7 для получения документации.

Получу документацию по FastAPI и Redis для проектирования архитектуры.

Теперь у меня достаточно информации для начала работы. Создам todo-список и начну с первого этапа - Bootstrap (каркас проекта).

Начинаю создание базовой структуры проекта.

Теперь создам виртуальное окружение, установлю зависимости и проверю код.

Тесты прошли. Теперь проверю Docker build.

## Этап 1: Bootstrap завершён

**Выполнено:**

1. **Структура проекта** — создана согласно ТЗ:
   - `app/` — основной код (api, core, queue, appsflyer, worker)
   - `tests/` — тесты
   - `docs/` — документация (references.md, decisions.md, appsflyer_api.md)
   - `docker/` — Dockerfile для API и Worker

2. **Конфигурация** (`app/core/config.py`):
   - Pydantic Settings с поддержкой `.env` файлов
   - Все параметры из ТЗ: AUTH_MODE, API_TOKENS, REDIS_URL, APPSFLYER_*, RATE_LIMIT_* и др.

3. **Логирование** (`app/core/logging.py`):
   - Structlog с JSON/console форматами
   - Автоматическое маскирование sensitive данных (token, sig, password)

4. **Health endpoints**:
   - `GET /health/live` — liveness probe
   - `GET /health/ready` — readiness probe (проверяет Redis)

5. **Docker**:
   - `docker/Dockerfile.api` — gunicorn + uvicorn workers
   - `docker/Dockerfile.worker` — worker процесс
   - `docker-compose.yml` — api + worker + redis

6. **Тесты** — 3 теста для health endpoints (все проходят)

**Коммит**: `feat(bootstrap): add project structure, config, health endpoints, docker`

**Push не удался** — репозиторий на GitHub не найден. Нужно создать репозиторий или обновить remote URL.

---

**Следующий этап**: Endpoint'ы `/v1/track/registration` и `/v1/track/purchase` с token-based аутентификацией, валидацией и маскированием секретов.

Продолжить со следующим этапом?

---

**User**

Verify these issues exist and fix them:

Bug 1:
`get_settings()` is decorated with `@lru_cache`, which globally caches the `Settings` instance. When this function is used as a FastAPI dependency with `Depends(get_settings)`, the cached instance persists across requests and environment variable changes won't be reflected. This violates the pydantic-settings design and could cause stale configuration in scenarios where environment variables are updated at runtime or between test runs.

Bug 2:
In `_check_redis()`, if `await client.ping()` at line 88 raises an exception, the subsequent `await client.aclose()` at line 89 is never executed. The connection pool is left open, causing a resource leak. Each failed health check leaves an unclosed connection pool, which can exhaust system resources over time. The cleanup must be guaranteed via a `finally` block or try-finally structure.

 @app/core/config.py:91-95 @app/api/health.py:81-93 

---

**Cursor**

Проверю указанные проблемы и исправлю их.

Проверил код — обе проблемы подтверждаются. Исправляю:

**Bug 1**: `@lru_cache` кэширует `Settings` глобально, что нарушает изоляцию тестов и блокирует runtime изменения ENV.

**Bug 2**: Если `ping()` выбросит исключение, `aclose()` не выполнится — утечка connection pool.

Проверю, что исправления не сломали тесты:

Тесты прошли. Исправлю whitespace warning:

Коммит исправлений:

Обновлю контекст проекта:

## ✅ Исправления выполнены

### Bug 1: `@lru_cache` в `get_settings()`

**Проблема**: Глобальное кэширование блокировало изменения ENV и нарушало изоляцию тестов.

**Исправление**:
```python
# Было:
@lru_cache
def get_settings() -> Settings:
    return Settings()

# Стало:
def get_settings() -> Settings:
    """Get settings instance.

    Note: Not cached to ensure environment variable changes are reflected
    in tests and runtime configuration updates.
    """
    return Settings()
```

### Bug 2: Resource leak в `_check_redis()`

**Проблема**: Если `ping()` выбрасывал исключение, `aclose()` не вызывался → утечка connection pool.

**Исправление**:
```python
# Было:
try:
    client = aioredis.from_url(redis_url, decode_responses=True)
    await client.ping()
    await client.aclose()  # Пропускается при exception
    return True
except Exception as e:
    return False

# Стало:
client = aioredis.from_url(redis_url, decode_responses=True)
try:
    await client.ping()
    return True
except Exception as e:
    return False
finally:
    # Гарантированное закрытие
    await client.aclose()
```

### Проверки
- ✅ Lint (ruff) — без ошибок
- ✅ Тесты (pytest) — 3/3 прошли
- ✅ Коммиты созданы:
  - `fix(config,health): remove lru_cache and fix redis resource leak`
  - `docs(context): update with bugfixes`

---

**User**

Теперь продолжи разработку на основе файла @.cursor/production/production.md , который содержит полное техническое задание. Используй MCP-сервер context7 для доступа к необходимым документациям. При работе обязательно используй файл @.cursor/context/context.md  для:
	•	сохранения информации, важной для понимания архитектуры и контекста проекта;
	•	использования этой информации при выполнении текущих задач.

Следуй следующему рабочему процессу:
	1.	За один запрос выполняй одну отдельную умеренно крупную задачу, не пытаясь разработать всё приложение сразу.
	2.	После завершения каждой задачи:
	•	выполняй тестовый билд и исправляй ошибки, если они обнаружатся;
	•	помечай задачу как выполненную в @.cursor/context/context.md ;
	•	обновляй информацию, важную для понимания контекста проекта, в этом же файле, дополняя его.
	3.	Делай коммит и пуш в Git согласно лучшим практикам. Если репозиторий ещё не создан — создай его.

---

**Cursor**

Продолжу разработку со второго этапа: реализация endpoint'ов с аутентификацией и валидацией.

Начинаю реализацию endpoint'ов с аутентификацией. Сначала создам модуль аутентификации:

Проверю работу API локально:

## ✅ Этап 2 завершён: Endpoint'ы + Аутентификация + Валидация

### Реализовано

**API Endpoints** (`app/api/routes.py`):
- `GET /v1/track/registration` — регистрация через query-параметры
- `POST /v1/track/registration` — регистрация через JSON body
- `GET /v1/track/purchase` — покупка через query-параметры  
- `POST /v1/track/purchase` — покупка через JSON body
- Все endpoint'ы возвращают `202 Accepted` с `event_id` и `queued_at`
- Автогенерация `event_id` если не передан клиентом

**Аутентификация** (`app/api/auth.py`):
- **Token mode**: `?token=<value>` с поддержкой множественных токенов через `API_TOKENS`
- **HMAC mode**: `?key=<id>&ts=<timestamp>&sig=<signature>`
  - HMAC-SHA256 подпись: `canonical_query + timestamp`
  - Защита от timestamp skew (±300 секунд)
  - Constant-time comparison для защиты от timing attacks
- Автоматическое маскирование токенов/подписей в логах

**Валидация** (`app/api/schemas.py`):
- `RegistrationRequest`: platform, appsflyer_id, customer_user_id, registration_method
- `PurchaseRequest`: revenue (≥0, required), currency (3 chars, required), product_id, order_id
- Автонормализация: `platform` → lowercase, `currency` → uppercase
- Pydantic v2 validation с подробными сообщениями об ошибках

**Обработка ошибок**:
- `401 Unauthorized` — auth failed
- `400 Bad Request` — validation error (custom)
- `422 Unprocessable Entity` — Pydantic validation error
- Специализированные exception handlers в `app/main.py`

### Тесты (23/23 passed)
- `test_auth.py`: 8 тестов token/HMAC auth
- `test_routes.py`: 12 тестов endpoints
- `test_health.py`: 3 теста health checks

### Коммит
```
feat(api): add tracking endpoints with token/HMAC auth
```

### Следующий этап
3. **Очередь Redis Streams + базовый worker** — постановка событий в Redis Streams и чтение worker'ом

---

**Статус**: Endpoint'ы работают, принимают запросы, валидируют данные, но пока не ставят события в очередь (возвращают 202 напрямую). Это будет реализовано на следующем этапе.

---

**User**

Verify these issues exist and fix them:

Bug 1:
The HMAC signature computation includes the `ts` parameter twice in the message. The `canonical_query` already contains `ts=<value>` from all sorted query parameters, then the code appends `ts` again, creating a message like `...&ts=123123` instead of `...&ts=123`. This causes valid signatures from correctly-implemented clients to fail authentication because the expected signature won't match.

 @app/api/auth.py:108-119 @tests/test_auth.py:128-139 

---

**Cursor**

Проверю указанную проблему:

Проблема подтверждается! В строке 119 `app/api/auth.py`:

```python
message = f"{canonical_query}{ts}".encode()
```

`canonical_query` уже содержит `ts=<value>` из всех отсортированных параметров, а затем добавляется еще раз просто значение `{ts}`.

**Результат**: `appsflyer_id=device-123&key=test-key&ts=17065432101706543210` (timestamp дублируется)

**Ожидается**: `appsflyer_id=device-123&key=test-key&ts=1706543210` (timestamp один раз)

Исправляю:

Проверяю, что исправление работает:

## ✅ Исправление HMAC Bug

**Проблема**: В HMAC аутентификации timestamp дублировался в сообщении для подписи.

### До исправления:
```python
canonical_query = "appsflyer_id=device-123&key=test-key&ts=1706543210"
message = f"{canonical_query}{ts}"  # ts = "1706543210"
# Результат: "...&ts=17065432101706543210" ❌
```

### После исправления:
```python
canonical_query = "appsflyer_id=device-123&key=test-key&ts=1706543210"
message = canonical_query  # ts уже внутри
# Результат: "...&ts=1706543210" ✅
```

### Последствия бага
Валидные подписи от корректно реализованных клиентов **всегда отклонялись**, так как:
1. Клиент создавал подпись от `canonical_query`
2. Сервер проверял подпись от `canonical_query + ts` (с дублированием)
3. Подписи не совпадали → 401 Unauthorized

### Исправления
- `app/api/auth.py`: строка 119 — убрано `{ts}` из `message`
- `tests/test_auth.py`: строка 138 — обновлен тест для корректной генерации подписи

### Проверка
- ✅ Все 23 теста проходят
- ✅ HMAC аутентификация теперь работает корректно
- ✅ Коммит: `fix(auth): remove duplicate timestamp in HMAC signature`

---

**Статус**: Баг исправлен. HMAC аутентификация теперь совместима с правильно реализованными клиентами.

---

**User**

Теперь продолжи разработку на основе файла @.cursor/production/production.md , который содержит полное техническое задание. Используй MCP-сервер context7 для доступа к необходимым документациям. При работе обязательно используй файл @.cursor/context/context.md  для:
	•	сохранения информации, важной для понимания архитектуры и контекста проекта;
	•	использования этой информации при выполнении текущих задач.

Следуй следующему рабочему процессу:
	1.	За один запрос выполняй одну отдельную умеренно крупную задачу, не пытаясь разработать всё приложение сразу.
	2.	После завершения каждой задачи:
	•	выполняй тестовый билд и исправляй ошибки, если они обнаружатся;
	•	помечай задачу как выполненную в @.cursor/context/context.md ;
	•	обновляй информацию, важную для понимания контекста проекта, в этом же файле, дополняя его.
	3.	Делай коммит и пуш в Git согласно лучшим практикам. Если репозиторий ещё не создан — создай его.

---

**Cursor**

Продолжаю разработку. Следующий этап — **Очередь Redis Streams + базовый worker**.

## ✅ Этап 3 завершён: Очередь Redis Streams + базовый worker

### Реализовано

**Модель данных** (`app/core/models.py`):
- `InternalEvent` — внутреннее представление события для очереди
- Поля: `event_type`, `event_id`, `received_at`, `payload`, `attempt`, `source_meta`
- Сериализация для Redis Streams: `to_stream_fields()` / `from_stream_fields()`

**Producer** (`app/queue/producer.py`):
- `enqueue()` — добавление события в `events:main` через `xadd`
- `check_duplicate()` — проверка через Redis key `dedup:<event_id>`
- `mark_processed()` — установка dedup key с TTL 7 дней
- `move_to_dlq()` — перенос в `events:dlq` с причиной и последней ошибкой

**Consumer** (`app/queue/consumer.py`):
- `ensure_consumer_group()` — создание Consumer Group (обработка `BUSYGROUP`)
- `read_events()` — чтение через `xreadgroup` с блокировкой
- `ack_message()` — подтверждение обработки через `xack`
- `get_pending_messages()` — reclaim зависших сообщений через `xautoclaim`

**Worker** (`app/worker/run.py`):
- Подключение к Redis с проверкой connectivity
- Инициализация Consumer Group при старте
- Processing loop: `read_events()` → `_process_event()` → `ack_message()`
- Graceful shutdown через SIGTERM/SIGINT
- Обработка событий (пока заглушка — `sleep 0.1s`)

**Интеграция в API** (`app/api/routes.py`):
- Dependency injection: `_get_redis()`, `_get_producer()`
- Проверка дубликатов перед enqueue
- Автоматическая постановка в очередь после валидации
- Возврат `"Duplicate event (already processed)"` при повторе

### Тесты (35/35 passed)
- `test_queue.py`: 10 unit тестов (producer/consumer)
- `test_integration.py`: 2 integration теста (producer→consumer, dedup)
- Обновлены существующие тесты с моками Redis/Producer

### Коммит
```
feat(queue): add Redis Streams producer, consumer and worker
```

### Текущее состояние

**Работает:**
- API принимает события → проверяет auth → валидирует → ставит в Redis Streams
- Worker читает из Consumer Group → обрабатывает (заглушка) → подтверждает
- Дедупликация предотвращает повторную обработку

**Не реализовано:**
- Отправка в AppsFlyer (следующий этап)
- Retry/backoff/DLQ логика при ошибках
- Pending messages reclaim в worker loop

---

**Следующий этап**: AppsFlyer client + mapper (получить спецификацию через Context7)

---

**User**

Verify these issues exist and fix them:

Bug 1:
The `to_stream_fields()` method serializes `payload` and `source_meta` using `model_dump_json(include={...})`, which produces JSON strings like `{"payload": {...}}` and `{"source_meta": {...}}`. When `from_stream_fields()` calls `json.loads()` on these strings, it deserializes to dicts with the field name as a key, not the field value. This causes the reconstruction to fail because the code expects `json.loads(fields["payload"])` to return the payload dict directly, not `{"payload": {...}}`.

Bug 2:
If Redis connection fails during application startup (in the lifespan function), `app.state.redis` is set to `None` (line 45 of app/main.py). However, the `_get_redis` dependency function (line 28-30 of app/api/routes.py) directly returns this None value without any checks. When endpoints use the producer, they try to call methods on the None object, causing an AttributeError. The endpoints should either validate that redis exists before using it, or the `_get_redis` dependency should raise an appropriate HTTP error.

 @app/core/models.py:1 @app/api/routes.py:27-30 @app/main.py:41-45 

---

**Cursor**

Проверю указанные проблемы:

Проблемы подтверждаются. Исправляю:

**Bug 1**: `model_dump_json(include={"payload"})` создаёт `{"payload": {...}}` вместо `{...}`. При десериализации `json.loads()` получает неправильную структуру.

**Bug 2**: При ошибке Redis `app.state.redis = None`, но `_get_redis()` возвращает None без проверки → AttributeError в endpoint'ах.

Создам тесты для проверки исправлений:

## ✅ Исправления завершены

### Bug 1: Неправильная сериализация InternalEvent

**Проблема**: `model_dump_json(include={"payload"})` создавал вложенную структуру:
```python
# Было:
"payload": '{"payload": {"appsflyer_id": "123"}}' 
# json.loads() → {"payload": {"appsflyer_id": "123"}}
# Ожидалось: {"appsflyer_id": "123"}
```

**Исправление**:
```python
# Было:
"payload": self.model_dump_json(include={"payload"})

# Стало:
"payload": json.dumps(self.payload)
```

Теперь сериализация/десериализация работает корректно:
- `to_stream_fields()` → `{"payload": '{"appsflyer_id": "123"}'}`
- `from_stream_fields()` → `json.loads('{"appsflyer_id": "123"}')` → `{"appsflyer_id": "123"}` ✅

### Bug 2: AttributeError при недоступности Redis

**Проблема**: 
```python
# app/main.py:45
app.state.redis = None  # При ошибке подключения

# app/api/routes.py:30
return request.app.state.redis  # Возвращает None

# Endpoint пытается вызвать методы:
producer = get_producer(redis=None, ...)  # AttributeError!
```

**Исправление**:
```python
async def _get_redis(request: Request) -> aioredis.Redis:
    redis = request.app.state.redis
    if redis is None:
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable (Redis connection failed)",
        )
    return redis
```

Теперь endpoint'ы корректно возвращают **503 Service Unavailable** при недоступности Redis.

### Новые тесты (4)
- `test_models.py`: 2 теста roundtrip сериализации (включая вложенные структуры)
- `test_redis_unavailable.py`: 2 теста обработки Redis failure (503 vs 202)

### Результаты
- ✅ Все 39 тестов проходят
- ✅ Lint проверки пройдены
- ✅ Коммиты:
  - `fix(queue,api): fix serialization bug and Redis unavailability handling`
  - `docs(context): add bugs 4-5 to known issues`

**Система теперь корректно**:
- Сериализует/десериализует события в/из Redis Streams
- Обрабатывает недоступность Redis с graceful degradation (503)

---

**User**

Теперь продолжи разработку на основе файла @.cursor/production/production.md , который содержит полное техническое задание. Используй MCP-сервер context7 для доступа к необходимым документациям. При работе обязательно используй файл @.cursor/context/context.md  для:
	•	сохранения информации, важной для понимания архитектуры и контекста проекта;
	•	использования этой информации при выполнении текущих задач.

Следуй следующему рабочему процессу:
	1.	За один запрос выполняй одну отдельную умеренно крупную задачу, не пытаясь разработать всё приложение сразу.
	2.	После завершения каждой задачи:
	•	выполняй тестовый билд и исправляй ошибки, если они обнаружатся;
	•	помечай задачу как выполненную в @.cursor/context/context.md ;
	•	обновляй информацию, важную для понимания контекста проекта, в этом же файле, дополняя его.
	3.	Делай коммит и пуш в Git согласно лучшим практикам. Если репозиторий ещё не создан — создай его.

---

**Cursor**

Продолжаю разработку. Следующий этап — **AppsFlyer client + mapper**. Сначала получу актуальную документацию AppsFlyer API через Context7.

Получил документацию AppsFlyer API. Обновлю `docs/appsflyer_api.md` и создам mapper с client.

## ✅ Этап 4 завершён: AppsFlyer Client + Mapper

### Реализовано

**AppsFlyer API Documentation** (`docs/appsflyer_api.md`):
- Получена актуальная спецификация через Context7 MCP
- Endpoint: `POST https://api2.appsflyer.com/inappevent/{app_id}`
- Аутентификация: Header `authentication: <dev_key>`
- Обязательные поля: `appsflyer_id`, `event_name`
- События: `af_complete_registration` (регистрация), `af_purchase` (покупка)
- Классификация ошибок: 2xx (success), 400/401/403 (non-retryable), 429/5xx (retryable)

**AppsFlyer Models** (`app/appsflyer/models.py`):
- `AppsFlyerRequest` — модель запроса к S2S API
- `AppsFlyerResponse` — модель ответа

**AppsFlyer Mapper** (`app/appsflyer/mapper.py`):
- `map_event()` — конвертация `InternalEvent` → `AppsFlyerRequest`
- Маппинг event_name: `registration` → `af_complete_registration`, `purchase` → `af_purchase`
- Маппинг revenue: `revenue` → `af_revenue` (string), `currency` → `af_currency`
- Маппинг purchase fields: `product_id` → `af_content_id`, `quantity` → `af_quantity`, `order_id` → `af_order_id`
- Нормализация platform: `ios/iphone/ipad` → `iOS`, `android` → `Android`
- Device IDs: объединение `advertising_id`, `idfa`, `android_id` в `device_ids`
- Custom data: merge в `event_value`

**AppsFlyer Client** (`app/appsflyer/client.py`):
- Async HTTP client с `httpx.AsyncClient`
- Строгие таймауты для connect/read/write/pool
- Headers: `authentication: <dev_key>`, `Content-Type: application/json`
- Классификация ошибок:
  - **2xx** → success
  - **429** → retryable (+ извлечение `Retry-After` header)
  - **400/401/403** → non-retryable (→ DLQ)
  - **5xx** → retryable
  - **Timeout/Network** → retryable
- Правильная обработка `AppsFlyerError` (не оборачивает в Exception)

**Worker Integration** (`app/worker/run.py`):
- Инициализация `AppsFlyerClient` при старте worker
- Processing flow: `map_event()` → `send_event()` → `ack_message()`
- Обработка `AppsFlyerError` с флагом `retryable`
- Обработка `ValueError` при mapping errors
- Логирование успеха и ошибок с `event_id`

**Configuration**:
- Добавлено `APPSFLYER_APP_ID` в конфигурацию
- Для iOS: префикс `id` (например `id123456789`)
- Для Android: package name (например `com.example.app`)
- Обновлены `.env.example` и `docker-compose.yml`

### Тесты (54/54 passed)
- `test_mapper.py`: 7 тестов (registration, purchase, platform normalization, custom data, device_ids)
- `test_appsflyer_client.py`: 8 тестов (success, 400/401/429/500, timeout, network)
- Используется `respx` для мокирования HTTP запросов к AppsFlyer

### Коммит
```
feat(appsflyer): add client, mapper and worker integration
```

---

**Текущее состояние**: Worker теперь **реально отправляет события в AppsFlyer**. При успехе — ack, при ошибке — логирует с флагом retryable.

**Не реализовано** (следующий этап):
- Retry logic с exponential backoff + jitter
- Автоматический перенос в DLQ после MAX_ATTEMPTS
- Reclaim pending messages в worker loop

---

**User**

давай использовать версию api3 и добавим передачу app_id как параметра в endpoint, чтобы сервис мог отправлять события на разные приложения. после завершения работы приведи пример запросов для трекинга регистрации и покупки

---

**Cursor**

Обновлю сервис для использования API v3 и добавлю поддержку `app_id` как параметра запроса.

Готово! Обновлён сервис для использования AppsFlyer API v3 и добавлена поддержка `app_id` как параметра запроса.

## ✅ Изменения

### Миграция на API v3
- **Base URL**: `https://api3.appsflyer.com` (вместо api2)
- **Endpoint**: `POST https://api3.appsflyer.com/inappevent/{app_id}`

### Поддержка мультиприложений
- **Конфигурация**: `APPSFLYER_DEFAULT_APP_ID` — fallback app_id
- **Параметр запроса**: `app_id` — переопределение для каждого события
- **Логика**: используется переданный `app_id`, иначе default из конфигурации

---

## 📋 Примеры запросов

### 1️⃣ Регистрация (GET, минимальный)

```bash
curl -X GET "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
appsflyer_id=1658954220-1234567890&\
platform=ios"
```

**Ответ:**
```json
{
  "status": "accepted",
  "event_id": "reg_a1b2c3d4e5f6",
  "queued_at": "2026-01-29T15:30:45.123Z",
  "message": "Event queued for processing"
}
```

### 2️⃣ Регистрация (GET, полный с app_id)

```bash
curl -X GET "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
app_id=id123456789&\
appsflyer_id=1658954220-1234567890&\
customer_user_id=user_12345&\
platform=ios&\
registration_method=email&\
event_id=reg_custom_001"
```

### 3️⃣ Покупка (GET, минимальный)

```bash
curl -X GET "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
appsflyer_id=1658954220-9876543210&\
revenue=19.99&\
currency=USD&\
platform=android"
```

### 4️⃣ Покупка (POST JSON, полный)

```bash
curl -X POST "http://localhost:8000/v1/track/purchase?token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "com.example.myapp",
    "appsflyer_id": "1658954220-9876543210",
    "customer_user_id": "user_67890",
    "revenue": 49.99,
    "currency": "USD",
    "product_id": "premium_yearly",
    "order_id": "order_abc456",
    "quantity": 1,
    "platform": "Android"
  }'
```

### 5️⃣ Мультиприложения (iOS + Android)

**iOS app:**
```bash
curl -X GET "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
app_id=id123456789&\
appsflyer_id=ios-device-123&\
revenue=9.99&\
currency=USD&\
platform=ios"
```

**Android app:**
```bash
curl -X GET "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
app_id=com.example.androidapp&\
appsflyer_id=android-device-456&\
revenue=14.99&\
currency=EUR&\
platform=android"
```

---

## 📝 Полная документация

- **[Примеры API](docs/api_examples.md)** — детальные примеры с HMAC auth, дубликатами
- **[AppsFlyer API](docs/appsflyer_api.md)** — спецификация S2S API
- **[References](docs/references.md)** — использованные источники Context7

**Тесты**: 55/55 passed ✅  
**Коммит**: `feat(appsflyer): migrate to API v3 and add per-request app_id support`

---

**User**

В Keitaro поддерживаются только GET и POST методы запросов, однако к POST запросу нельзя добавить тело запроса. Мне кажется, что логически было бы верно использовать POST-запросы для трекинга событий из Keitaro в AppsFlyer, поэтому сделай endpoint'ы принимающие POST-запросы, но данные принимаются из query-параметров 

---

**Cursor**

Понял. Изменю POST endpoint'ы, чтобы они принимали данные из query-параметров (как GET), но использовали метод POST для семантической корректности.

Тесты валидации падают, потому что Pydantic ValidationError выбрасывается внутри функции. Добавлю обработку:

## ✅ Готово! POST endpoints теперь используют query-параметры

### Изменения

**Совместимость с Keitaro**:
- POST endpoint'ы теперь принимают данные из **query-параметров** (не из body)
- GET endpoint'ы остались без изменений (обратная совместимость)
- POST семантически корректнее для событий (side effects)

**API v3 + Multi-app**:
- Base URL: `https://api3.appsflyer.com`
- Параметр `app_id` для отправки в разные приложения
- Fallback на `APPSFLYER_DEFAULT_APP_ID` если не указан

---

## 📋 Примеры запросов для Keitaro

### 1️⃣ Регистрация (минимальный POST)

**URL для Keitaro S2S Postback:**
```
http://your-server:8000/v1/track/registration?token=YOUR_TOKEN&appsflyer_id={sub1}&platform=ios
```

**Тестовый curl:**
```bash
curl -X POST "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
appsflyer_id=1658954220-1234567890&\
platform=ios"
```

**Ответ:**
```json
{
  "status": "accepted",
  "event_id": "reg_a1b2c3d4e5f6",
  "queued_at": "2026-01-29T15:30:45.123Z",
  "message": "Event queued for processing"
}
```

---

### 2️⃣ Регистрация (полный POST с маркерами Keitaro)

**URL для Keitaro:**
```
http://your-server:8000/v1/track/registration?token=YOUR_TOKEN&app_id=id123456789&appsflyer_id={sub1}&customer_user_id={sub2}&platform=ios&registration_method=email&event_id=reg_{click_id}
```

**Макросы Keitaro:**
- `{sub1}` → appsflyer_id (обязательно)
- `{sub2}` → customer_user_id
- `{click_id}` → для event_id (дедупликация)

**Тестовый curl:**
```bash
curl -X POST "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
app_id=id123456789&\
appsflyer_id=1658954220-1234567890&\
customer_user_id=user_12345&\
platform=ios&\
registration_method=email&\
event_id=reg_custom_001"
```

---

### 3️⃣ Покупка (минимальный POST)

**URL для Keitaro:**
```
http://your-server:8000/v1/track/purchase?token=YOUR_TOKEN&appsflyer_id={sub1}&revenue={payout}&currency=USD&platform=android
```

**Макросы Keitaro:**
- `{sub1}` → appsflyer_id
- `{payout}` → revenue (сумма)

**Тестовый curl:**
```bash
curl -X POST "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
appsflyer_id=1658954220-9876543210&\
revenue=19.99&\
currency=USD&\
platform=android"
```

**Ответ:**
```json
{
  "status": "accepted",
  "event_id": "purchase_7g8h9i0j1k2l",
  "queued_at": "2026-01-29T15:35:12.456Z",
  "message": "Event queued for processing"
}
```

---

### 4️⃣ Покупка (полный POST с маркерами Keitaro)

**URL для Keitaro:**
```
http://your-server:8000/v1/track/purchase?token=YOUR_TOKEN&app_id=com.example.myapp&appsflyer_id={sub1}&customer_user_id={sub2}&revenue={payout}&currency=USD&product_id={offer_id}&order_id=order_{click_id}&platform=android&event_id=purchase_{click_id}
```

**Макросы:**
- `{sub1}` → appsflyer_id
- `{sub2}` → customer_user_id
- `{payout}` → revenue
- `{offer_id}` → product_id
- `{click_id}` → для order_id и event_id

**Тестовый curl:**
```bash
curl -X POST "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
app_id=com.example.myapp&\
appsflyer_id=1658954220-9876543210&\
customer_user_id=user_67890&\
revenue=49.99&\
currency=USD&\
product_id=premium_yearly&\
order_id=order_abc456&\
platform=android&\
event_id=purchase_custom_002"
```

---

## 🎯 Мультиприложения

### iOS app

```
http://your-server:8000/v1/track/purchase?token=YOUR_TOKEN&app_id=id123456789&appsflyer_id={sub1}&revenue={payout}&currency=USD&platform=ios
```

### Android app

```
http://your-server:8000/v1/track/purchase?token=YOUR_TOKEN&app_id=com.example.androidapp&appsflyer_id={sub1}&revenue={payout}&currency=USD&platform=android
```

---

## ℹ️ Параметры

### Обязательные (Registration)
- `token` — API токен
- `appsflyer_id` — AppsFlyer device ID

### Обязательные (Purchase)
- `token` — API токен
- `appsflyer_id` — AppsFlyer device ID
- `revenue` — сумма покупки (число ≥0)
- `currency` — код валюты (3 символа, например USD, EUR)

### Опциональные
- `app_id` — AppsFlyer app ID (для iOS: `id123456789`, для Android: `com.app.name`)
- `customer_user_id` — ID пользователя
- `platform` — платформа (ios, android)
- `product_id` — ID товара
- `order_id` — ID заказа
- `quantity` — количество
- `event_id` — уникальный ID события (для дедупликации)
- `registration_method` — метод регистрации (email, social и т.д.)

---

## 📊 Проверка работы

### 1. Проверка health

```bash
curl http://your-server:8000/health/ready
```

Должен вернуть `200 OK` с `"status": "ok"`.

### 2. Проверка логов

```bash
# Docker
docker compose logs -f api
docker compose logs -f worker

# Локально
tail -f logs/app.log
```

### 3. Мониторинг метрик

```bash
curl http://your-server:8000/metrics
```

---

**Все тесты**: 55/55 ✅  
**Коммит**: `refactor(api): change POST endpoints to use query params for Keitaro`

