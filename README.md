# AppsFlyer Event Sender Service

Веб-сервис для приёма S2S postback от Keitaro и отправки событий в AppsFlyer.

## Архитектура

```
Keitaro → API (FastAPI) → Redis Streams → Worker → AppsFlyer API
```

**Компоненты:**
- **API** — принимает HTTP-запросы, валидирует, ставит в очередь
- **Worker** — обрабатывает события из очереди, отправляет в AppsFlyer
- **Redis** — очередь (Streams), дедупликация, rate limiting

## Быстрый старт

### 1. Настройка окружения

```bash
cp .env.example .env
# Отредактируйте .env, установите API_TOKENS и APPSFLYER_DEV_KEY
```

### 2. Запуск через Docker Compose

```bash
docker compose up -d
```

### 3. Проверка работоспособности

```bash
# Liveness probe
curl http://localhost:8000/health/live

# Readiness probe
curl http://localhost:8000/health/ready
```

## API Endpoints

### Health Checks

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/health/live` | GET | Liveness probe |
| `/health/ready` | GET | Readiness probe (проверяет Redis) |

### Tracking (в разработке)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/v1/track/registration` | GET/POST | Событие регистрации |
| `/v1/track/purchase` | GET/POST | Событие покупки |

## Конфигурация

Все параметры настраиваются через переменные окружения (см. `.env.example`):

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `APP_ENV` | dev | Окружение (dev/prod) |
| `AUTH_MODE` | token | Режим аутентификации (token/hmac) |
| `API_TOKENS` | - | Валидные токены (через запятую) |
| `REDIS_URL` | redis://localhost:6379/0 | URL Redis |
| `LOG_LEVEL` | INFO | Уровень логирования |
| `LOG_FORMAT` | json | Формат логов (json/console) |

## Разработка

### Установка зависимостей

```bash
python -m venv .venv
source .venv/bin/activate
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

### Локальный запуск API

```bash
uvicorn app.main:app --reload
```

## Структура проекта

```
app/
├── main.py           # FastAPI приложение
├── api/              # HTTP endpoints
├── core/             # Конфигурация, логирование
├── queue/            # Redis Streams
├── appsflyer/        # Клиент AppsFlyer
└── worker/           # Фоновая обработка
tests/
docs/
docker/
```

## Документация

- [Архитектурные решения](docs/decisions.md)
- [Использованные источники](docs/references.md)
- [AppsFlyer API](docs/appsflyer_api.md)

## License

MIT
