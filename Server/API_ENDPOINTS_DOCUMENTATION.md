# Полная документация по API эндпоинтам PC-RMDS Server

Все эндпоинты имеют префикс `/api`

---

## 📊 Группа эндпоинтов /metrics (Метрики)
✅ **Для всех GET эндпоинтов метрик работает одинаковый принцип фильтрации:**

✅ **Обязательные параметры:**
- `from` - начальная дата (формат `YYYY-MM-DD`)
- `to` - конечная дата (формат `YYYY-MM-DD`)

✅ **Один из двух параметров обязательно:**
- `computer_id` - ID компьютера в базе данных
- `hostname` - hostname компьютера напрямую

| Метод | Эндпоинт | Описание | Дополнительные параметры |
|-------|----------|----------|--------------------------|
| GET | `/api/metrics/full-period` | Получить все сырые записи файлов метрик за указанный период | |
| GET | `/api/metrics/performance` | Получить ВСЕ точки показателей производительности (CPU, RAM, Disk, Network) за период | |
| GET | `/api/metrics/average` | Получить усредненные показатели производительности за период | |
| GET | `/api/metrics/events` | Получить все системные события за период | |
| GET | `/api/metrics/events/statistics` | Получить статистику по типам событий за период | |
| GET | `/api/metrics/anomalies` | Получить записи с аномально высокой нагрузкой | `cpu_threshold` (по умолчанию 90%), `ram_threshold` (по умолчанию 90%) |
| POST | `/api/metrics/upload` | Загрузка файла метрик в S3 хранилище | Принимает `multipart/form-data` с полем `file` |

### ✨ Примеры запросов метрик:

#### 🔹 Получить метрики по ID компьютера за период:
```
GET /api/metrics/performance?computer_id=123&from=2026-04-01&to=2026-04-14
```

#### 🔹 Получить метрики по hostname компьютера:
```
GET /api/metrics/average?hostname=WORKSTATION-07&from=2026-04-10&to=2026-04-14
```

#### 🔹 Получить аномалии с кастомным порогом:
```
GET /api/metrics/anomalies?computer_id=45&from=2026-04-01&to=2026-04-14&cpu_threshold=85&ram_threshold=95
```

---

## 💻 Группа эндпоинтов /computers (Компьютеры)

| Метод | Эндпоинт | Описание | Параметры |
|-------|----------|----------|-----------|
| POST | `/api/computers/register` | Регистрация/привязка компьютера к пользователю | `user_id`, `hardware_hash`, `hostname`, `mac_address` |
| GET | `/api/computers` | Получить список всех компьютеров | `page`, `limit`, `status`, `type`, `search`, `user_id`, `os_id` |
| GET | `/api/computers/{id}` | Получить детальную информацию по конкретному компьютеру | |
| PUT | `/api/computers/{id}` | Обновить данные компьютера | 📌 Поддерживает частичное обновление, можно передавать только измененные поля |
| DELETE | `/api/computers/{id}` | Удалить компьютер из системы | |
| PUT | `/api/computers/{id}/status` | Обновить статус онлайн/оффлайн компьютера | `is_online` |
| GET | `/api/computers/{id}/sessions` | Получить историю сессий компьютера | `limit` |
| GET | `/api/computers/{id}/ip-addresses` | Получить историю IP адресов компьютера | |

### ✨ Пример обновления информации о компьютере:
```http
PUT /api/computers/123
Content-Type: application/json

{
  "hostname": "NEW-HOSTNAME-PC",
  "computer_type": "server",
  "description": "Рабочая станция бухгалтерии",
  "location": "Офис 305",
  "os_id": 7
}
```

✅ Поля которые можно обновлять:
`hostname`, `computer_type`, `description`, `location`, `os_id`, `hardware_config_id`, `department`, `inventory_number`

✅ Ответ:
```json
{
  "success": true,
  "message": "Computer updated successfully"
}
```

---

## 🔐 Группа эндпоинтов /auth (Авторизация)
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| POST | `/api/auth/login` | Авторизация пользователя |
| POST | `/api/auth/register` | Регистрация нового пользователя |
| POST | `/api/auth/refresh` | Обновление токена доступа |
| POST | `/api/auth/logout` | Выход из системы |

