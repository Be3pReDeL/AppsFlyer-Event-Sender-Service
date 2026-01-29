# Architectural Decisions

Ключевые архитектурные решения проекта.

## ADR-001: Redis Streams как очередь сообщений

**Статус**: Принято

**Контекст**: Необходим надёжный механизм очереди для асинхронной отправки событий в AppsFlyer.

**Решение**: Использовать Redis Streams вместо альтернатив (Kafka, RabbitMQ).

**Обоснование**:
- Простота деплоя — Redis уже используется для rate limiting и дедупликации
- Consumer Groups обеспечивают надёжную обработку с acknowledgment
- Поддержка pending entries для переобработки "зависших" сообщений
- Достаточная производительность для ожидаемой нагрузки

---

## ADR-002: Token-based аутентификация как базовый режим

**Статус**: Принято

**Контекст**: Keitaro не поддерживает HTTP headers в S2S postback.

**Решение**: Поддержать два режима:
1. Token-based (обязательный) — `?token=<secret>`
2. HMAC (опциональный) — `?key=<id>&ts=<timestamp>&sig=<signature>`

**Обоснование**:
- Token-based прост в настройке и достаточен для базовых сценариев
- HMAC добавляет защиту от replay-атак и утечки токена
- Ротация токенов поддерживается через список в конфигурации

---

## ADR-003: Lifespan context manager вместо on_startup/on_shutdown

**Статус**: Принято

**Контекст**: FastAPI поддерживает два способа управления жизненным циклом приложения.

**Решение**: Использовать `lifespan` async context manager.

**Обоснование**:
- Рекомендуемый подход в документации FastAPI
- Упрощает управление shared state между startup и shutdown
- on_startup/on_shutdown deprecated

---

## ADR-004: Структурное логирование с structlog

**Статус**: Принято

**Контекст**: Необходимы JSON-логи для production и читаемые логи для разработки.

**Решение**: Использовать structlog с переключаемым форматом (json/console).

**Обоснование**:
- Встроенная поддержка контекстных переменных (request_id, event_id)
- Автоматическое маскирование sensitive данных
- Совместимость со стандартной библиотекой logging

---

## ADR-005: Re-enqueue стратегия для retry вместо in-place retry

**Статус**: Принято

**Контекст**: Worker может обрабатывать retryable ошибки двумя способами:
1. In-place retry — повторные попытки в той же обработке сообщения
2. Re-enqueue — инкремент attempt и постановка обратно в очередь

**Решение**: Использовать re-enqueue подход.

**Обоснование**:
- **Fair scheduling**: ошибочные события не блокируют обработку новых событий
- **Backoff распределён во времени**: sleep не блокирует worker
- **Горизонтальное масштабирование**: re-enqueued события могут быть обработаны другими workers
- **Observability**: каждая попытка видна как отдельное сообщение в stream
- **Pending reclaim работает корректно**: зависшие сообщения не теряются

**Альтернатива (отклонена)**: In-place retry
- (+) Проще реализация
- (-) Блокирует worker на всё время backoff
- (-) Плохая изоляция ошибок — один медленный event блокирует других
- (-) Сложность с graceful shutdown

---

## ADR-006: Exponential backoff с jitter для retry

**Статус**: Принято

**Контекст**: Retryable ошибки должны обрабатываться с увеличением задержки.

**Решение**: Exponential backoff `base * (2^attempt)` с ±25% jitter, capped на `BACKOFF_MAX_SECONDS`.

**Обоснование**:
- **Exponential backoff**: предотвращает лавинообразное увеличение нагрузки при проблемах AppsFlyer
- **Jitter**: предотвращает thundering herd когда множество events ретраятся одновременно
- **Cap**: предотвращает слишком долгие задержки (максимум 60 секунд по умолчанию)
- **Configurable base/max**: адаптируется под конкретные SLA и характеристики AppsFlyer API

**Формула**:
```python
delay = min(base * (2 ** attempt), max)
jitter = random.uniform(-delay * 0.25, delay * 0.25)
final_delay = max(0.1, delay + jitter)
```

---

## ADR-007: DLQ для non-retryable и exhausted events

**Статус**: Принято

**Контекст**: Некоторые события не могут быть обработаны успешно:
- 4xx ошибки от AppsFlyer (validation, auth)
- Mapping errors (missing required fields)
- Исчерпаны MAX_ATTEMPTS

**Решение**: Перемещать такие события в Dead Letter Queue (`events:dlq`) с метаданными.

