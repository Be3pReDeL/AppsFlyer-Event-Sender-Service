# production.md — Техническое задание (Production)
## Сервис S2S отправки событий в AppsFlyer (FastAPI + Docker + очередь)

> **Назначение документа**: это единое production-ready ТЗ для разработки веб‑сервиса, который принимает S2S postback’и (Keitaro) и надёжно отправляет события в AppsFlyer по API, используя очередь и воркеры.

---

## 1) Цель и назначение

Разработать веб‑сервис на **Python** с использованием **FastAPI**, **Docker‑контейнеризации** и **очередей**, который:

- предоставляет **публичные endpoint’ы** для трекинга событий **Registration** и **Purchase**;
- предназначен для использования как **S2S Postback endpoint** в **Keitaro**;
- принимает входящие запросы, валидирует/нормализует данные и **асинхронно** отправляет события в **AppsFlyer** по актуальной спецификации API;
- обеспечивает **production‑уровень** по устойчивости, производительности, безопасности и наблюдаемости.

**Ограничение:** Keitaro не имеет возможности добавлять заголовки (headers) к запросам → авторизация должна работать без headers (через query‑параметры либо альтернативу, описанную ниже).

---

## 2) Результат работ

В репозитории должен быть готовый к деплою проект, включающий:

- FastAPI сервис (HTTP API)
- очередь + воркеры для отправки в AppsFlyer
- конфигурацию через ENV
- Dockerfile(ы), docker-compose
- healthchecks, метрики, структурные логи
- тесты (unit + минимум интеграционный “end‑to‑end” через очередь с mock AppsFlyer)
- документацию и файлы решений/референсов (см. раздел 18)

---

## 3) Основные требования (functional)

### 3.1. Входные события
Сервис должен принимать и обрабатывать два типа событий:

1) **registration** — регистрация
2) **purchase** — покупка

### 3.2. Внешние публичные endpoint’ы
Endpoint’ы будут использоваться Keitaro как S2S postback URL.

Требования:
- Поддержать **GET (обязательно)** с query‑параметрами
- Поддержать **POST (опционально)** с JSON‑body (для расширяемости/будущих интеграций)

### 3.3. Нормализация данных
Сервис должен преобразовывать входные данные в внутреннюю модель `InternalEvent`, а затем в запрос AppsFlyer (`AppsFlyerRequest`) через отдельный слой маппинга (см. раздел 5.4).

**Важно:** конкретные поля, требуемые AppsFlyer, должны строго соответствовать актуальной документации (получаемой через MCP Context7, см. раздел 18–19).

---

## 4) Нефункциональные требования (production)

### 4.1. Производительность
- Быстрый ответ API: при доступном Redis — p95 **≤ 50–100 ms** на “принять и поставить в очередь”.
- Выдерживать **высокую параллельность** (пакеты одновременных запросов), не терять задачи, не деградировать до падений.

### 4.2. Надёжность/устойчивость
- Очередь между API и AppsFlyer: API не зависит от latency/ошибок AppsFlyer.
- Ретраи с backoff + jitter.
- DLQ (dead-letter queue).
- Автоперезапуск контейнеров.
- Перехват и корректная обработка исключений.

### 4.3. Безопасность
- Авторизация без headers (query token / HMAC).
- Не логировать секреты и PII.
- Rate limiting.
- Опционально: IP allowlist.

### 4.4. Наблюдаемость
- Структурные JSON‑логи.
- Метрики Prometheus `/metrics`.
- Health endpoints: liveness/readiness.

---

## 5) Архитектура и компоненты

### 5.1. Высокоуровневая схема
**API (FastAPI)** → **Redis Streams (очередь)** → **Worker(ы)** → **AppsFlyer API**

Компоненты:

1) **API Service**
- принимает запросы Keitaro
- авторизует
- валидирует
- формирует `InternalEvent`
- ставит задачу в очередь
- отвечает 202/200

2) **Redis**
- Stream `events:main` — основная очередь
- Stream `events:dlq` — dead letter
- ключи дедупликации `dedup:<event_id>` с TTL
- rate limit buckets (если Redis‑based)

3) **Worker Service**
- читает Stream через Consumer Group
- отправляет запрос в AppsFlyer
- обрабатывает ответы/ошибки
- retry/backoff
- переносит в DLQ при исчерпании попыток

### 5.2. Почему Redis Streams
- достаточно надёжен и прост для небольшого проекта
- consumer groups, pending entries, переобработка “зависших” задач
- не требует сложного деплоя (в отличие от Kafka)

