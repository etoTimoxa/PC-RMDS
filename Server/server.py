import asyncio
import websockets
import json
import socket
import threading
from datetime import datetime
from typing import Dict, Set, Optional, Any

# Импортируем API сервер
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_server import create_app
from config import API_CONFIG

# -------------------------------
# Хранилища данных
# -------------------------------
hosts: Dict[str, Any] = {}  # computer_id -> websocket
clients: Dict[str, Dict] = {}  # client_id -> {"ws": websocket, "computer_id": str}
active_sessions: Dict[str, Dict] = {}  # computer_id -> полное состояние сессии
session_logs: Dict[str, list] = {}  # computer_id -> список всех событий сессии
blocked_clients: Set[str] = set()  # заблокированные клиенты
server_control_clients: Set[str] = set()  # клиенты под управлением сервера

# -------------------------------
# Логирование
# -------------------------------
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

# -------------------------------
# МЕНЕДЖЕР СЕССИЙ (НОВОЕ)
# -------------------------------
def init_session(computer_id: str, computer_info: Dict):
    """Инициализирует новую сессию для компьютера"""
    computer_id_str = str(computer_id)
    active_sessions[computer_id_str] = {
        "computer_id": computer_id,
        "hostname": computer_info.get('hostname'),
        "session_id": computer_info.get('session_id'),
        "status": "idle",
        "connected_admins": [],
        "start_time": datetime.now().isoformat(),
        "commands_sent": 0,
        "last_activity": datetime.now().isoformat(),
        "is_locked": False,
        "is_server_controlled": False,
        "streaming_enabled": True,
        "client_input_enabled": True,
        "allowed_commands": ["*"],
        "blocked_commands": []
    }
    session_logs[computer_id_str] = []
    log(f"✅ Сессия инициализирована для computer_id={computer_id_str}")

def log_session_event(computer_id: str, event_type: str, data: Dict):
    """Записывает абсолютно все события сессии"""
    computer_id_str = str(computer_id)
    if computer_id_str not in session_logs:
        session_logs[computer_id_str] = []
    
    event = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        "data": data
    }
    session_logs[computer_id_str].append(event)
    
    # Обновляем статистику сессии
    if computer_id_str in active_sessions:
        active_sessions[computer_id_str]["last_activity"] = datetime.now().isoformat()
        if event_type in ["command", "mouse_move", "mouse_click", "key_press"]:
            active_sessions[computer_id_str]["commands_sent"] += 1

def is_command_allowed(computer_id: str, command_type: str) -> bool:
    """Проверяет разрешена ли данная команда для выполнения"""
    computer_id_str = str(computer_id)
    if computer_id_str not in active_sessions:
        return True
    
    session = active_sessions[computer_id_str]
    
    if session.get("is_locked", False):
        return False
    
    if not session.get("client_input_enabled", True):
        return False
    
    if command_type in session.get("blocked_commands", []):
        return False
    
    allowed = session.get("allowed_commands", ["*"])
    if "*" in allowed:
        return True
    
    return command_type in allowed

# -------------------------------
# ПЕРЕХВАТЧИК КОМАНД (НОВОЕ)
# -------------------------------
async def intercept_client_command(data: Dict) -> Dict:
    """
    ✅ ОСНОВНОЙ ПЕРЕХВАТЧИК КОМАНД
    Вызывается ПЕРЕД тем как команда будет отправлена агенту
    Здесь можно модифицировать, блокировать, логировать любую команду
    """
    command_type = data.get("type")
    computer_id = data.get("computer_id")
    client_id = data.get("client_id", "unknown")
    
    # Логируем абсолютно все команды
    log_session_event(computer_id, command_type, {
        "client_id": client_id,
        "command_data": data.get("data", {})
    })
    
    # Проверяем разрешена ли команда
    if not is_command_allowed(computer_id, command_type):
        log(f"⛔ Команда {command_type} ЗАБЛОКИРОВАНА для computer_id={computer_id}")
        return None
    
    # Проверяем не заблокирован ли клиент
    if client_id in blocked_clients:
        log(f"⛔ Клиент {client_id} заблокирован, команда отклонена")
        return None
    
    # Если сессия под контролем сервера - игнорируем команды от обычных клиентов
    computer_id_str = str(computer_id)
    if computer_id_str in active_sessions and active_sessions[computer_id_str].get("is_server_controlled", False):
        if client_id not in server_control_clients:
            log(f"⚠️ Сессия {computer_id_str} под управлением сервера, команда от клиента {client_id} проигнорирована")
            return None
    
    # ✅ Здесь можно внедрять любую модификацию команд
    # Например: добавить серверные метки, изменить координаты, подменить данные
    
    log(f"🔍 Перехвачена команда {command_type} от {client_id} для {computer_id}")
    return data