**Обоснование**:
- **Не теряем данные**: события доступны для анализа и ручной переобработки
- **Не блокируем очередь**: не ретраим бесконечно
- **Debugging**: `dlq_reason` и `last_error` помогают диагностике
- **Monitoring**: метрика `worker_dlq_total{reason}` для алертинга

**Метаданные DLQ**:
- `dlq_reason`: категория ошибки
- `last_error`: последнее сообщение об ошибке (обрезано до 500 символов)
- Все оригинальные поля события

---

## ADR-008: Pending messages reclaim каждые 30 секунд

**Статус**: Принято

**Контекст**: Worker может упасть во время обработки сообщения, оставляя его в pending state.

**Решение**: Periodically (каждые 30 секунд) вызывать `xautoclaim` для messages idle > `PENDING_CLAIM_MS`.

**Обоснование**:
- **Гарантия обработки**: события не теряются при сбоях worker
- **Настраиваемый min_idle**: баланс между повторной обработкой и ложным reclaim
- **xautoclaim автоматика**: Redis сам переназначает ownership
- **Периодичность 30s**: компромисс между latency восстановления и overhead

**Риски**:
- Duplicate processing возможен если worker медленный но не упал
- Митигация: deduplication keys и idempotent AppsFlyer requests

---

## ADR-009: Атомарная дедупликация через Redis SET NX

**Статус**: Принято

**Контекст**: Изначальная реализация дедупликации имела TOCTOU (time-of-check to time-of-use) race condition:
```python
is_duplicate = await check_duplicate(event_id)  # Check
if not is_duplicate:
    await enqueue(event)                        # Use
    await mark_processed(event_id)              # Mark
```

Между check и mark concurrent запросы с одинаковым `event_id` могут оба пройти проверку и оба enqueue'нуться, нарушая идемпотентность.

**Решение**: Использовать атомарную операцию Redis `SET key value NX EX ttl`.

**Реализация**:
```python
# Атомарная операция: check-and-set в одной команде
was_set = await redis.set("dedup:event_id", "1", nx=True, ex=ttl)
if not was_set:  # Key already exists - duplicate
    return "duplicate"
# Key was set successfully - new event, proceed to enqueue
```

**Обоснование**:
- **Атомарность**: Redis SET NX гарантирует, что только один concurrent запрос установит ключ
- **Гарантия идемпотентности**: невозможно дважды enqueue событие с одинаковым event_id
- **Performance**: одна Redis операция вместо трёх (exists + enqueue + setex)
- **Simplicity**: меньше кода, нет сложной синхронизации

**Альтернативы (отклонены)**:
- Distributed lock (Redis lock): сложнее, требует timeout management и lock cleanup
- Database transactions: требует другого storage backend (PostgreSQL)
- Lua script: избыточно для такой простой операции

---

## ADR-010: Консистентный backoff для всех retry errors

**Статус**: Принято

**Контекст**: Изначально backoff calculation выполнялся в разные моменты attempt lifecycle:
- AppsFlyerError: `backoff(current_attempt)` → `attempt++` → sleep → re-enqueue
- Unexpected error: `attempt++` → `backoff(new_attempt)` → sleep → re-enqueue

Это приводило к inconsistency: при attempt=0 AppsFlyerError ждал ~1s, а unexpected error ~2s для первой retry попытки.

**Решение**: Унифицировать порядок операций для всех retryable errors:
```python
attempt += 1
backoff_delay = calculate_backoff(attempt)
await sleep(backoff_delay)
await enqueue(event)
await ack(message)
```

**Обоснование**:
- **Консистентность**: одинаковый retry policy независимо от типа ошибки
- **Понятность**: attempt всегда соответствует номеру попытки (1-based после первой ошибки)
- **Предсказуемость**: логи показывают правильный attempt при retry
- **Справедливость**: все события обрабатываются с одинаковым backoff

**Влияние**:
- Тесты обновлены для проверки консистентности backoff
- Метрики `worker_retry_total{attempt}` теперь точнее отражают реальное количество попыток

---

## ADR-011: Redis-based Sliding Window Rate Limiting

**Статус**: Принято

**Контекст**: Production-сервис должен защищаться от злоупотреблений и DDoS-атак. Необходим rate limiting для ограничения частоты запросов per token/IP.

**Решение**: Реализовать Redis-based rate limiting с использованием Sorted Sets и sliding window algorithm.

**Алгоритм**:
```python
1. Remove old entries: zremrangebyscore(key, 0, current_time - window)
2. Count current: count = zcard(key)
3. If count >= burst: reject (429)
4. Add request: zadd(key, {current_time: current_time})
5. Set TTL: expire(key, window * 2)
```

