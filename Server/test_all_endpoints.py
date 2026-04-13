#!/usr/bin/env python3
"""
Скрипт для автоматического тестирования всех эндпоинтов PC-RMDS API Server
"""
import sys
import json
import requests
from datetime import datetime
from colorama import init, Fore, Style

# Инициализация colorama
init(autoreset=True)

# Конфигурация
API_BASE_URL = "http://localhost:5000"
TIMEOUT = 10

# Список всех эндпоинтов для тестирования
ENDPOINTS = [
    # Общие эндпоинты
    {"method": "GET", "path": "/", "name": "Корневой эндпоинт"},
    {"method": "GET", "path": "/health", "name": "Health Check"},
    
    # Computers API
    {"method": "GET", "path": "/api/computers", "name": "Список компьютеров"},
    {"method": "GET", "path": "/api/computers?page=1&limit=10", "name": "Список компьютеров (пагинация)"},
    {"method": "GET", "path": "/api/computers/1", "name": "Детали компьютера (ID=1)"},
    {"method": "GET", "path": "/api/computers/1/sessions", "name": "Сессии компьютера (ID=1)"},
    {"method": "GET", "path": "/api/computers/1/ip-history", "name": "История IP компьютера (ID=1)"},
    
    # Users API
    {"method": "GET", "path": "/api/users", "name": "Список пользователей"},
    {"method": "GET", "path": "/api/users/1", "name": "Детали пользователя (ID=1)"},
    {"method": "GET", "path": "/api/users/1/computers", "name": "Компьютеры пользователя (ID=1)"},
    {"method": "GET", "path": "/api/users/roles", "name": "Список ролей"},
    
    # Sessions API
    {"method": "GET", "path": "/api/sessions", "name": "Список сессий"},
    {"method": "GET", "path": "/api/sessions/active", "name": "Активные сессии"},
    {"method": "GET", "path": "/api/sessions/1", "name": "Детали сессии (ID=1)"},
    
    # Metrics API
    {"method": "GET", "path": "/api/metrics", "name": "Общие метрики"},
    {"method": "GET", "path": "/api/metrics/summary", "name": "Сводка метрик"},
    {"method": "GET", "path": "/api/metrics/events", "name": "События"},
    {"method": "GET", "path": "/api/metrics/anomalies", "name": "Аномалии"},
    {"method": "GET", "path": "/api/metrics/hardware", "name": "Оборудование"},
    {"method": "GET", "path": "/api/metrics/ip-addresses", "name": "IP адреса"},
    {"method": "GET", "path": "/api/metrics/operating-systems", "name": "Операционные системы"},
    {"method": "GET", "path": "/api/metrics/statuses", "name": "Статусы"},
    
    # Dashboard API
    {"method": "GET", "path": "/api/dashboard/stats", "name": "Статистика дашборда"},
    {"method": "GET", "path": "/api/dashboard/computers-summary", "name": "Сводка компьютеров"},
    {"method": "GET", "path": "/api/dashboard/activity", "name": "Активность"},
    {"method": "GET", "path": "/api/dashboard/top-users", "name": "Топ пользователей"},
    {"method": "GET", "path": "/api/dashboard/sessions-summary", "name": "Сводка сессий"},
    {"method": "GET", "path": "/api/dashboard/quick-stats", "name": "Быстрая статистика"},
    {"method": "GET", "path": "/api/dashboard/recent-activity", "name": "Последняя активность"},
    
    # Hardware API
    {"method": "GET", "path": "/api/hardware", "name": "Список конфигураций оборудования"},
    {"method": "GET", "path": "/api/hardware/unique", "name": "Уникальные конфигурации"},
    
    # IP Addresses API
    {"method": "GET", "path": "/api/ip-addresses", "name": "История IP адресов"},
    {"method": "GET", "path": "/api/ip-addresses/current", "name": "Текущие IP адреса"},
    
    # Operating Systems API
    {"method": "GET", "path": "/api/operating-systems", "name": "Список ОС"},
    {"method": "GET", "path": "/api/operating-systems/families", "name": "Семейства ОС"},
    
    # Roles API
    {"method": "GET", "path": "/api/roles", "name": "Список ролей"},
]