---

## 👤 Группа эндпоинтов /users (Пользователи)
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/users` | Список пользователей |
| GET | `/api/users/{id}` | Информация о пользователе |
| POST | `/api/users` | Создание пользователя |
| PUT | `/api/users/{id}` | Редактирование пользователя |
| DELETE | `/api/users/{id}` | Удаление пользователя |

---

## 📈 Группа эндпоинтов /dashboard (Дашборд)
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/dashboard/overview` | Общая статистика для главной страницы |
| GET | `/api/dashboard/online` | Список онлайн компьютеров |
| GET | `/api/dashboard/stats` | Сводная статистика по системе |

---

## 🕒 Группа эндпоинтов /sessions (Сессии)
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/sessions` | Список всех активных сессий |
| GET | `/api/sessions/{id}` | Детали сессии |
| DELETE | `/api/sessions/{id}` | Завершить сессию |

---

## 📋 Группа эндпоинтов /statuses (Статусы)
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/statuses` | Список возможных статусов компьютеров |
| GET | `/api/statuses/{id}` | Информация о статусе |

---

## ⚙️ Дополнительные группы эндпоинтов:
- `/api/hardware` - работа с конфигурациями железа
- `/api/ip-addresses` - справочник IP адресов
- `/api/operating-systems` - справочник операционных систем
- `/api/roles` - управление ролями пользователей

---

## 📝 Общая информация:
✅ Все ответы возвращаются в формате JSON с полями:
- `success` - `true/false` статус выполнения запроса
- `data` - данные ответа (при успехе)
- `error` - текст ошибки (при неудаче)

✅ Коды статусов HTTP:
- `200` - успешный запрос
- `400` - ошибка в параметрах запроса
- `404` - ресурс не найден
- `409` - конфликт данных
- `500` - внутренняя ошибка сервера

---

## 📋 Данные возвращаемые GET эндпоинтами

### 💻 GET /api/computers/{id}
| Поле | Тип | Описание |
|------|-----|----------|
| `computer_id` | int | Уникальный ID компьютера |
| `hostname` | string | Имя компьютера в сети |
| `mac_address` | string | MAC адрес сетевого адаптера |
| `computer_type` | string | Тип компьютера (client/server/laptop) |
| `is_online` | bool | Статус онлайн |
| `last_online` | datetime | Время последней активности |
| `description` | string | Описание компьютера |
| `location` | string | Физическое расположение |
| `department` | string | Отдел |
| `inventory_number` | string | Инвентарный номер |
| `user_id` | int | ID владельца пользователя |
| `os_id` | int | ID операционной системы |
| `hardware_config_id` | int | ID конфигурации железа |
| `created_at` | datetime | Дата регистрации компьютера |
| `login` | string | Логин владельца |
| `full_name` | string | Полное имя владельца |
| `os_name` | string | Название операционной системы |
| `os_version` | string | Версия операционной системы |
| `cpu_model` | string | Модель процессора |
| `cpu_cores` | int | Количество ядер процессора |
| `ram_total` | float | Объем оперативной памяти ГБ |
| `storage_total` | float | Объем диска ГБ |
| `gpu_model` | string | Модель видеокарты |
| `current_ip` | string | Последний известный IP адрес |

---

### 📊 GET /api/metrics/performance
| Поле | Тип | Описание |
|------|-----|----------|
| `timestamp` | datetime | Время замера |
| `cpu_usage` | float | Загрузка процессора % |
| `ram_usage` | float | Загрузка оперативной памяти % |
| `ram_used` | float | Использовано памяти МБ |
| `disk_usage` | float | Загрузка диска % |
| `disk_read` | float | Скорость чтения с диска МБ/с |
| `disk_write` | float | Скорость записи на диск МБ/с |
| `network_rx` | float | Входящий трафик МБ/с |
| `network_tx` | float | Исходящий трафик МБ/с |
| `uptime` | int | Время работы системы в секундах |
| `process_count` | int | Количество запущенных процессов |

---

