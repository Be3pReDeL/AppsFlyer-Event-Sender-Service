# AppsFlyer API Documentation

Документация по интеграции с AppsFlyer S2S API.

> **Note**: Эта документация будет дополнена актуальными данными из Context7 на этапе интеграции с AppsFlyer.

## Endpoint

```
POST https://api2.appsflyer.com/inappevent/{app_id}
```

## Обязательные параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| appsflyer_id | string | Уникальный ID устройства AppsFlyer |
| eventName | string | Название события (регистрация/покупка) |
| eventValue | object | JSON с данными события |

## Аутентификация

- Header: `authentication: <dev_key>`

## События

### Registration
- `eventName`: af_complete_registration
- `eventValue`: данные о регистрации

### Purchase
- `eventName`: af_purchase
- `eventValue`: revenue, currency, product_id и т.д.

## Коды ответов

| Код | Описание | Действие |
|-----|----------|----------|
| 200 | Успех | Ack |
| 400 | Неверные параметры | DLQ |
| 401 | Неверная авторизация | DLQ |
| 429 | Rate limit | Retry с Retry-After |
| 5xx | Ошибка сервера | Retry |

---

*Актуальная спецификация будет получена через Context7 MCP.*