def log_result(success, name, status_code=None, error=None, response_time=None):
    """Логирование результата теста"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    if success:
        status = f"{Fore.GREEN}✅ PASS{Style.RESET_ALL}"
        extra = f" {status_code} | {response_time:.2f}ms" if status_code else ""
    else:
        status = f"{Fore.RED}❌ FAIL{Style.RESET_ALL}"
        extra = f" {status_code}" if status_code else ""
        if error:
            extra += f" | {error}"
    
    print(f"[{timestamp}] {status} | {name}{extra}")

def test_endpoint(endpoint):
    """Тестирование одного эндпоинта"""
    url = API_BASE_URL + endpoint["path"]
    method = endpoint["method"]
    name = endpoint["name"]
    
    try:
        start_time = datetime.now()
        
        if method == "GET":
            response = requests.get(url, timeout=TIMEOUT)
        elif method == "POST":
            response = requests.post(url, timeout=TIMEOUT)
        elif method == "PUT":
            response = requests.put(url, timeout=TIMEOUT)
        elif method == "DELETE":
            response = requests.delete(url, timeout=TIMEOUT)
        else:
            raise ValueError(f"Неизвестный метод: {method}")
        
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Проверка статуса ответа
        success = response.status_code in (200, 201, 404)
        
        # Проверка что ответ валидный JSON
        try:
            data = response.json()
            # Проверка стандартной структуры ответа
            if 'success' in data:
                success = success and (data['success'] is True or response.status_code == 404)
        except json.JSONDecodeError:
            success = False
            log_result(False, name, response.status_code, "Невалидный JSON", response_time)
            return False
        
        log_result(success, name, response.status_code, None, response_time)
        return success
        
    except requests.exceptions.ConnectionError:
        log_result(False, name, None, "Ошибка подключения - сервер не запущен?")
        return False
    except Exception as e:
        log_result(False, name, None, str(e))
        return False

def main():
    """Основная функция"""
    print(f"\n{Fore.CYAN}╔═══════════════════════════════════════════════════════════╗")
    print(f"{Fore.CYAN}║           PC-RMDS API ENDPOINTS TESTER                    ║")
    print(f"{Fore.CYAN}╠═══════════════════════════════════════════════════════════╣")
    print(f"{Fore.CYAN}║  Target: {API_BASE_URL:<45} ║")
    print(f"{Fore.CYAN}║  Total endpoints: {len(ENDPOINTS):<36} ║")
    print(f"{Fore.CYAN}╚═══════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")
    
    # Проверка доступности сервера
    print(f"{Fore.YELLOW}🔍 Проверка доступности API сервера...{Style.RESET_ALL}")
    try:
        requests.get(API_BASE_URL + "/health", timeout=5)
        print(f"{Fore.GREEN}✅ Сервер доступен\n{Style.RESET_ALL}")
    except:
        print(f"{Fore.RED}❌ Сервер недоступен! Запустите api_server.py сначала")
        print(f"{Fore.YELLOW}Команда для запуска: python api_server.py\n{Style.RESET_ALL}")
        sys.exit(1)
    
    # Запуск тестов
    print(f"{Fore.YELLOW}🚀 Начинаю тестирование эндпоинтов...{Style.RESET_ALL}\n")
    
    passed = 0
    failed = 0
    
    for endpoint in ENDPOINTS:
        if test_endpoint(endpoint):
            passed += 1
        else:
            failed += 1
    
    # Итоги
    print(f"\n{Fore.CYAN}═══════════════════════════════════════════════════════════")
    print(f"{Fore.CYAN}📊 ИТОГИ ТЕСТИРОВАНИЯ:")
    print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════")
    print(f"✅ Успешно: {passed}")
    print(f"❌ Ошибок: {failed}")
    print(f"📋 Всего: {len(ENDPOINTS)}")
    print(f"📈 Процент прохождения: {(passed/len(ENDPOINTS))*100:.1f}%")
    print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}\n")
    
    if failed == 0:
        print(f"{Fore.GREEN}🎉 Все эндпоинты работают корректно!{Style.RESET_ALL}\n")
    else:
        print(f"{Fore.YELLOW}⚠️  Обнаружены проблемы, проверьте вышеуказанные эндпоинты{Style.RESET_ALL}\n")

if __name__ == "__main__":
    main()