### 5.3. Модель данных (внутренняя)
`InternalEvent` (минимально):
- `event_type`: registration|purchase
- `event_id`: string (uuid/hash)
- `received_at`: datetime (UTC)
- `payload`: dict (нормализованные поля)
- `attempt`: int
- `source_meta`: dict (ip, user-agent, raw params hash и т.д., без секретов)

### 5.4. Слой маппинга (обязательно)
Строго разделить:
- `InboundKeitaroRequest -> InternalEvent`
- `InternalEvent -> AppsFlyerRequest`

Цель: изолировать изменения входного/выходного контрактов от внутренней логики очереди/воркера.

---

## 6) Авторизация (учёт Keitaro без headers)

### 6.1. Базовый режим (обязателен)
- query‑параметр: `token=<shared_secret>`
- список активных токенов поддерживается для ротации (`API_TOKENS=...`)

Поведение:
- отсутствует/неверный token → `401 Unauthorized`
- token верный → продолжить обработку

**Требование:** token **никогда** не выводится в логах/метриках.

### 6.2. Усиленный режим (рекомендуется, если Keitaro позволяет собрать параметры)
Чтобы уменьшить риск утечки “вечного” токена:
- `key=<public_id>`
- `ts=<unix_seconds>`
- `sig=<HMAC_SHA256(secret_for_key, canonical_query + ts)>`

Правила:
- допускаемая “дрейф‑вилка” времени: ±300 секунд (конфиг)
- защита от replay: хранить `sig`/`nonce` в Redis с TTL
- неверная подпись/время → 401

---

## 7) Внешний API сервиса (контракт)

### 7.1. Версионирование
- префикс: `/v1`

### 7.2. Endpoint’ы
1) Registration:
- `GET  /v1/track/registration?token=...&...`
- `POST /v1/track/registration?token=...` (JSON body)

2) Purchase:
- `GET  /v1/track/purchase?token=...&...`
- `POST /v1/track/purchase?token=...` (JSON body)

### 7.3. Входные параметры
- формат входных параметров должен учитывать Keitaro postback (query‑based)
- обязательные поля определяются спецификацией AppsFlyer и маппингом

Минимальная функциональная поддержка:
- идентификатор пользователя/устройства в требуемом AppsFlyer формате
- event time (если требуется) или server time
- revenue/currency для purchase (если требуется)
- возможность пробросить дополнительные поля AppsFlyer (как passthrough)

### 7.4. Ответы API
- `202 Accepted` — событие принято и поставлено в очередь
- `200 OK` — допустимо для дубликата (по решению реализации), но предпочтительно 202
- `400 Bad Request` — невалидные параметры
- `401 Unauthorized` — auth failed
- `429 Too Many Requests` — rate limit
- `503 Service Unavailable` — Redis/внутренняя инфраструктура недоступна
- `500 Internal Server Error` — непредвиденная ошибка (минимизировать)

**JSON ответ (пример):**
```json
{
  "status": "accepted",
  "event_id": "uuid-or-hash",
  "queued_at": "2026-01-29T12:34:56Z"
}
```

---

## 8) Очередь, ретраи, DLQ, идемпотентность

### 8.1. Поставка в очередь
- API кладёт событие в `events:main`
- API не делает прямой вызов AppsFlyer

### 8.2. Retry policy (обязательно)
Ретрай при:
- сетевых ошибках (timeout, DNS, reset)
- 5xx от AppsFlyer
- 429 от AppsFlyer (учитывать `Retry-After`, если есть)

Backoff:
- экспоненциальный + jitter
- `1s, 2s, 4s, 8s, ...` до `BACKOFF_MAX_SECONDS`
- `MAX_ATTEMPTS` по конфигу (например 8)

Timeouts:
- `APPSFLYER_TIMEOUT_SECONDS` (connect/read) — конфиг, по умолчанию 3–5s

### 8.3. DLQ (dead letter)
- по исчерпанию попыток событие переносится в `events:dlq`
- сохранять причину/последний код/последнюю ошибку
- инкрементировать метрику `worker_dlq_total`

### 8.4. Идемпотентность / дедупликация
Цель: не отправлять одно и то же событие повторно, если Keitaro дублирует postback.

- ключ дедупликации: `dedup:<event_id>` с TTL (например 7 дней)
- если дедуп‑ключ уже существует:
  - не ставить в очередь повторно (или ставить с меткой duplicate — по решению)
  - возвращать 202/200 с указанием event_id

Генерация `event_id`:
- если Keitaro предоставляет уникальный id — использовать
- иначе — генерировать стабильный hash (canonical params + event_type + time bucket)

