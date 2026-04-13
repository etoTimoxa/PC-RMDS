import asyncio
import websockets
import json
import socket
import threading
from datetime import datetime

# Импортируем API сервер
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_server import create_app
from config import API_CONFIG

hosts = {}  # computer_id -> websocket (computer_id хранится как строка)
clients = {}  # client_id -> {"ws": websocket, "computer_id": computer_id}

def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [SERVER] {msg}")

def find_free_port(preferred_port=9001, max_port=9100):
    port = preferred_port
    while port <= max_port:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError("Нет свободных портов")

async def handler(websocket):
    client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    log(f"Новое подключение: {client_info}")
    
    try:
        async for msg in websocket:
            try:
                data = json.loads(msg)
                msg_type = data.get("type")
                log(f"Получено сообщение: {msg_type} от {client_info}")
                
                # Регистрация хоста (старый формат)
                if msg_type == "register_host":
                    host_id = data["data"]["host_id"]
                    hosts[str(host_id)] = websocket  # Приводим к строке
                    log(f"✅ Хост зарегистрирован (старый формат): host_id={host_id}")
                
                # Регистрация агента (новый формат от host.py с БД)
                elif msg_type == "register_agent":
                    agent_data = data.get("data", {})
                    computer_id = agent_data.get("computer_id")
                    session_id = agent_data.get("session_id")
                    hostname = agent_data.get("agent_id") or agent_data.get("hostname")
                    
                    log(f"Регистрация агента: computer_id={computer_id}, session_id={session_id}, hostname={hostname}")
                    
                    if computer_id is not None:
                        # Приводим computer_id к строке для единообразия
                        computer_id_str = str(computer_id)
                        hosts[computer_id_str] = websocket
                        
                        # Сохраняем дополнительную информацию
                        if not hasattr(websocket, 'computer_info'):
                            websocket.computer_info = {}
                        websocket.computer_info = {
                            'computer_id': computer_id,
                            'session_id': session_id,
                            'hostname': hostname
                        }
                        log(f"✅ Агент зарегистрирован: computer_id={computer_id_str}")
                        log(f"📋 Доступные хосты: {list(hosts.keys())}")
                    else:
                        log(f"❌ Ошибка: отсутствует computer_id в данных: {agent_data}")
                
                # Регистрация клиента
                elif msg_type == "register_client":
                    client_id = data["data"]["client_id"]
                    computer_id = data["data"].get("computer_id") or data["data"].get("host_id")
                    
                    log(f"Регистрация клиента: client_id={client_id}, computer_id={computer_id}")
                    
                    if computer_id is not None:
                        computer_id_str = str(computer_id)
                        clients[client_id] = {"ws": websocket, "computer_id": computer_id_str}
                        log(f"✅ Клиент зарегистрирован: {client_id} -> computer_id={computer_id_str}")
                        log(f"📋 Доступные хосты: {list(hosts.keys())}")
                        
                        # Проверяем, существует ли хост
                        if computer_id_str in hosts:
                            log(f"✅ Хост {computer_id_str} найден!")
                        else:
                            log(f"⚠️ Хост {computer_id_str} не найден в списке хостов!")
                        
                        # Отправляем подтверждение клиенту
                        await websocket.send(json.dumps({
                            "type": "registration_success",
                            "data": {"status": "ok", "computer_id": computer_id_str}
                        }))
                    else:
                        log(f"❌ Ошибка: отсутствует computer_id в данных клиента: {data}")
                
                # Команды от клиента к хосту
                elif msg_type in ["command", "mouse_move", "mouse_click", "key_press", "mouse_wheel", 
                                "request_system_info", "start_stream", "stop_stream", "keyboard_input"]:
                    computer_id = data.get("computer_id")
                    client_id = data.get("client_id", "unknown")
                    
                    log(f"Команда {msg_type} от {client_id} для computer_id={computer_id}")
                    
                    if computer_id is not None:
                        computer_id_str = str(computer_id)
                        if computer_id_str in hosts:
                            # Добавляем client_id если его нет
                            if "client_id" not in data:
                                data["client_id"] = client_id
                            
                            await hosts[computer_id_str].send(json.dumps(data))
                            log(f"✅ Команда {msg_type} отправлена хосту {computer_id_str}")
                        else:
                            log(f"❌ Хост {computer_id_str} не найден. Доступные хосты: {list(hosts.keys())}")
                    else:
                        log(f"❌ computer_id не указан в команде")
                
                # Данные от хоста к клиенту (скриншоты, системная информация)
                elif msg_type in ["screenshot", "command_result", "system_info"]:
                    computer_id = data.get("computer_id") or data.get("agent_id")
                    
                    log(f"Данные {msg_type} от computer_id={computer_id}")
                    
                    if computer_id is not None:
                        computer_id_str = str(computer_id)
                        # Отправляем всем клиентам, подключенным к этому компьютеру
                        sent_count = 0
                        for c_id, c_info in clients.items():
                            if c_info["computer_id"] == computer_id_str:
                                try:
                                    await c_info["ws"].send(msg)
                                    sent_count += 1
                                    log(f"✅ Данные отправлены клиенту {c_id}")
                                except Exception as e:
                                    log(f"❌ Ошибка отправки клиенту {c_id}: {e}")
                        
                        if sent_count > 0:
                            log(f"✅ Данные {msg_type} от {computer_id_str} отправлены {sent_count} клиентам")
                        else:
                            log(f"⚠️ Нет клиентов для computer_id={computer_id_str}. Клиенты: {[(k, v['computer_id']) for k, v in clients.items()]}")
                    else:
                        log(f"❌ computer_id не найден в данных {msg_type}")
                
                # Тестовое сообщение
                elif msg_type == "test":
                    log(f"Тестовое сообщение от {client_info}: {data}")
                    await websocket.send(json.dumps({"type": "test_response", "status": "ok"}))
                
                else:
                    log(f"⚠️ Неизвестный тип сообщения: {msg_type} от {client_info}")

            except json.JSONDecodeError as e:
                log(f"❌ Ошибка декодирования JSON: {e}")
            except Exception as e:
                log(f"❌ Ошибка обработки сообщения: {e}")

    except websockets.exceptions.ConnectionClosed:
        log(f"Соединение закрыто: {client_info}")
    except Exception as e:
        log(f"❌ Ошибка в обработчике: {e}")
    finally:
        # Очистка при отключении
        for computer_id, ws in list(hosts.items()):
            if ws == websocket:
                del hosts[computer_id]
                log(f"Хост отключен: computer_id={computer_id}")
                break
        
        for client_id, c_info in list(clients.items()):
            if c_info["ws"] == websocket:
                del clients[client_id]
                log(f"Клиент отключен: {client_id}")
                break

