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
