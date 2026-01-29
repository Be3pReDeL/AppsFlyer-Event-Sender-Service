# Примеры запросов для Keitaro

Готовые примеры POST запросов для настройки в Keitaro S2S Postback.

## ⚠️ Важно

- **Метод**: POST (рекомендуется) или GET
- **Данные**: передаются через query-параметры (не body)
- **Авторизация**: параметр `token=YOUR_TOKEN`

## Настройка переменных

Перед использованием установите в `.env`:
```bash
API_TOKENS=ваш-секретный-токен-здесь
APPSFLYER_DEV_KEY=ваш-appsflyer-dev-key
APPSFLYER_DEFAULT_APP_ID=id123456789  # для iOS: idXXX, для Android: com.app.name
```

---

## 📱 Регистрация (Registration)

### Вариант 1: Минимальный (POST)

**URL для Keitaro:**
```
http://your-server:8000/v1/track/registration?token=YOUR_TOKEN&appsflyer_id={sub1}&platform=ios
```

**Макросы Keitaro:**
- `{sub1}` — AppsFlyer device ID
- `{sub2}` — Customer user ID (опционально)

### Вариант 2: Полный (POST)

**URL для Keitaro:**
```
http://your-server:8000/v1/track/registration?token=YOUR_TOKEN&app_id=id123456789&appsflyer_id={sub1}&customer_user_id={sub2}&platform=ios&registration_method=email&event_id=reg_{click_id}
```

**Макросы:**
- `{sub1}` → appsflyer_id
- `{sub2}` → customer_user_id
- `{click_id}` → уникальный ID клика (для event_id)

### Тестовый запрос (curl)

```bash
curl -X POST "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
appsflyer_id=1658954220-1234567890&\
customer_user_id=user_12345&\
platform=ios&\
registration_method=email"
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

## 💰 Покупка (Purchase)

### Вариант 1: Минимальный (POST)

**URL для Keitaro:**
```
http://your-server:8000/v1/track/purchase?token=YOUR_TOKEN&appsflyer_id={sub1}&revenue={payout}&currency=USD&platform=android
```

**Макросы Keitaro:**
- `{sub1}` — AppsFlyer device ID
- `{payout}` — сумма покупки
- `{currency}` — валюта (если доступна)

### Вариант 2: Полный (POST)

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

### Тестовый запрос (curl)

```bash
curl -X POST "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
appsflyer_id=1658954220-9876543210&\
customer_user_id=user_67890&\
revenue=29.99&\
currency=EUR&\
product_id=premium_monthly&\
order_id=order_xyz789&\
platform=android"
```

**Ответ:**
```json
{
  "status": "accepted",
  "event_id": "purchase_1a2b3c4d5e6f",
  "queued_at": "2026-01-29T15:35:12.456Z",
  "message": "Event queued for processing"
}
```

---

## 🔄 Мультиприложения (iOS + Android)

### iOS приложение

```bash
curl -X POST "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
app_id=id123456789&\
appsflyer_id={sub1}&\
revenue={payout}&\
currency=USD&\
platform=ios"
```

### Android приложение

```bash
curl -X POST "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
app_id=com.example.androidapp&\
appsflyer_id={sub1}&\
revenue={payout}&\
currency=USD&\
platform=android"
```

---

## ✅ Рекомендации для Keitaro

1. **Используйте POST** — семантически корректнее для side effects
2. **Передавайте app_id** — если работаете с несколькими приложениями
3. **Используйте event_id** — для отслеживания и дедупликации (например `{click_id}`)
4. **Маппинг макросов**:
   - `{sub1}` → `appsflyer_id` (обязательно)
   - `{sub2}` → `customer_user_id` (опционально)
   - `{payout}` → `revenue` (для purchase)
   - `{offer_id}` → `product_id` (опционально)
   - `{click_id}` → `event_id` (рекомендуется)

## 🔍 Проверка статуса

После настройки в Keitaro проверьте логи сервиса:

```bash
# Логи API
docker compose logs -f api

# Логи Worker
docker compose logs -f worker
```

Успешная обработка покажет:
```
event_enqueued → processing_event → appsflyer_send_success → event_processed
```

## ❌ Возможные ошибки

| Ошибка | Код | Причина |
|--------|-----|---------|
| Missing token parameter | 401 | Не передан `token` |
| Invalid token | 401 | Неверный токен |
| Missing required fields | 400 | Для purchase: отсутствует `revenue` или `currency` |
| Service temporarily unavailable | 503 | Redis недоступен |

## 💡 Совет

Для отладки используйте DEBUG режим:
```bash
# .env
LOG_LEVEL=DEBUG
LOG_FORMAT=console
```

Это покажет детали обработки каждого события.