### 8.5. Pending/reclaim
Worker должен уметь переобрабатывать “зависшие” сообщения:
- Consumer Group + проверка pending
- reclaim сообщений старше `PENDING_CLAIM_MS` (конфиг)

---

## 9) Интеграция с AppsFlyer

### 9.1. Источник истины
**Спецификация AppsFlyer API** берётся из актуальной документации через MCP Context7 (см. раздел 18–19).  
Сервис обязан соответствовать реальной схеме параметров, endpoint’ов, ошибкам и ограничениям.

### 9.2. Требования к реализации клиента
- HTTP client: `httpx` (async)
- строгие таймауты
- ограничение конкурентности (если нужно, через semaphore)
- логирование результата без PII и без секретов

### 9.3. Классификация ответов AppsFlyer
- 2xx → успех, ack задачи
- 429 → retry (учесть `Retry-After`)
- 5xx → retry
- 4xx (кроме 429) → обычно “неисправимо” → DLQ (или политика по документам)

---

## 10) Наблюдаемость (Observability)

### 10.1. Логи
- JSON‑логи
- поля: `timestamp`, `level`, `service`, `request_id`, `event_id`, `event_type`, `status`, `latency_ms`
- токены/подписи/PII маскировать

### 10.2. Метрики (Prometheus)
Endpoint: `GET /metrics`

Минимум:
- `http_requests_total{path,method,status}`
- `http_request_duration_seconds` (histogram)
- `queue_enqueued_total{event_type}`
- `worker_processed_total{event_type,result}`
- `worker_retry_total{event_type}`
- `worker_dlq_total{event_type,reason}`
- `appsflyer_latency_seconds` (histogram)

### 10.3. Health endpoints
- `GET /health/live` — процесс жив
- `GET /health/ready` — Redis доступен (опционально: базовая проверка конфигурации AppsFlyer)

---

## 11) Безопасность

Обязательные меры:
- авторизация (token или HMAC)
- rate limiting (per token/key и/или per IP)
- ограничение размера запроса
- строгая валидация входных данных (Pydantic)
- запрет логирования секретов/PII
- TLS обеспечивается на уровне reverse proxy (nginx/traefik) или окружения

Опционально:
- allowlist IP (если известны IP Keitaro)
- WAF/Fail2ban на уровне инфраструктуры

---

## 12) Масштабирование и запуск

### 12.1. API
- запуск: `gunicorn` + `uvicorn.workers.UvicornWorker`
- число воркеров — конфигом/по CPU

### 12.2. Worker
- отдельный контейнер
- горизонтальное масштабирование количеством реплик

### 12.3. Redis
- отдельный сервис в docker-compose
- в production допустим managed Redis

---

## 13) Рекомендуемый стек
- Python 3.11+
- FastAPI, Pydantic v2
- httpx (async)
- redis-py (async) + Redis Streams
- prometheus-client / instrumentator
- pytest + pytest-asyncio + respx (mock httpx)
- ruff + mypy (рекомендуется)

---

## 14) Рекомендуемая структура проекта
```
app/
  main.py
  api/
    routes.py
    schemas.py
    auth.py
    rate_limit.py
  core/
    config.py
    logging.py
    utils.py
  queue/
    redis_streams.py
    producer.py
    consumer.py
  appsflyer/
    client.py
    mapper.py
    models.py
  worker/
    run.py
tests/
docs/
  references.md
  decisions.md
  appsflyer_api.md
docker/
  Dockerfile.api
  Dockerfile.worker
docker-compose.yml
.env.example
README.md
```

---

## 15) Конфигурация (ENV)
Минимум:
- `APP_ENV=prod|dev`
- `AUTH_MODE=token|hmac`
- `API_TOKENS=token1,token2` *(для token режима)*
- `HMAC_KEYS_JSON=...` *(для hmac режима: public_id → secret)*
- `AUTH_TS_SKEW_SECONDS=300`

Инфраструктура:
- `REDIS_URL=redis://redis:6379/0`
- `STREAM_MAIN=events:main`
- `STREAM_DLQ=events:dlq`
- `WORKER_CONSUMER_GROUP=af_sender`
- `WORKER_CONSUMER_NAME=...` *(можно генерировать)*
- `WORKER_CONCURRENCY=...`
- `MAX_ATTEMPTS=8`
- `BACKOFF_BASE_SECONDS=1`
- `BACKOFF_MAX_SECONDS=60`
- `PENDING_CLAIM_MS=60000`

AppsFlyer:
- `APPSFLYER_BASE_URL=...`
- `APPSFLYER_TIMEOUT_SECONDS=5`
- дополнительные ключи/параметры по спецификации

