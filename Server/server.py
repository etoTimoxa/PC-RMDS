import asyncio
import websockets
import json
import socket

hosts = {}
clients = {}

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
    try:
        async for msg in websocket:
            data = json.loads(msg)
            msg_type = data.get("type")
            
            if msg_type == "register_host":
                host_id = data["data"]["host_id"]
                hosts[host_id] = websocket
                print(f"Хост зарегистрирован: {host_id}")
            
            elif msg_type == "register_client":
                client_id = data["data"]["client_id"]
                target_host = data["data"]["host_id"]
                clients[client_id] = {"ws": websocket, "host_id": target_host}
                print(f"Клиент зарегистрирован: {client_id} -> {target_host}")
            
            elif msg_type in ["command", "mouse_move", "mouse_click", "key_press", "mouse_wheel", "request_system_info"]:
                host_id = data.get("host_id")
                if host_id in hosts:
                    await hosts[host_id].send(msg)
            
            elif msg_type in ["screenshot", "command_result", "system_info"]:
                host_id = data.get("host_id")
                for c_id, c_info in clients.items():
                    if c_info["host_id"] == host_id:
                        try:
                            await c_info["ws"].send(msg)
                        except:
                            pass

    except websockets.ConnectionClosed:
        for host_id, ws in list(hosts.items()):
            if ws == websocket:
                del hosts[host_id]
                break
        for client_id, c_info in list(clients.items()):
            if c_info["ws"] == websocket:
                del clients[client_id]
                break

async def main():
    PORT = find_free_port(9001)
    print(f"Сервер запущен на порту {PORT}")
    async with websockets.serve(handler, "0.0.0.0", PORT):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())