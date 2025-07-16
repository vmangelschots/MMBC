import socket
import json

def start_udp_shelly_emulator(listen_port=1010):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", listen_port))
    print(f"[UDP] Listening on port {listen_port} for Shelly EM probes")

    while True:
        data, addr = sock.recvfrom(1024)
        print(f"[UDP] Received packet from {addr}: {data}")

        try:
            request = json.loads(data.decode())
            if request.get("method") == "EM.GetStatus":
                response = {
                    "id": request.get("id", 1),
                    "a_act_power": [100.0, 100.0, 100.0],
                    "a_voltage": [230.0, 230.0, 230.0],
                    "a_current": [0.43, 0.43, 0.43],
                    "total_act_power": 300.0,
                    "total_current": 1.29
                }
                response_bytes = json.dumps(response).encode()
                sock.sendto(response_bytes, addr)
                print(f"[UDP] Responded to {addr}")
        except Exception as e:
            print(f"[UDP] Failed to parse/handle packet: {e}")


if __name__ == "__main__":
    start_udp_shelly_emulator(listen_port=2020 )
    # You can change the port by passing a different value to start_udp_shelly_em