### 📊 GET /api/metrics/average
| Поле | Тип | Описание |
|------|-----|----------|
| `period_from` | datetime | Начало периода |
| `period_to` | datetime | Конец периода |
| `avg_cpu` | float | Средняя загрузка CPU % |
| `max_cpu` | float | Максимальная загрузка CPU % |
| `min_cpu` | float | Минимальная загрузка CPU % |
| `avg_ram` | float | Средняя загрузка RAM % |
| `max_ram` | float | Максимальная загрузка RAM % |
| `avg_disk` | float | Средняя загрузка диска % |
| `total_network_rx` | float | Общий входящий трафик за период |
| `total_network_tx` | float | Общий исходящий трафик за период |
| `measurement_count` | int | Количество точек замера |

---

### 📊 GET /api/metrics/events
| Поле | Тип | Описание |
|------|-----|----------|
| `timestamp` | datetime | Время события |
| `event_type` | string | Тип события |
| `event_level` | string | Уровень критичности (info/warning/error/critical) |
| `source` | string | Источник события |
| `message` | string | Текст описания события |
| `data` | object | Дополнительные данные события |

---

### 👤 GET /api/users/{id}
| Поле | Тип | Описание |
|------|-----|----------|
| `user_id` | int | Уникальный ID пользователя |
| `login` | string | Логин |
| `full_name` | string | Полное имя |
| `email` | string | Email адрес |
| `role_id` | int | ID роли |
| `role_name` | string | Название роли |
| `is_active` | bool | Статус активности |
| `last_login` | datetime | Время последнего входа |
| `created_at` | datetime | Дата регистрации |
| `computer_count` | int | Количество компьютеров закрепленных за пользователем |

---

### 🕒 GET /api/sessions/{id}
| Поле | Тип | Описание |
|------|-----|----------|
| `session_id` | int | Уникальный ID сессии |
| `computer_id` | int | ID компьютера |
| `hostname` | string | Имя компьютера |
| `user_id` | int | ID пользователя сессии |
| `start_time` | datetime | Время начала сессии |
| `end_time` | datetime | Время окончания сессии |
| `last_activity` | datetime | Время последней активности |
| `status_id` | int | ID статуса |
| `status_name` | string | Название статуса |
| `json_sent_count` | int | Количество отправленных метрик |
| `error_count` | int | Количество ошибок за сессию |

---

### ⚙️ GET /api/hardware/{id}
| Поле | Тип | Описание |
|------|-----|----------|
| `config_id` | int | Уникальный ID конфигурации |
| `cpu_model` | string | Модель процессора |
| `cpu_cores` | int | Количество ядер процессора |
| `ram_total` | float | Объем оперативной памяти ГБ |
| `storage_total` | float | Объем дискового хранилища ГБ |
| `gpu_model` | string | Модель видеокарты |
| `motherboard` | string | Модель материнской платы |
| `bios_version` | string | Версия BIOS |
| `detected_at` | datetime | Дата первого обнаружения конфигурации |
| `computer_count` | int | Количество компьютеров с такой конфигурацией |

---

### 📈 GET /api/dashboard/overview
| Поле | Тип | Описание |
|------|-----|----------|
| `total_computers` | int | Общее количество компьютеров в системе |
| `online_computers` | int | Количество компьютеров онлайн |
| `offline_computers` | int | Количество компьютеров оффлайн |
| `total_users` | int | Количество активных пользователей |
| `active_sessions` | int | Количество активных сессий сейчас |
| `sessions_24h` | int | Количество сессий за последние 24 часа |
| `by_operating_system` | array | Статистика по операционным системам |

---

### 🌐 GET /api/computers/{id}/ip-addresses
Возвращает полную историю всех IP адресов которые использовал компьютер

| Поле | Тип | Описание |
|------|-----|----------|
| `computer_id` | int | ID компьютера |
| `ip_addresses` | array | Массив записей истории IP |
| `ip_address` | string | IPv4/IPv6 адрес |
| `subnet_mask` | string | Маска подсети |
| `gateway` | string | Адрес шлюза |
| `detected_at` | datetime | Время когда этот IP был обнаружен |


