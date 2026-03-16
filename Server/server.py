import asyncio
import websockets
import logging
import sys
import socket
import json

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("relay_server.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("relay")

# === Автоматический выбор свободного порта ===
def find_free_port(preferred_port=9001, max_port=9100):
    port = preferred_port
    while port <= max_port:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                s.close()
                return port
            except OSError:
                port += 1
    raise RuntimeError("Нет свободных портов")

# === Словари подключений ===
hosts = {}    # host_id -> websocket
clients = {}  # client_id -> websocket

async def handler(websocket):
    try:
        async for msg in websocket:
            data = json.loads(msg)
            msg_type = data.get("type")
            
            # Регистрация хоста
            if msg_type == "register_host":
                host_id = data["data"]["host_id"]
                hosts[host_id] = websocket
                logger.info(f"Хост зарегистрирован: {host_id}")
            
            # Регистрация клиента
            elif msg_type == "register_client":
                client_id = data["data"]["client_id"]
                target_host = data["data"]["host_id"]
                clients[client_id] = {"ws": websocket, "host_id": target_host}
                logger.info(f"Клиент зарегистрирован: {client_id} -> {target_host}")
            
            # Пересылка сообщений от клиента к хосту
            elif msg_type in ["command", "mouse_move", "mouse_click", "key_press"]:
                host_id = data.get("host_id")
                host_ws = hosts.get(host_id)
                if host_ws:
                    await host_ws.send(msg)
            
            # Пересылка скриншотов и результатов команд от хоста клиенту
            elif msg_type in ["screenshot", "command_result"]:
                host_id = data.get("host_id")
                for c_id, c_info in clients.items():
                    if c_info["host_id"] == host_id:
                        await c_info["ws"].send(msg)
            
            else:
                logger.warning(f"Неизвестный тип сообщения: {msg_type}")

    except websockets.ConnectionClosed:
        logger.info("Соединение закрыто")
    except Exception as e:
        logger.error(f"Ошибка: {e}")

async def main():
    PORT = find_free_port(9001)
    logger.info(f"Relay-сервер запущен на порту {PORT}")
    async with websockets.serve(handler, "0.0.0.0", PORT):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"Ошибка при запуске сервера: {e}")