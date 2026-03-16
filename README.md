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

### Локальная разработка

```bash
# 1. Настройка окружения
cp .env.example .env
# Отредактируйте .env:
# - API_TOKENS: ваши токены для аутентификации
# - APPSFLYER_DEV_KEY: дефолтный ключ разработчика AppsFlyer (fallback, можно переопределить query-параметром dev_key)
# - APPSFLYER_DEFAULT_APP_ID: ID приложения (id123... для iOS, com.app.name для Android)

# 2. Запуск через Docker Compose
docker compose up -d

# 3. Проверка работоспособности
curl http://localhost:8000/health/ready
```

### Production деплой на DigitalOcean

```bash
# 1. Настройка сервера (запустить на сервере)
bash scripts/deploy-setup.sh

# 2. Клонировать репозиторий
git clone git@github.com:USER/REPO.git /opt/apps/AppsFlyer-Event-Sender-Service
cd /opt/apps/AppsFlyer-Event-Sender-Service

# 3. Настроить production конфигурацию
cp deploy/env-examples/production.env .env
nano .env  # Заполнить реальные credentials

# 4. Проверка готовности
bash scripts/preflight-check.sh

# 5. Автоматический деплой
bash scripts/auto-deploy.sh production
```

**Подробнее:** [Deployment Documentation](docs/deployment_digitalocean.md)

### Production деплой на Render (из GitHub)

1. Убедитесь, что в репозитории есть `render.yaml`.
2. Запушьте изменения в GitHub.
3. Откройте Blueprint:
   `https://dashboard.render.com/blueprint/new?repo=<HTTPS_URL_ВАШЕГО_РЕПОЗИТОРИЯ>`
4. Заполните секреты (`API_TOKENS`, `ADMIN_TOKENS`, `APPSFLYER_DEFAULT_APP_ID`, опционально `APPSFLYER_DEV_KEY`) и нажмите `Apply`.
5. Blueprint сам создаст Postgres для `app_id -> dev_key` mapping и подключит его к `api` и `worker`.

**Подробнее:** [Deployment Guide для Render](docs/deployment_render.md)

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
| `/v1/track/registration/proxy` | POST | Прокси для регистрации (token auth, без HMAC) |
| `/v1/track/purchase/proxy` | POST | Прокси для покупки (token auth, без HMAC) |

### Admin

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/v1/admin/dev-keys` | POST | Защищённый upsert `app_id -> dev_key` (header `X-Admin-Token`) |

> **Note**: POST endpoints используют query-параметры (совместимость с Keitaro).
> Приоритет выбора `dev_key` при отправке в AppsFlyer:
> 1) `dev_key` из query конкретного события
> 2) `dev_key` из БД по `app_id` (через `/v1/admin/dev-keys`)
> 3) `APPSFLYER_DEV_KEY` из env (fallback)

### Admin Endpoint Example

```bash
curl -X POST "http://localhost:8000/v1/admin/dev-keys" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN" \
  -d '{
    "app_id": "id6758761140",
    "dev_key": "YOUR_APPSFLYER_DEV_KEY_FOR_APP"
  }'
```

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
dev_key=YOUR_DEV_KEY_OVERRIDE&\
appsflyer_id=1658954220-1234567890&\
customer_user_id=user_123&\
platform=ios&\
registration_method=email&\
event_id=reg_custom_001"
```

### Регистрация (Keitaro без HMAC через proxy)

```bash
curl -X POST "http://localhost:8000/v1/track/registration/proxy?\
token=YOUR_TOKEN&\
appsflyer_id=1658954220-1234567890&\
platform=ios"
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
dev_key=YOUR_DEV_KEY_OVERRIDE&\
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

### Покупка (Keitaro без HMAC через proxy)

```bash
curl -X POST "http://localhost:8000/v1/track/purchase/proxy?\
token=YOUR_TOKEN&\
appsflyer_id=1658954220-9876543210&\
revenue=19.99&\
currency=USD&\
platform=android"
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
| `ADMIN_TOKENS` | - | Admin токены для `/v1/admin/*` |
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
| `APPSFLYER_DEV_KEY` | - | Dev key по умолчанию (fallback, можно переопределить `dev_key` в query) |
| `APPSFLYER_DEFAULT_APP_ID` | - | App ID по умолчанию |
| `APPSFLYER_TIMEOUT_SECONDS` | 5 | Timeout запросов |
| `APPSFLYER_DEV_KEY_DATABASE_URL` | - | Shared Postgres URL для mapping `app_id -> dev_key` |
| `APPSFLYER_DEV_KEY_DB_PATH` | /data/appsflyer_dev_keys.db | Fallback SQLite path для single-host deploy |

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

### Деплой

- [Полное руководство по деплою на DigitalOcean](docs/deployment_digitalocean.md)
- [Полное руководство по деплою на Render из GitHub](docs/deployment_render.md)
- [Быстрый старт деплоя](docs/deployment_quickstart.md)
- [Шаблон Nginx конфигурации](deploy/nginx.conf.template)
- [systemd unit файл](deploy/appsflyer-service.service)

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
