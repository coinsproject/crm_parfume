# REST API Документация для мобильных приложений

## Базовый URL
```
http://localhost:9000/api/v1
```

## Аутентификация

Все запросы (кроме `/auth/login`) требуют Bearer токен в заголовке `Authorization`:
```
Authorization: Bearer <your_access_token>
```

### Получение токена

**POST** `/api/v1/auth/login`

**Request Body:**
```json
{
  "username": "your_username",
  "password": "your_password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": 1,
  "username": "your_username"
}
```

**Примечание:** Если у пользователя включена 2FA, будет возвращена ошибка с требованием пройти двухфакторную аутентификацию.

---

## Клиенты

### Получить список клиентов

**GET** `/api/v1/clients`

**Query Parameters:**
- `q` (optional) - поисковый запрос (имя, телефон, email)
- `page` (optional, default: 1) - номер страницы
- `page_size` (optional, default: 50, max: 100) - количество записей на странице

**Response:**
```json
[
  {
    "id": 1,
    "name": "Иванов Иван",
    "phone": "+7 (999) 123-45-67",
    "email": "ivan@example.com",
    "city": "Москва",
    "notes": "Постоянный клиент",
    "telegram": "@ivanov",
    "instagram": "ivanov_inst",
    "can_access_catalog": true,
    "created_at": "2024-01-15T10:30:00",
    "updated_at": "2024-01-15T10:30:00"
  }
]
```

### Получить клиента по ID

**GET** `/api/v1/clients/{client_id}`

**Response:**
```json
{
  "id": 1,
  "name": "Иванов Иван",
  "phone": "+7 (999) 123-45-67",
  "email": "ivan@example.com",
  "city": "Москва",
  "notes": "Постоянный клиент",
  "telegram": "@ivanov",
  "instagram": "ivanov_inst",
  "can_access_catalog": true,
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00"
}
```

### Создать клиента

**POST** `/api/v1/clients`

**Request Body:**
```json
{
  "name": "Петров Петр",
  "phone": "+7 (999) 123-45-67",
  "email": "petrov@example.com",
  "city": "Санкт-Петербург",
  "notes": "Новый клиент",
  "telegram": "@petrov",
  "instagram": "petrov_inst",
  "can_access_catalog": false
}
```

**Обязательные поля:**
- `name` - имя клиента

**Response:** 201 Created
```json
{
  "id": 2,
  "name": "Петров Петр",
  ...
}
```

### Обновить клиента

**PUT** `/api/v1/clients/{client_id}`

**Request Body:** (все поля опциональны)
```json
{
  "name": "Петров Петр Петрович",
  "phone": "+7 (999) 123-45-68",
  "city": "Москва"
}
```

**Response:**
```json
{
  "id": 2,
  "name": "Петров Петр Петрович",
  ...
}
```

### Удалить клиента

**DELETE** `/api/v1/clients/{client_id}`

**Response:** 204 No Content

---

## Заказы

### Получить список заказов

**GET** `/api/v1/orders`

**Query Parameters:**
- `page` (optional, default: 1) - номер страницы
- `page_size` (optional, default: 50, max: 100) - количество записей на странице
- `status_filter` (optional) - фильтр по статусу (NEW, WAITING_PAYMENT, PAID, PACKING, SHIPPED, DELIVERED, CANCELLED, RETURNED)

**Response:**
```json
[
  {
    "id": 1,
    "client_id": 1,
    "partner_id": null,
    "status": "NEW",
    "total_amount": 10000.00,
    "total_client_amount": 12000.00,
    "payment_method": "SBP",
    "delivery_type": "CDEK",
    "delivery_tracking": "1234567890",
    "created_at": "2024-01-15T10:30:00",
    "updated_at": "2024-01-15T10:30:00",
    "items": [
      {
        "id": 1,
        "fragrance_id": 1,
        "price_product_id": null,
        "catalog_item_id": null,
        "qty": 2,
        "discount": 0.00,
        "client_price": 6000.00,
        "cost_for_owner": 5000.00,
        "line_client_amount": 12000.00,
        "line_cost_amount": 10000.00,
        "line_margin": 2000.00
      }
    ]
  }
]
```

### Получить заказ по ID

**GET** `/api/v1/orders/{order_id}`

**Response:** (аналогично элементу из списка)

### Создать заказ

**POST** `/api/v1/orders`

**Request Body:**
```json
{
  "client_id": 1,
  "partner_id": null,
  "status": "NEW",
  "payment_method": "SBP",
  "delivery_type": "CDEK",
  "delivery_tracking": null,
  "items": [
    {
      "fragrance_id": 1,
      "price_product_id": null,
      "catalog_item_id": null,
      "qty": 2,
      "discount": 0.00
    },
    {
      "fragrance_id": null,
      "price_product_id": 5,
      "catalog_item_id": null,
      "qty": 1,
      "discount": 500.00
    }
  ]
}
```