def run_api_server():
    """Функция для запуска Flask API сервера в отдельном потоке"""
    app = create_app()
    host = API_CONFIG['host']
    port = API_CONFIG['port']
    debug = API_CONFIG['debug']
    
    print(f"""
 ╔═══════════════════════════════════════════════════════════╗
 ║           PC-RMDS REST API Server                         ║
 ╠═══════════════════════════════════════════════════════════╣
 ║  Started at: http://{host}:{port}                         
 ║  Debug mode: {str(debug):5}                                  
 ╠═══════════════════════════════════════════════════════════╣
 ║  Endpoints:                                              ║
 ║    GET  /api/computers          - Список компьютеров      ║
 ║    GET  /api/users              - Список пользователей    ║
 ║    GET  /api/statuses           - Список статусов        ║
 ║    GET  /api/metrics            - Метрики из S3          ║
 ║    GET  /api/dashboard/stats   - Статистика              ║
 ║    GET  /health                 - Health check           ║
 ╚═══════════════════════════════════════════════════════════╝
     """)
    
    # Запускаем Flask сервер без debug режима в потоке (чтобы не было перезагрузки)
    app.run(
        host=host,
        port=port,
        debug=False,
        threaded=True,
        use_reloader=False
    )


async def main():
    # Запускаем API сервер в отдельном потоке демоне
    api_thread = threading.Thread(target=run_api_server, daemon=True)
    api_thread.start()
    
    PORT = find_free_port(9001)
    log(f"🚀 Запуск WebSocket сервера на порту: {PORT}")
    log(f"📡 Ожидание подключений...")
    
    async with websockets.serve(handler, "0.0.0.0", PORT):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("🛑 Сервер остановлен пользователем")
    except Exception as e:
        log(f"💥 Критическая ошибка: {e}")