async def intercept_host_message(data: Dict, original_msg: str) -> str:
    """
    Перехватывает сообщения ИЗ агента ПЕРЕД отправкой клиенту
    """
    msg_type = data.get("type")
    computer_id = data.get("computer_id") or data.get("agent_id")
    
    log_session_event(computer_id, f"host_{msg_type}", {
        "size": len(original_msg)
    })
    
    # ✅ Здесь можно модифицировать скриншоты, добавлять вотермарки, искажать и т.д.
    
    return original_msg

# -------------------------------
# СЕРВЕРНЫЕ КОМАНДЫ УПРАВЛЕНИЯ (НОВОЕ)
# -------------------------------
async def handle_server_control_command(data: Dict, ws):
    """Обрабатывает специальные команды управления от админа/сервера"""
    command = data.get("command")
    computer_id = str(data.get("computer_id"))
    
    log(f"⚙️ Серверная команда управления: {command} для {computer_id}")
    
    if command == "get_session_info":
        return {
            "type": "session_info",
            "data": active_sessions.get(computer_id, {})
        }
    
    elif command == "lock_session":
        if computer_id in active_sessions:
            active_sessions[computer_id]["is_locked"] = True
            return {"status": "ok", "message": "Сессия заблокирована"}
    
    elif command == "unlock_session":
        if computer_id in active_sessions:
            active_sessions[computer_id]["is_locked"] = False
            return {"status": "ok", "message": "Сессия разблокирована"}
    
    elif command == "take_control":
        if computer_id in active_sessions:
            active_sessions[computer_id]["is_server_controlled"] = True
            active_sessions[computer_id]["client_input_enabled"] = False
            return {"status": "ok", "message": "Управление перехвачено сервером"}
    
    elif command == "release_control":
        if computer_id in active_sessions:
            active_sessions[computer_id]["is_server_controlled"] = False
            active_sessions[computer_id]["client_input_enabled"] = True
            return {"status": "ok", "message": "Управление возвращено клиентам"}
    
    elif command == "mute_client":
        client_id = data.get("client_id")
        blocked_clients.add(client_id)
        return {"status": "ok", "message": f"Клиент {client_id} заглушен"}
    
    elif command == "send_server_command":
        # Отправить команду агенту от имени сервера
        if computer_id in hosts:
            await hosts[computer_id].send(json.dumps(data.get("command_data")))
            return {"status": "ok", "message": "Команда отправлена агенту"}
    
    return {"status": "error", "message": "Неизвестная команда"}