**Обязательные поля:**
- `client_id` - ID клиента
- `items` - массив позиций заказа

**Для каждой позиции нужно указать один из:**
- `fragrance_id` - ID аромата
- `price_product_id` - ID товара из прайса
- `catalog_item_id` - ID товара из каталога

**Response:** 201 Created
```json
{
  "id": 1,
  "client_id": 1,
  ...
}
```

### Обновить заказ

**PUT** `/api/v1/orders/{order_id}`

**Request Body:** (все поля опциональны)
```json
{
  "status": "PAID",
  "payment_method": "Карта",
  "delivery_tracking": "1234567890"
}
```

**Response:**
```json
{
  "id": 1,
  "status": "PAID",
  ...
}
```

---

## Поиск в прайсе

### Поиск товаров в прайсе

**GET** `/api/v1/price/search`

**Query Parameters:**
- `q` (optional) - поисковый запрос
- `page` (optional, default: 1) - номер страницы
- `page_size` (optional, default: 20, max: 20) - количество записей на странице
- `client_id` (optional) - ID клиента (для расчета цены с накрутками)
- `partner_id` (optional) - ID партнера (для расчета цены с накрутками)

**Response:**
```json
[
  {
    "id": 1,
    "external_article": "ART-001",
    "raw_name": "Chanel No 5",
    "brand": "Chanel",
    "product_name": "No 5",
    "base_price": 5000.00,
    "client_price": 6000.00,
    "cost": 4000.00
  }
]
```

---

## Информация о пользователе

### Получить информацию о текущем пользователе

**GET** `/api/v1/me`

**Response:**
```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "partner_id": null,
  "permissions": [
    "clients.view_all",
    "clients.create",
    "orders.view_all",
    "orders.create",
    ...
  ],
  "is_admin": true
}
```

---

## Коды ответов

- `200 OK` - успешный запрос
- `201 Created` - ресурс успешно создан
- `204 No Content` - успешное удаление
- `400 Bad Request` - неверный запрос (валидация данных)
- `401 Unauthorized` - требуется аутентификация
- `403 Forbidden` - недостаточно прав
- `404 Not Found` - ресурс не найден
- `429 Too Many Requests` - превышен лимит запросов

---

## Примеры использования

### JavaScript (Fetch API)

```javascript
// Логин
const loginResponse = await fetch('http://localhost:9000/api/v1/auth/login', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    username: 'your_username',
    password: 'your_password'
  })
});

const { access_token } = await loginResponse.json();

// Получить список клиентов
const clientsResponse = await fetch('http://localhost:9000/api/v1/clients?page=1&page_size=20', {
  headers: {
    'Authorization': `Bearer ${access_token}`
  }
});

const clients = await clientsResponse.json();

// Создать клиента
const newClient = await fetch('http://localhost:9000/api/v1/clients', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${access_token}`
  },
  body: JSON.stringify({
    name: 'Новый клиент',
    phone: '+7 (999) 123-45-67',
    city: 'Москва'
  })
});
```

### Python (requests)

```python
import requests

BASE_URL = "http://localhost:9000/api/v1"

# Логин
response = requests.post(f"{BASE_URL}/auth/login", json={
    "username": "your_username",
    "password": "your_password"
})
token = response.json()["access_token"]

# Получить список клиентов
headers = {"Authorization": f"Bearer {token}"}
clients = requests.get(f"{BASE_URL}/clients", headers=headers).json()

# Создать клиента
new_client = requests.post(
    f"{BASE_URL}/clients",
    headers=headers,
    json={
        "name": "Новый клиент",
        "phone": "+7 (999) 123-45-67",
        "city": "Москва"
    }
).json()
```

### cURL

```bash
# Логин
curl -X POST http://localhost:9000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"your_username","password":"your_password"}'

# Получить список клиентов
curl -X GET http://localhost:9000/api/v1/clients \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# Создать клиента
curl -X POST http://localhost:9000/api/v1/clients \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Новый клиент","phone":"+7 (999) 123-45-67","city":"Москва"}'
```

---

## Примечания

1. Все даты и время возвращаются в формате ISO 8601 (UTC)
2. Все денежные суммы возвращаются в формате Decimal (строки с точкой)
3. Права доступа проверяются на каждом запросе
4. Пользователи с правами `view_own` видят только свои ресурсы
5. Пользователи с правами `view_all` видят все ресурсы
6. Токен действителен в течение времени, указанного в настройках (по умолчанию 30 минут)