**Обоснование**:
- **Sliding window**: более точный контроль vs fixed window (нет "reset burst" проблемы)
- **Redis Sorted Sets**: эффективная структура для time-series данных
  - O(log N) для zadd
  - O(log N + M) для zremrangebyscore
  - O(1) для zcard
- **Distributed**: работает с multiple API instances (shared state в Redis)
- **Configurable**: `RATE_LIMIT_RPS` и `RATE_LIMIT_BURST` через ENV
- **Fail-open**: на ошибках Redis пропускает requests (availability over strict limiting)

**Идентификация**:
- **Priority 1**: Hashed token (SHA256[:16]) — защита от token leakage в Redis
- **Priority 2**: IP address — fallback для requests без token
- Разные идентификаторы имеют независимые rate limits

**Headers**:
- `X-RateLimit-Limit`: burst capacity
- `X-RateLimit-Remaining`: оставшиеся requests
- `X-RateLimit-Reset`: unix timestamp когда limit сбросится
- `Retry-After`: seconds до reset (стандарт 429 response)

**Альтернативы (отклонены)**:
- **Fixed window**: проще, но позволяет burst на границах window (2x rate)
- **Token bucket**: сложнее реализация в Redis, требует atomic операции
- **In-memory rate limiting**: не работает с multiple instances, теряется при рестарте

**Риски и митигация**:
- **Redis latency**: rate limit check добавляет 1-2 Redis операции per request
  - Митигация: Redis operations быстрые (< 1ms), параллельно с auth check
- **Redis unavailable**: fail-open behavior
  - Митигация: health check на Redis connectivity
- **Clock skew**: timestamps могут отличаться между nodes
  - Митигация: Redis использует свой clock, consistency гарантируется

**Метрики** (будущее):
- `rate_limit_blocked_total{identifier_type}` — количество blocked requests
- `rate_limit_requests_total{identifier_type}` — общее количество requests
- `rate_limit_remaining{identifier_type}` (gauge) — текущий remaining count

---

## ADR-012: Единообразная обработка Pydantic ValidationError в GET/POST endpoints

**Статус**: Принято

**Контекст**: GET и POST purchase endpoints имели несогласованную обработку ошибок валидации. POST endpoint оборачивал создание `PurchaseRequest` в try-except блок для преобразования `PydanticValidationError` в HTTP 422, в то время как GET endpoint не делал этого, что приводило к HTTP 500.

**Решение**: Обернуть создание `PurchaseRequest` в try-except блок во всех endpoints (GET и POST) для единообразной обработки ошибок валидации.

**Обоснование**:
- **Консистентность API**: Одинаковые типы ошибок должны возвращать одинаковые HTTP коды
- **Правильная семантика**: 422 Unprocessable Entity правильный код для validation errors, не 500 Internal Server Error
- **Лучший DX**: Клиенты получают структурированные ошибки валидации вместо generic 500

**Код**:
```python
try:
    event_data = PurchaseRequest(...)
except PydanticValidationError as e:
    raise HTTPException(status_code=422, detail=e.errors()) from e
```

**Риски**: Нет. Это исправление бага, улучшающее корректность API.

---

## ADR-013: Явное преобразование datetime в ISO format для event_time

**Статус**: Принято

**Контекст**: В `AppsFlyerMapper.map_event()` значение `event_time` из payload бралось напрямую. Если payload содержал datetime объект из Pydantic (например, `received_at`), он передавался в `AppsFlyerRequest` без сериализации. При попытке JSON-сериализации через httpx это вызывало исключение, так как datetime не JSON-serializable.

**Решение**: Явно конвертировать `event_time` в ISO format string при извлечении из payload:

```python
if payload.get("event_time"):
    from datetime import datetime
    evt = payload["event_time"]
    event_time = evt.isoformat() if isinstance(evt, datetime) else str(evt)
elif event.received_at:
    event_time = event.received_at.isoformat()
```

**Обоснование**:
- **Корректность**: datetime объекты должны быть сериализованы в строки перед JSON encoding
- **Единообразие**: Все datetime значения преобразуются в ISO format одинаково
- **Отказоустойчивость**: Обрабатывает случаи, когда `event_time` уже строка

**Альтернативы (отклонены)**:
- **Custom JSON encoder**: Усложняет сериализацию, требует изменений в httpx client
- **Pydantic serialization**: Уже используется, но `model_dump()` возвращает datetime как есть для dict values

**Риски**: Нет. Это исправление бага, предотвращающее runtime errors при отправке событий.
