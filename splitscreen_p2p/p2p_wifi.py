"""
SplitScreenP2P Off-Grid Direct Networking and Zero-Config Discovery
Enables direct Wi-Fi P2P / Hotspot setup without external routers,
and broadcasts UDP beacons for zero-configuration host discovery.
"""

import sys
import socket
import json
import time
import subprocess
from typing import List, Dict, Optional, Tuple
from splitscreen_p2p.protocol import BEACON_MAGIC, DEFAULT_BEACON_PORT, DEFAULT_TCP_PORT


def get_local_ip_addresses() -> List[str]:
    """Retrieves all non-loopback local IPv4 addresses."""
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass

    # Fallback probe via dummy socket
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip not in ips:
                ips.append(ip)
        except Exception:
            ips.append("127.0.0.1")

    return ips


def get_wifi_direct_instructions() -> str:
    """Returns step-by-step instructions for off-grid P2P direct Wi-Fi linking."""
    if sys.platform == "win32":
        return (
            "=== Off-Grid Wi-Fi Direct Setup (Windows) ===\n"
            "Method 1 (Instant Windows Mobile Hotspot - Recommended):\n"
            "  1. In Windows Settings -> Network & Internet -> Mobile Hotspot, turn it ON.\n"
            "  2. Peer devices connect directly to this Wi-Fi network (no router needed).\n"
            "  3. Default Host IP is typically: 192.168.137.1\n\n"
            "Method 2 (Command Line HostedNetwork):\n"
            "  netsh wlan set hostednetwork mode=allow ssid=SplitP2P key=splitscreen123\n"
            "  netsh wlan start hostednetwork\n"
        )
    else:
        return (
            "=== Off-Grid Wi-Fi Direct Setup (Linux) ===\n"
            "Using NetworkManager Hotspot:\n"
            "  nmcli dev wifi hotspot ifname wlan0 ssid SplitP2P password splitscreen123\n"
            "Peers can connect directly to 'SplitP2P' with password 'splitscreen123'.\n"
            "Default Host IP is: 10.42.0.1\n"
        )


class P2PBeaconBroadcaster:
    """Periodically broadcasts UDP discovery beacon on the direct P2P network."""
    def __init__(self, host_name: str, tcp_port: int = DEFAULT_TCP_PORT, beacon_port: int = DEFAULT_BEACON_PORT):
        self.host_name = host_name
        self.tcp_port = tcp_port
        self.beacon_port = beacon_port
        self.running = False
        self.sock = None

    def start(self):
        self.running = True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception as e:
            print(f"[Beacon] Failed to create broadcast socket: {e}")
            self.sock = None

    def broadcast_tick(self, available_slots: List[int]):
        """Sends one beacon datagram."""
        if not self.running or not self.sock:
            return
        payload = {
            "service": "SplitScreenP2P",
            "host_name": self.host_name,
            "tcp_port": self.tcp_port,
            "available_slots": available_slots,
            "ts": time.time()
        }
        raw = BEACON_MAGIC + json.dumps(payload).encode("utf-8")
        try:
            self.sock.sendto(raw, ("<broadcast>", self.beacon_port))
        except Exception:
            pass

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


class P2PBeaconListener:
    """Listens for Host discovery beacons on the direct link."""
    def __init__(self, beacon_port: int = DEFAULT_BEACON_PORT, timeout_sec: float = 2.0):
        self.beacon_port = beacon_port
        self.timeout_sec = timeout_sec

    def discover(self) -> Optional[Dict]:
        """Listens for a broadcast beacon. Returns host metadata and IP if found."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", self.beacon_port))
            s.settimeout(self.timeout_sec)
        except Exception as e:
            print(f"[BeaconListener] Bind notice: {e}")
            return None

        t_end = time.time() + self.timeout_sec
        try:
            while time.time() < t_end:
                try:
                    data, addr = s.recvfrom(2048)
                    if data.startswith(BEACON_MAGIC):
                        json_bytes = data[len(BEACON_MAGIC):]
                        info = json.loads(json_bytes.decode("utf-8"))
                        info["host_ip"] = addr[0]
                        s.close()
                        return info
                except socket.timeout:
                    break
                except Exception:
                    pass
        finally:
            try:
                s.close()
            except Exception:
                pass
        return None
