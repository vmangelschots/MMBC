import socket
import json
import threading

class ShellyController:
    def __init__(self):
        self.batteries = {}
        self._lock = threading.Lock()

    def set_charge(self, battery_ip: str, watts: int):
        with self._lock:
            self.batteries[battery_ip] = -watts

    def set_discharge(self, battery_ip: str, watts: int):
        with self._lock:
            self.batteries[battery_ip] = watts

    def set_idle(self, battery_ip: str):
        with self._lock:
            self.batteries[battery_ip] = 0

    def get_power_for_ip(self, ip: str) -> int:
        with self._lock:
            return self.batteries.get(ip, 0)
    def start_udp_proxy(self):
        """Starts the internal UDP Shelly 3EM emulator in a background thread."""
        def server_thread():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("", 2020))
            print(f"[ShellyController] UDP proxy listening on port 2020")

            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    sender_ip = addr[0]
                    print(f"[ShellyController] Received request from {sender_ip}: {data}")
                    request = json.loads(data.decode())

                    if request.get("method") == "EM.GetStatus":
                        watts = self.get_power_for_ip(sender_ip)
                        voltage = 230.0
                        current = abs(watts) / voltage if voltage else 0.0

                        response = {
                            "id": request.get("id", 1),
                            "a_act_power": [watts, 0.0, 0.0],
                            "a_voltage": [voltage, voltage, voltage],
                            "a_current": [current, 0.0, 0.0],
                            "total_act_power": watts,
                            "total_current": current
                        }

                        sock.sendto(json.dumps(response).encode(), addr)
                        print(f"[ShellyController] Responded to {sender_ip} with {watts} W")
                except Exception as e:
                    print(f"[ShellyController] Error: {e}")

        thread = threading.Thread(target=server_thread, daemon=True)
        thread.start()