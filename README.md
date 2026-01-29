# AppsFlyer Event Sender Service

Production-ready веб-сервис для приёма S2S postback от Keitaro и надёжной отправки событий в AppsFlyer.

## Архитектура

```
Keitaro → API (FastAPI) → Redis Streams → Worker → AppsFlyer API
```

**Компоненты:**
- **API** — принимает HTTP-запросы, авторизует, валидирует, ставит в очередь
- **Worker** — обрабатывает события из очереди, отправляет в AppsFlyer с retry/backoff
- **Redis** — очередь (Streams), дедупликация, rate limiting

## Возможности

- **Аутентификация**: Token-based и HMAC режимы
- **Rate Limiting**: Sliding window алгоритм на Redis
- **Надёжность**: Retry с exponential backoff + jitter, DLQ для failed events
- **Дедупликация**: Атомарная проверка через Redis SET NX
- **Observability**: Prometheus metrics, structured JSON logs, health endpoints
- **Масштабирование**: Horizontal scaling workers, Redis Streams consumer groups

## Быстрый старт

### 1. Настройка окружения

```bash
cp .env.example .env
# Отредактируйте .env:
# - API_TOKENS: ваши токены для аутентификации
# - APPSFLYER_DEV_KEY: ключ разработчика AppsFlyer
# - APPSFLYER_DEFAULT_APP_ID: ID приложения (id123... для iOS, com.app.name для Android)
```

### 2. Запуск через Docker Compose

```bash
docker compose up -d
```

### 3. Проверка работоспособности

```bash
# Liveness probe
curl http://localhost:8000/health/live

# Readiness probe (проверяет Redis)
curl http://localhost:8000/health/ready

# Prometheus metrics
curl http://localhost:8000/metrics
```

## API Endpoints

### Health Checks

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/health/live` | GET | Liveness probe |
| `/health/ready` | GET | Readiness probe (проверяет Redis) |
| `/metrics` | GET | Prometheus metrics |

### Tracking Events

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/v1/track/registration` | GET/POST | Событие регистрации |
| `/v1/track/purchase` | GET/POST | Событие покупки |

> **Note**: POST endpoints используют query-параметры (совместимость с Keitaro)

## Примеры использования

### Регистрация (минимальный запрос)

```bash
curl -X POST "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
appsflyer_id=1658954220-1234567890&\
platform=ios"
```

### Регистрация (полный запрос)

```bash
curl -X POST "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
app_id=id123456789&\
appsflyer_id=1658954220-1234567890&\
customer_user_id=user_123&\
platform=ios&\
registration_method=email&\
event_id=reg_custom_001"
```

### Покупка (минимальный запрос)

```bash
curl -X POST "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
appsflyer_id=1658954220-9876543210&\
revenue=19.99&\
currency=USD&\
platform=android"
```

