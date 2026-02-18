# Деплой на Render из GitHub

Этот проект можно развернуть в Render через Blueprint (`render.yaml`) из GitHub-репозитория.

## Что создаётся в Render

- `appsflyer-api` (`type: web`) — публичный FastAPI сервис.
- `appsflyer-worker` (`type: worker`) — фоновый обработчик очереди.
- `appsflyer-redis` (`type: redis`) — внутреннее key-value хранилище для Streams/dedup/rate limit.

Текущая конфигурация планов:
- `appsflyer-api`: `free`
- `appsflyer-redis`: `free`
- `appsflyer-worker`: `starter` (на free worker недоступен в Render)
- Python version: `3.11` (зафиксирован через `.python-version`)

## Предварительные требования

- Код запушен в GitHub репозиторий.
- В корне репозитория есть `render.yaml`.
- Подготовлены секреты:
  - `API_TOKENS`
  - `APPSFLYER_DEV_KEY`
  - `APPSFLYER_DEFAULT_APP_ID`

## Шаги деплоя

1. Убедитесь, что `render.yaml` закоммичен и отправлен в GitHub:

```bash
git add render.yaml docs/deployment_render.md README.md
git commit -m "Add Render Blueprint deployment"
git push
```

2. Откройте Blueprint в Render Dashboard:

```text
https://dashboard.render.com/blueprint/new?repo=<HTTPS_URL_ВАШЕГО_РЕПОЗИТОРИЯ>
```

Пример для текущего репозитория:

```text
https://dashboard.render.com/blueprint/new?repo=https://github.com/Be3pReDeL/AppsFlyer-Event-Sender-Service
```

3. Нажмите `Apply` и заполните секретные переменные (`sync: false`):
   - `API_TOKENS`
   - `APPSFLYER_DEV_KEY`
   - `APPSFLYER_DEFAULT_APP_ID`

4. Дождитесь статуса `Live` у `appsflyer-api` и `appsflyer-worker`.

## Проверка после деплоя

- Liveness:

```bash
curl https://<your-api>.onrender.com/health/live
```

- Readiness (должен видеть Redis):

```bash
curl https://<your-api>.onrender.com/health/ready
```

- Тестовый event:

```bash
curl -X POST "https://<your-api>.onrender.com/v1/track/registration?token=<TOKEN>&appsflyer_id=test-af-id&platform=ios"
```

## Важные замечания

- `REDIS_URL` для API/worker подставляется автоматически через `fromService`.
- В Render free-инстансы не поддерживают `worker`, поэтому для фонового обработчика используется `starter`.
- Если изменяете контракт переменных окружения, обновляйте одновременно `.env.example` и `render.yaml`.