Rate limiting:
- `RATE_LIMIT_RPS=...`
- `RATE_LIMIT_BURST=...`

---

## 16) Деплой (Docker / docker-compose)

### 16.1. Сервисы
- `api` — FastAPI
- `worker` — отправка в AppsFlyer
- `redis` — очередь/дедуп/rate limit
- *(опционально)* `nginx`/`traefik` — TLS + reverse proxy

### 16.2. Требования
- `restart: always` (или эквивалент)
- healthchecks
- наружу открыт только API (через proxy)

---

## 17) Критерии приёмки (Definition of Done)

1. `docker compose up -d` поднимает сервисы без ручных шагов.
2. `GET /health/ready` возвращает OK при доступном Redis.
3. `GET /v1/track/registration` и `/v1/track/purchase`:
   - без авторизации → 401
   - с валидной авторизацией и параметрами → 202 + `event_id`
4. При недоступности AppsFlyer события не теряются: ретраятся по политике.
5. После исчерпания ретраев событие попадает в DLQ.
6. Дедуп работает: повторный identical postback не приводит к повторной отправке.
7. `/metrics` отдаёт метрики, логи структурированы и не содержат токенов/подписей.
8. Базовый нагрузочный smoke‑тест подтверждает стабильность (нет падений, приемлемая latency на приём).

---

## 18) Процесс разработки в Cursor IDE (AI‑агент) + MCP Context7

### 18.1. Общие принципы
- Разработка ведётся в Cursor IDE с AI‑агентом как исполнителем задач по этому ТЗ.
- Для внешних интеграций/библиотек (AppsFlyer API, Redis Streams и пр.) агент обязан получать актуальные сведения через **MCP Context7**.
- Любые неопределённости → сначала запрос в Context7, потом реализация.

### 18.2. Правила использования Context7 (обязательные)
Агент обязан:
- получать документацию через Context7 для:
  - AppsFlyer API (endpoint’ы, обязательные поля, форматы, ошибки, rate limit, retry рекомендации)
  - Redis Streams / Consumer Groups (ack/pending/claim)
  - FastAPI/httpx/redis‑py/prometheus и прочих используемых библиотек
- фиксировать в `docs/references.md`:
  - источник/идентификатор/метаданные (если доступны)
  - дату обращения
- при неоднозначностях — фиксировать решение в `docs/decisions.md`

### 18.3. Обязательные артефакты репозитория
- `README.md` — запуск, ENV, примеры запросов, troubleshooting
- `docs/references.md` — перечень доков (Context7)
- `docs/decisions.md` — архитектурные решения и причины
- `docs/appsflyer_api.md` — конкретика AppsFlyer (поля/примеры) по актуальной документации
- `.env.example` — без секретов
- Dockerfile(ы), docker-compose, healthchecks

### 18.4. Этапы выполнения (итеративно)
Каждый этап заканчивается проверками и коммитом:

1) Bootstrap (каркас, Docker, health)
2) Endpoint’ы + auth + валидация + маскирование секретов
3) Очередь Redis Streams + базовый worker
4) AppsFlyer client + mapper по докам Context7
5) Надёжность (retry/backoff/DLQ/dedup/pending reclaim)
6) Observability + hardening + финальная документация и тесты

### 18.5. Quality gates
На каждом этапе:
- `pytest`
- `ruff`/`flake8` + `mypy` (рекомендуется)
- smoke запуск через docker compose
- проверка, что секреты не логируются

### 18.6. Git‑правила
- репозиторий создаётся на старте
- коммиты по этапам, Conventional Commits:
  - `feat(api): add registration endpoint with token auth`
  - `feat(queue): add redis streams producer and consumer group`
  - `feat(appsflyer): implement purchase event mapping`
  - `fix(worker): handle 429 with retry-after`
  - `chore(docs): add references and decisions`

---

## 19) Спецификация AppsFlyer как “Source of Truth” (через Context7)

1. Агент получает актуальную схему AppsFlyer API через Context7.
2. Формирует `docs/appsflyer_api.md`:
   - таблица параметров для registration/purchase
   - примеры запросов/ответов
   - правила обработки ошибок и лимитов
3. Любые обновления спецификации → отдельный коммит + обновление mapper и тестов.

---

## 20) Дополнительные замечания
- Проект должен оставаться небольшим и простым в деплое: предпочтительно Redis Streams вместо тяжёлых брокеров.
- Код должен быть защищённым, модульным и производительным.
- Все параметры, влияющие на поведение (timeouts, retries, auth mode), должны быть конфигурируемыми через ENV.