### Покупка (полный запрос)

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
quantity=1&\
platform=android&\
event_id=purchase_custom_002"
```

### Ответ API

```json
{
  "status": "accepted",
  "event_id": "purchase_abc123def456",
  "queued_at": "2026-01-29T12:34:56.789Z",
  "message": "Event queued for processing"
}
```

## Конфигурация

Все параметры настраиваются через переменные окружения (см. `.env.example`):

### Основные

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `APP_ENV` | dev | Окружение (dev/prod) |
| `DEBUG` | false | Режим отладки (включает /docs) |

### Аутентификация

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `AUTH_MODE` | token | Режим аутентификации (token/hmac) |
| `API_TOKENS` | - | Валидные токены (через запятую) |
| `HMAC_KEYS_JSON` | {} | JSON mapping public_id → secret |
| `AUTH_TS_SKEW_SECONDS` | 300 | Допустимый timestamp skew для HMAC |

### Redis

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `REDIS_URL` | redis://localhost:6379/0 | URL Redis |
| `STREAM_MAIN` | events:main | Основной stream |
| `STREAM_DLQ` | events:dlq | Dead letter queue stream |

### Worker

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `WORKER_CONSUMER_GROUP` | af_sender | Consumer group name |
| `MAX_ATTEMPTS` | 8 | Максимум попыток перед DLQ |
| `BACKOFF_BASE_SECONDS` | 1 | Базовая задержка retry |
| `BACKOFF_MAX_SECONDS` | 60 | Максимальная задержка retry |
| `PENDING_CLAIM_MS` | 60000 | Timeout для reclaim pending |

### AppsFlyer

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `APPSFLYER_BASE_URL` | https://api3.appsflyer.com | Base URL API |
| `APPSFLYER_DEV_KEY` | - | Dev key (обязательно) |
| `APPSFLYER_DEFAULT_APP_ID` | - | App ID по умолчанию |
| `APPSFLYER_TIMEOUT_SECONDS` | 5 | Timeout запросов |

### Rate Limiting

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `RATE_LIMIT_ENABLED` | true | Включить rate limiting |
| `RATE_LIMIT_RPS` | 100 | Requests per second |
| `RATE_LIMIT_BURST` | 200 | Burst capacity |

### Логирование

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `LOG_LEVEL` | INFO | Уровень логирования |
| `LOG_FORMAT` | json | Формат логов (json/console) |

## Prometheus Metrics

Доступны на `/metrics`:

### HTTP Metrics
- `http_requests_total{method,path,status}` — общее количество запросов
- `http_request_duration_seconds{method,path}` — latency запросов
- `http_requests_inprogress{method,path}` — текущие in-flight запросы

### Queue Metrics
- `queue_enqueued_total{event_type}` — события добавленные в очередь
- `queue_duplicate_total{event_type}` — обнаруженные дубликаты

### Worker Metrics
- `worker_processed_total{event_type,result}` — обработанные события (success/dlq)
- `worker_retry_total{event_type}` — retry attempts
- `worker_dlq_total{event_type,reason}` — события в DLQ

### AppsFlyer Metrics
- `appsflyer_requests_total{event_type,status_code}` — запросы к AppsFlyer
- `appsflyer_latency_seconds{event_type}` — latency AppsFlyer API

### Rate Limit Metrics
- `rate_limit_blocked_total{identifier_type}` — заблокированные запросы

### Deduplication Metrics
- `dedup_check_total{result}` — результаты проверки дубликатов (new/duplicate)

## Разработка

### Установка зависимостей

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Запуск тестов

```bash
pytest
```

### Запуск линтеров

```bash
ruff check .
mypy app/
```

### Локальный запуск

```bash
# API
uvicorn app.main:app --reload

# Worker
python -m app.worker.run
```

## Структура проекта

```
app/
├── main.py              # FastAPI приложение
├── api/
│   ├── auth.py          # Token/HMAC аутентификация
│   ├── health.py        # Health endpoints
│   ├── rate_limit.py    # Rate limiting
│   ├── routes.py        # Tracking endpoints
│   └── schemas.py       # Pydantic models
├── core/
│   ├── config.py        # Настройки из ENV
│   ├── exceptions.py    # Custom exceptions
│   ├── logging.py       # Structured logging
│   ├── metrics.py       # Prometheus metrics
│   └── models.py        # Internal models
├── queue/
│   ├── consumer.py      # Redis Streams consumer
│   └── producer.py      # Redis Streams producer
├── appsflyer/
│   ├── client.py        # AppsFlyer HTTP client
│   ├── mapper.py        # Event mapping
│   └── models.py        # AppsFlyer models
└── worker/
    └── run.py           # Background worker

tests/                   # Unit и integration тесты
docs/                    # Документация
docker/                  # Dockerfiles
```

## Документация

- [Примеры API запросов](docs/api_examples.md)
- [Архитектурные решения](docs/decisions.md)
- [Использованные источники](docs/references.md)
- [AppsFlyer API](docs/appsflyer_api.md)

## Keitaro Integration

### URL для S2S Postback

**Registration:**
```
http://your-server:8000/v1/track/registration?token=YOUR_TOKEN&appsflyer_id={sub1}&customer_user_id={sub2}&platform=ios&event_id=reg_{click_id}
```

**Purchase:**
```
http://your-server:8000/v1/track/purchase?token=YOUR_TOKEN&appsflyer_id={sub1}&revenue={payout}&currency=USD&platform=android&event_id=purchase_{click_id}
```

### Макросы Keitaro
- `{sub1}` → appsflyer_id
- `{sub2}` → customer_user_id
- `{payout}` → revenue
- `{click_id}` → для event_id (дедупликация)

## License

MIT
