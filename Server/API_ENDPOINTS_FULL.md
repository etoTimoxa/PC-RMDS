# PC-RMDS API Server - Полная документация эндпоинтов с телом запросов

---

## 🔐 Авторизация

### ✅ POST `/api/auth/login`
```json
// Тело запроса
{
  "login": "admin",
  "password": "admin123"
}

// Ответ
{
  "success": true,
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user": {
      "user_id": 4,
      "login": "admin",
      "full_name": "Администратор Системы",
      "role_id": 2,
      "is_admin": true
    }
  }
}
```

---

### ✅ POST `/api/auth/register`
```json
// Тело запроса
{
  "login": "newuser",
  "password": "password123",
  "full_name": "Новый Пользователь"
}

// Ответ
{
  "success": true,
  "message": "Пользователь успешно зарегистрирован",
  "data": {
    "user_id": 14
  }
}
```

---

## 💻 Компьютеры

### ✅ PUT `/api/computers/{id}/status`
```json
// Тело запроса
{
  "is_online": true,
  "session_id": 98
}

// Ответ
{
  "success": true,
  "message": "Статус компьютера обновлен"
}
```

---

### ✅ POST `/api/computers/register`
```json
// Тело запроса
{
  "user_id": 4,
  "hardware_id": 8,
  "hostname": "DESKTOP-TEST",
  "force_rebind": false
}
```

---

### ✅ PUT `/api/computers/{id}`
```json
// Тело запроса
{
  "hostname": "Новое имя компьютера",
  "description": "Рабочий компьютер бухгалтера",
  "computer_type": "admin"
}
```

---

## 📊 Сессии

### ✅ POST `/api/sessions`
```json
// Тело запроса
{
  "computer_id": 8,
  "user_id": 4,
  "session_token": "DESKTOP-TEST_2026-04-14_08-19-00"
}

// Ответ
{
  "success": true,
  "message": "Сессия успешно создана",
  "data": {
    "session_id": 99
  }
}
```

---

### ✅ PUT `/api/sessions/{id}`
```json
// Тело запроса
{
  "status_id": 1,
  "last_activity": "2026-04-14T08:20:00Z",
  "json_sent_count": 15,
  "error_count": 0
}

// Ответ
{
  "success": true,
  "message": "Session updated successfully"
}
```

---

### ✅ DELETE `/api/sessions/{id}`
```json
// Ответ
{
  "success": true,
  "message": "Session deleted successfully"
}
```

---

## 👤 Пользователи

### ✅ POST `/api/users`
```json
// Тело запроса
{
  "login": "ivanov",
  "password": "ivanov123",
  "full_name": "Иванов Иван",
  "role_id": 1,
  "is_active": true
}
```

---

### ✅ PUT `/api/users/{id}`
```json
// Тело запроса
{
  "full_name": "Иванов Иван Иванович",
  "role_id": 2,
  "is_active": true
}
```

---

## 🛡️ Роли

### ✅ POST `/api/roles`
```json
// Тело запроса
{
  "role_name": "moderator",
  "description": "Модератор системы"
}
```

---

## 🔧 Железо

### ✅ POST `/api/hardware`
```json
// Тело запроса
{
  "cpu_model": "Intel Core i7-10700K",
  "cpu_cores": 8,
  "ram_total": 32.0,
  "storage_total": 1000.0,
  "gpu_model": "NVIDIA GeForce RTX 3070",
  "motherboard": "ASUS ROG STRIX",
  "bios_version": "3801"
}
```

---

## 🌐 IP Адреса

### ✅ POST `/api/ip-addresses`
```json
// Тело запроса
{
  "computer_id": 8,
  "ip_address": "192.168.1.100",
  "subnet_mask": "255.255.255.0",
  "gateway": "192.168.1.1"
}
```

---

## 🖥️ Операционные системы

### ✅ POST `/api/operating-systems`
```json
// Тело запроса
{
  "os_name": "Windows",
  "os_version": "11",
  "os_build": "22621.1992",
  "os_architecture": "x64",
  "family_id": 1
}
```

---

## 📌 Статусы

### ✅ POST `/api/statuses`
```json
// Тело запроса
{
  "status_name": "error",
  "status_type": "session",
  "description": "Ошибка в сессии"
}
```

---

## 📈 Метрики

### ✅ POST `/api/metrics`
```json
// Тело запроса
{
  "computer_id": 8,
  "cpu_usage": 45.2,
  "ram_usage": 62.8,
  "disk_usage": 72.1,
  "network_in": 125000,
  "network_out": 89000,
  "timestamp": "2026-04-14T08:25:00Z"
}
```

---

## 🔍 Общие параметры для GET запросов

| Параметр | Описание |
|----------|----------|
| `page` | Номер страницы (по умолчанию 1) |
| `limit` | Количество записей на странице (по умолчанию 20) |
| `search` | Поиск по названию |
| `from` | Дата начала (ISO формат) |
| `to` | Дата окончания (ISO формат) |

---

### ✅ Пример ответа для списков
```json
{
  "success": true,
  "data": {
    "items": [
      // ... массив объектов
    ],
    "total": 156,
    "page": 1,
    "limit": 20,
    "pages": 8
  }
}
```

---

### ✅ Пример ответа ошибки
```json
{
  "success": false,
  "error": "Описание ошибки"
}
```

---

✅ ВСЕ ЭНДПОИНТЫ РЕАЛИЗОВАНЫ И РАБОТАЮТ