# -------------------------------
# ОСНОВНОЙ ОБРАБОТЧИК СОЕДИНЕНИЙ
# -------------------------------
async def handler(websocket):
    client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    log(f"Новое подключение: {client_info}")
    
    try:
        async for msg in websocket:
            try:
                data = json.loads(msg)
                msg_type = data.get("type")
                log(f"Получено сообщение: {msg_type} от {client_info}")
                
                # Регистрация хоста (агента)
                if msg_type == "register_host":
                    host_id = data["data"]["host_id"]
                    hosts[str(host_id)] = websocket
                    log(f"✅ Хост зарегистрирован (старый формат): host_id={host_id}")
                
                # Регистрация агента (новый формат)
                elif msg_type == "register_agent":
                    agent_data = data.get("data", {})
                    computer_id = agent_data.get("computer_id")
                    session_id = agent_data.get("session_id")
                    hostname = agent_data.get("agent_id") or agent_data.get("hostname")
                    
                    if computer_id is not None:
                        computer_id_str = str(computer_id)
                        hosts[computer_id_str] = websocket
                        
                        if not hasattr(websocket, 'computer_info'):
                            websocket.computer_info = {}
                        websocket.computer_info = {
                            'computer_id': computer_id,
                            'session_id': session_id,
                            'hostname': hostname
                        }
                        
                        # Инициализируем сессию
                        init_session(computer_id_str, websocket.computer_info)
                        log(f"✅ Агент зарегистрирован: computer_id={computer_id_str}")
                    else:
                        log(f"❌ Ошибка: отсутствует computer_id в данных: {agent_data}")
                
                # Регистрация клиента
                elif msg_type == "register_client":
                    client_id = data["data"]["client_id"]
                    computer_id = data["data"].get("computer_id") or data["data"].get("host_id")
                    
                    if computer_id is not None:
                        computer_id_str = str(computer_id)
                        clients[client_id] = {"ws": websocket, "computer_id": computer_id_str}
                        
                        # Добавляем клиента в сессию
                        if computer_id_str in active_sessions:
                            active_sessions[computer_id_str]["connected_admins"].append(client_id)
                        
                        log(f"✅ Клиент зарегистрирован: {client_id} -> computer_id={computer_id_str}")
                        
                        await websocket.send(json.dumps({
                            "type": "registration_success",
                            "data": {"status": "ok", "computer_id": computer_id_str}
                        }))
                    else:
                        log(f"❌ Ошибка: отсутствует computer_id в данных клиента: {data}")
                
                # Серверные команды управления
                elif msg_type == "server_control":
                    result = await handle_server_control_command(data, websocket)
                    await websocket.send(json.dumps(result))
                
                # Команды от клиента к хосту
                elif msg_type in ["command", "mouse_move", "mouse_click", "key_press", "mouse_wheel", 
                                "request_system_info", "start_stream", "stop_stream", "keyboard_input"]:
                    computer_id = data.get("computer_id")
                    client_id = data.get("client_id", "unknown")
                    
                    if computer_id is not None:
                        computer_id_str = str(computer_id)
                        
                        # ✅ ПЕРЕХВАТ КОМАНДЫ
                        modified_data = await intercept_client_command(data)
                        
                        if modified_data is None:
                            continue  # Команда заблокирована
                        
                        if computer_id_str in hosts:
                            if "client_id" not in modified_data:
                                modified_data["client_id"] = client_id
                            
                            await hosts[computer_id_str].send(json.dumps(modified_data))
                            log(f"✅ Команда {msg_type} отправлена хосту {computer_id_str}")
                        else:
                            log(f"❌ Хост {computer_id_str} не найден")
                    else:
                        log(f"❌ computer_id не указан в команде")
                
                # Данные от хоста к клиенту
                elif msg_type in ["screenshot", "audio_chunk", "command_result", "system_info"]:
                    computer_id = data.get("computer_id") or data.get("agent_id")
                    
                    if computer_id is not None:
                        computer_id_str = str(computer_id)
                        
                        # ✅ ПЕРЕХВАТ ДАННЫХ ОТ АГЕНТА
                        if msg_type == "audio_chunk":
                            # Для аудио не модифицируем сообщение, передаем как есть
                            modified_msg = msg
                        else:
                            modified_msg = await intercept_host_message(data, msg)
                        
                        # Отправляем всем клиентам
                        sent_count = 0
                        for c_id, c_info in clients.items():
                            if c_info["computer_id"] == computer_id_str:
                                try:
                                    await c_info["ws"].send(modified_msg)
                                    sent_count += 1
                                except Exception as e:
                                    log(f"❌ Ошибка отправки клиенту {c_id}: {e}")
                        
                        if sent_count > 0:
                            log(f"✅ Данные {msg_type} от {computer_id_str} отправлены {sent_count} клиентам")
                        else:
                            log(f"⚠️ Нет клиентов для computer_id={computer_id_str}")
                
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
                if computer_id in active_sessions:
                    del active_sessions[computer_id]
                if computer_id in session_logs:
                    del session_logs[computer_id]
                log(f"Хост отключен: computer_id={computer_id}")
                break
        
        for client_id, c_info in list(clients.items()):
            if c_info["ws"] == websocket:
                computer_id = c_info["computer_id"]
                if computer_id in active_sessions and client_id in active_sessions[computer_id]["connected_admins"]:
                    active_sessions[computer_id]["connected_admins"].remove(client_id)
                del clients[client_id]
                if client_id in blocked_clients:
                    blocked_clients.remove(client_id)
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
