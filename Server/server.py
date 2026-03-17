import asyncio
import websockets
import json
import socket
from datetime import datetime

hosts = {}
clients = {}

def log(msg):
    """Функция для логирования с временной меткой"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [SERVER] {msg}")

def find_free_port(preferred_port=9001, max_port=9100):
    port = preferred_port
    while port <= max_port:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                log(f"Порт {port} свободен")
                return port
            except OSError:
                log(f"Порт {port} занят, пробуем следующий")
                port += 1
    raise RuntimeError("Нет свободных портов")

async def handler(websocket):
    client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    log(f"Новое подключение от {client_info}")
    
    try:
        async for msg in websocket:
            try:
                data = json.loads(msg)
                msg_type = data.get("type")
                log(f"Получено сообщение типа '{msg_type}' от {client_info}")
                
                if msg_type == "register_host":
                    host_id = data["data"]["host_id"]
                    hosts[host_id] = websocket
                    log(f"✅ Хост зарегистрирован: {host_id} (всего хостов: {len(hosts)})")
                
                elif msg_type == "register_client":
                    client_id = data["data"]["client_id"]
                    target_host = data["data"]["host_id"]
                    clients[client_id] = {"ws": websocket, "host_id": target_host}
                    log(f"✅ Клиент зарегистрирован: {client_id} -> {target_host} (всего клиентов: {len(clients)})")
                    
                    # Проверяем, существует ли целевой хост
                    if target_host in hosts:
                        log(f"✅ Целевой хост {target_host} найден")
                    else:
                        log(f"⚠️ Целевой хост {target_host} НЕ найден!")
                
                elif msg_type in ["command", "mouse_move", "mouse_click", "key_press", "mouse_wheel", 
                                "request_system_info", "start_stream", "stop_stream"]:
                    host_id = data.get("host_id")
                    client_id = data.get("client_id", "unknown")
                    
                    log(f"📤 Команда '{msg_type}' от клиента {client_id} для хоста {host_id}")
                    
                    if host_id in hosts:
                        # Добавляем client_id в сообщение, если его нет
                        if "client_id" not in data:
                            data["client_id"] = client_id
                            log(f"   Добавлен client_id={client_id} в сообщение")
                        
                        log(f"   Пересылаю команду хосту {host_id}")
                        await hosts[host_id].send(json.dumps(data))
                        log(f"   ✅ Команда переслана")
                    else:
                        log(f"   ❌ Хост {host_id} не найден! Доступные хосты: {list(hosts.keys())}")
                
                elif msg_type in ["screenshot", "command_result", "system_info"]:
                    host_id = data.get("host_id")
                    log(f"📥 Данные от хоста {host_id}, тип: {msg_type}")
                    
                    # Находим всех клиентов, которые подписаны на этот хост
                    found_clients = 0
                    for c_id, c_info in clients.items():
                        if c_info["host_id"] == host_id:
                            try:
                                await c_info["ws"].send(msg)
                                found_clients += 1
                                log(f"   📤 Переслано клиенту {c_id}")
                            except Exception as e:
                                log(f"   ❌ Ошибка отправки клиенту {c_id}: {e}")
                    
                    log(f"   Данные пересланы {found_clients} клиентам")

            except json.JSONDecodeError:
                log(f"❌ Ошибка парсинга JSON: {msg[:100]}")
            except Exception as e:
                log(f"❌ Ошибка обработки сообщения: {e}")

    except websockets.ConnectionClosed:
        log(f"🔌 Соединение с {client_info} закрыто")
    except Exception as e:
        log(f"❌ Ошибка соединения с {client_info}: {e}")
    finally:
        # Удаляем хосты
        for host_id, ws in list(hosts.items()):
            if ws == websocket:
                del hosts[host_id]
                log(f"❌ Хост отключен: {host_id}")
                break
        
        # Удаляем клиентов
        for client_id, c_info in list(clients.items()):
            if c_info["ws"] == websocket:
                del clients[client_id]
                log(f"❌ Клиент отключен: {client_id}")
                break
        
        log(f"Текущее состояние - хостов: {len(hosts)}, клиентов: {len(clients)}")

async def main():
    PORT = find_free_port(9001)
    log(f"🚀 Сервер запускается на порту {PORT}")
    log(f"📡 Адрес для подключения: ws://130.49.149.152:{PORT}")
    
    async with websockets.serve(handler, "0.0.0.0", PORT):
        log(f"✅ Сервер успешно запущен и слушает порт {PORT}")
        await asyncio.Future()  # работаем вечно

if __name__ == "__main__":
    log("="*50)
    log("ЗАПУСК СЕРВЕРА")
    log("="*50)
    asyncio.run(main())