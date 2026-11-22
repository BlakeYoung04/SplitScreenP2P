"""
SplitScreenP2P Networking Engine
Manages Host and Client TCP Signaling, UDP Video Distribution, and UDP Input Telemetry.
"""

import socket
import select
import threading
import time
from typing import Dict, Any, Optional, Tuple, Callable
import numpy as np

from splitscreen_p2p.protocol import (
    DEFAULT_TCP_PORT,
    DEFAULT_UDP_VIDEO_PORT,
    DEFAULT_UDP_INPUT_PORT,
    pack_tcp_message,
    TcpStreamReader,
    VideoFrameReassembler,
    unpack_gamepad_packet
)
from splitscreen_p2p.capture import ScreenCaptureEngine, compute_crop_rect, MODE_4P_QUADRANT
from splitscreen_p2p.encoder import VideoEncoder, VideoDecoder
from splitscreen_p2p.input_handler import ViGEmControllerManager, HostInputDispatcher, ClientInputReader
from splitscreen_p2p.p2p_wifi import P2PBeaconBroadcaster, P2PBeaconListener, get_local_ip_addresses


class ConnectedPeer:
    """Represents a connected client on the host."""
    def __init__(self, slot_id: int, tcp_sock: socket.socket, addr: Tuple[str, int]):
        self.slot_id = slot_id
        self.tcp_sock = tcp_sock
        self.addr = addr
        self.client_name = "Unknown"
        self.udp_addr = (addr[0], DEFAULT_UDP_VIDEO_PORT)
        self.crop_rect = (0, 0, 960, 540)
        self.reader = TcpStreamReader()
        self.last_input_time = time.time()
        self.encoder = VideoEncoder(quality=75)
        self.stats = {"fps": 0, "kbps": 0, "frames_sent": 0}


class HostServer:
    """
    Main Host/Server controller for SplitScreenP2P.
    Orchestrates screen capture, cropping, UDP video multicasting,
    TCP connection control, and virtual controller emulation.
    """
    def __init__(
        self,
        tcp_port: int = DEFAULT_TCP_PORT,
        udp_video_port: int = DEFAULT_UDP_VIDEO_PORT,
        udp_input_port: int = DEFAULT_UDP_INPUT_PORT,
        force_demo: bool = False,
        split_mode: str = MODE_4P_QUADRANT,
        target_fps: int = 60
    ):
        self.tcp_port = tcp_port
        self.udp_video_port = udp_video_port
        self.udp_input_port = udp_input_port
        self.split_mode = split_mode
        self.target_fps = target_fps
        self.running = False

        self.capture_engine = ScreenCaptureEngine(force_demo=force_demo)
        self.input_manager = ViGEmControllerManager()

        self.peers: Dict[int, ConnectedPeer] = {}  # slot_id -> ConnectedPeer
        self.available_slots = [2, 3, 4]  # Slot 1 is local host player

        # Sockets
        self.tcp_server_sock: Optional[socket.socket] = None
        self.udp_video_sock: Optional[socket.socket] = None
        self.udp_input_sock: Optional[socket.socket] = None

        self.beacon = P2PBeaconBroadcaster("SplitScreenP2P-Host", self.tcp_port)

        # Worker threads
        self.threads = []
        self.latest_full_frame: Optional[np.ndarray] = None
        self.fps_meter = 0.0
        self.broadcast_fullscreen = False

    def toggle_fullscreen_broadcast(self) -> bool:
        """Toggles between split-screen quadrant cropping and full display broadcast."""
        self.broadcast_fullscreen = not self.broadcast_fullscreen
        mode_str = "FULLSCREEN BROADCAST" if self.broadcast_fullscreen else "SPLIT-SCREEN SLICING"
        print(f"[Host] Streaming mode changed to: {mode_str}")
        return self.broadcast_fullscreen

    def start(self):
        """Starts all network listeners and streaming threads."""
        self.running = True

        # 1. Setup TCP Server
        self.tcp_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_server_sock.bind(("0.0.0.0", self.tcp_port))
        self.tcp_server_sock.listen(5)
        self.tcp_server_sock.setblocking(False)

        # 2. Setup UDP Sockets
        self.udp_video_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Increase send buffer for 60fps video
        try:
            self.udp_video_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2 * 1024 * 1024)
        except Exception:
            pass

        self.udp_input_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_input_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_input_sock.bind(("0.0.0.0", self.udp_input_port))
        self.udp_input_sock.setblocking(False)

        # 3. Start Beacon
        self.beacon.start()

        # 4. Launch Threads
        t_tcp = threading.Thread(target=self._tcp_thread_loop, daemon=True)
        t_input = threading.Thread(target=self._udp_input_thread_loop, daemon=True)
        t_stream = threading.Thread(target=self._video_stream_thread_loop, daemon=True)
        t_beacon = threading.Thread(target=self._beacon_thread_loop, daemon=True)

        self.threads.extend([t_tcp, t_input, t_stream, t_beacon])
        for t in self.threads:
            t.start()

        local_ips = get_local_ip_addresses()
        print(f"[Host] Started SplitScreenP2P Server on IPs: {local_ips}")
        print(f"[Host] TCP Port: {self.tcp_port} | Video UDP: {self.udp_video_port} | Input UDP: {self.udp_input_port}")

    def _beacon_thread_loop(self):
        while self.running:
            self.beacon.broadcast_tick(self.available_slots)
            time.sleep(1.0)

    def _tcp_thread_loop(self):
        while self.running:
            try:
                r, _, _ = select.select([self.tcp_server_sock], [], [], 0.1)
                if r:
                    client_sock, addr = self.tcp_server_sock.accept()
                    client_sock.setblocking(False)
                    self._handle_new_tcp_connection(client_sock, addr)
            except Exception:
                pass

            # Read from existing peers
            for slot_id, peer in list(self.peers.items()):
                try:
                    r, _, _ = select.select([peer.tcp_sock], [], [], 0.0)
                    if r:
                        data = peer.tcp_sock.recv(4096)
                        if not data:
                            self._disconnect_peer(slot_id, "Connection closed by client")
                            continue
                        messages = peer.reader.feed(data)
                        for msg in messages:
                            self._handle_tcp_message(peer, msg)
                except Exception:
                    self._disconnect_peer(slot_id, "Socket read error")

    def _handle_new_tcp_connection(self, sock: socket.socket, addr: Tuple[str, int]):
        if not self.available_slots:
            # Server full
            reject = pack_tcp_message({"type": "SERVER_FULL", "reason": "No player slots available (max 4)"})
            sock.sendall(reject)
            sock.close()
            return

        slot_id = self.available_slots.pop(0)
        peer = ConnectedPeer(slot_id, sock, addr)
        self.peers[slot_id] = peer

        # Prepare virtual controller on host for this slot
        self.input_manager.create_controller_for_slot(slot_id)
        print(f"[Host] Client connected from {addr[0]}:{addr[1]} assigned to Player Slot {slot_id}")

    def _handle_tcp_message(self, peer: ConnectedPeer, msg: Dict[str, Any]):
        msg_type = msg.get("type")
        if msg_type == "CLIENT_HELLO":
            peer.client_name = msg.get("client_name", "RemotePeer")
            client_udp_port = msg.get("udp_video_port", DEFAULT_UDP_VIDEO_PORT)
            peer.udp_addr = (peer.addr[0], client_udp_port)

            # Compute crop rectangle based on split mode
            w, h = 1920, 1080
            crop_rect = compute_crop_rect(self.split_mode, peer.slot_id, w, h)
            peer.crop_rect = crop_rect

            # Send assignment
            assign_msg = {
                "type": "HOST_SESSION_ASSIGN",
                "player_slot": peer.slot_id,
                "crop_rect": crop_rect,
                "udp_video_port": self.udp_video_port,
                "udp_input_port": self.udp_input_port,
                "target_fps": self.target_fps
            }
            peer.tcp_sock.sendall(pack_tcp_message(assign_msg))
            print(f"[Host] Sent session assign to Slot {peer.slot_id} with crop {crop_rect}")

    def _disconnect_peer(self, slot_id: int, reason: str):
        if slot_id in self.peers:
            peer = self.peers.pop(slot_id)
            try:
                peer.tcp_sock.close()
            except Exception:
                pass
            if slot_id not in self.available_slots:
                self.available_slots.append(slot_id)
                self.available_slots.sort()
            print(f"[Host] Player Slot {slot_id} disconnected ({reason})")

    def _udp_input_thread_loop(self):
        """Receives 120-250 Hz UDP gamepad packets from clients."""
        while self.running:
            try:
                r, _, _ = select.select([self.udp_input_sock], [], [], 0.05)
                if r:
                    data, _ = self.udp_input_sock.recvfrom(512)
                    parsed = unpack_gamepad_packet(data)
                    if parsed:
                        slot_id = parsed["slot_id"]
                        # Forward to virtual hardware controller
                        self.input_manager.update_controller(
                            slot_id=slot_id,
                            buttons=parsed["buttons"],
                            l_trig=parsed["left_trigger"],
                            r_trig=parsed["right_trigger"],
                            lx=parsed["thumb_lx"],
                            ly=parsed["thumb_ly"],
                            rx=parsed["thumb_rx"],
                            ry=parsed["thumb_ry"]
                        )
                        # Also feed synthetic demo engine if running
                        self.capture_engine.synthetic.update_player_input(
                            slot_id=slot_id,
                            lx=parsed["thumb_lx"],
                            ly=parsed["thumb_ly"],
                            btn_a=bool(parsed["buttons"] & 1)
                        )
            except Exception:
                pass

    def _video_stream_thread_loop(self):
        """High performance 60 FPS capture, crop, encode, and transmit loop."""
        frame_interval = 1.0 / self.target_fps
        frame_times = []

        while self.running:
            t_loop_start = time.perf_counter()

            # 1. Grab full screen or synthetic canvas
            full_frame = self.capture_engine.grab_full_frame()
            self.latest_full_frame = full_frame
            fh, fw = full_frame.shape[:2]

            # 2. Distribute cropped slices or full screen to each active peer
            for slot_id, peer in list(self.peers.items()):
                if self.broadcast_fullscreen:
                    slice_img = full_frame
                    peer.crop_rect = (0, 0, fw, fh)
                else:
                    # Recompute crop if frame dimensions changed
                    crop = compute_crop_rect(self.split_mode, slot_id, fw, fh)
                    peer.crop_rect = crop
                    x, y, w, h = crop
                    slice_img = full_frame[y:y+h, x:x+w]

                # Encode and fragment
                fid, packets, enc_ms = peer.encoder.encode_and_fragment(slice_img, slot_id)

                # Send all packets over UDP
                for pkt in packets:
                    try:
                        self.udp_video_sock.sendto(pkt, peer.udp_addr)
                    except Exception:
                        pass

                peer.stats["frames_sent"] += 1

            # Timing control for stable target FPS
            elapsed = time.perf_counter() - t_loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

            now_p = time.perf_counter()
            frame_times.append(now_p)
            while frame_times and now_p - frame_times[0] > 1.0:
                frame_times.pop(0)
            self.fps_meter = float(len(frame_times))

    def stop(self):
        self.running = False
        self.beacon.close()
        for slot_id in list(self.peers.keys()):
            self._disconnect_peer(slot_id, "Server stopping")
        self.input_manager.close()
        if self.tcp_server_sock:
            try:
                self.tcp_server_sock.close()
            except Exception:
                pass
        if self.udp_video_sock:
            try:
                self.udp_video_sock.close()
            except Exception:
                pass
        if self.udp_input_sock:
            try:
                self.udp_input_sock.close()
            except Exception:
                pass
        print("[Host] Stopped SplitScreenP2P Server.")


class StreamClient:
    """
    Client agent for SplitScreenP2P.
    Connects to Host via TCP, receives cropped stream over UDP, and sends gamepad telemetry.
    """
    def __init__(
        self,
        host_ip: Optional[str] = None,
        tcp_port: int = DEFAULT_TCP_PORT,
        udp_video_port: int = DEFAULT_UDP_VIDEO_PORT,
        udp_input_port: int = DEFAULT_UDP_INPUT_PORT,
        client_name: str = "ClientPeer"
    ):
        self.host_ip = host_ip
        self.tcp_port = tcp_port
        self.udp_video_port = udp_video_port
        self.udp_input_port = udp_input_port
        self.client_name = client_name
        self.running = False

        self.slot_id = 0
        self.crop_rect = (0, 0, 960, 540)
        self.target_fps = 60

        self.tcp_sock: Optional[socket.socket] = None
        self.udp_video_sock: Optional[socket.socket] = None
        self.udp_input_sock: Optional[socket.socket] = None

        self.reassembler = VideoFrameReassembler()
        self.decoder = VideoDecoder()
        self.input_reader: Optional[ClientInputReader] = None

        self.latest_frame: Optional[np.ndarray] = None
        self.stats = {"fps": 0, "decode_ms": 0, "latency_ms": 0}

        self.threads = []

    def connect(self) -> bool:
        """Discovers host (if host_ip is None) and establishes TCP signaling."""
        if not self.host_ip:
            print("[Client] Searching for SplitScreenP2P Host on local Wi-Fi Direct link...")
            listener = P2PBeaconListener(timeout_sec=2.5)
            beacon_info = listener.discover()
            if beacon_info:
                self.host_ip = beacon_info["host_ip"]
                self.tcp_port = beacon_info.get("tcp_port", self.tcp_port)
                print(f"[Client] Discovered Host '{beacon_info.get('host_name')}' at {self.host_ip}!")
            else:
                # Default fallback
                self.host_ip = "127.0.0.1"
                print(f"[Client] No beacon received; falling back to {self.host_ip}")

        try:
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.connect((self.host_ip, self.tcp_port))
            print(f"[Client] Connected to Host TCP at {self.host_ip}:{self.tcp_port}")

            # Send CLIENT_HELLO
            hello_msg = {
                "type": "CLIENT_HELLO",
                "client_name": self.client_name,
                "udp_video_port": self.udp_video_port
            }
            self.tcp_sock.sendall(pack_tcp_message(hello_msg))

            # Wait for HOST_SESSION_ASSIGN
            reader = TcpStreamReader()
            while True:
                data = self.tcp_sock.recv(4096)
                if not data:
                    print("[Client] Host closed connection during handshake.")
                    return False
                msgs = reader.feed(data)
                for m in msgs:
                    if m.get("type") == "HOST_SESSION_ASSIGN":
                        self.slot_id = m["player_slot"]
                        self.crop_rect = tuple(m["crop_rect"])
                        self.target_fps = m.get("target_fps", 60)
                        self.udp_input_port = m.get("udp_input_port", self.udp_input_port)
                        print(f"[Client] Assigned Player Slot: {self.slot_id} | Crop: {self.crop_rect}")
                        self._start_streaming_threads()
                        return True
                    elif m.get("type") == "SERVER_FULL":
                        print(f"[Client] Server is full: {m.get('reason')}")
                        return False
        except Exception as e:
            print(f"[Client] Failed to connect to {self.host_ip}: {e}")
            return False

    def _start_streaming_threads(self):
        self.running = True
        self.input_reader = ClientInputReader(self.slot_id)

        # UDP Video Receiver Socket
        self.udp_video_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_video_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_video_sock.bind(("0.0.0.0", self.udp_video_port))
        try:
            self.udp_video_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
        except Exception:
            pass

        # UDP Input Sender Socket
        self.udp_input_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        t_video = threading.Thread(target=self._video_receive_loop, daemon=True)
        t_input = threading.Thread(target=self._input_send_loop, daemon=True)

        self.threads.extend([t_video, t_input])
        for t in self.threads:
            t.start()

    def _video_receive_loop(self):
        frame_times = []
        while self.running:
            try:
                data, _ = self.udp_video_sock.recvfrom(4096)
                res = self.reassembler.add_packet(data)
                if res:
                    fid, frame_bytes, ts_us = res
                    # Decode JPEG
                    decoded = self.decoder.decode(frame_bytes)
                    if decoded is not None:
                        self.latest_frame = decoded
                        now_us = int(time.time() * 1_000_000) & 0xFFFFFFFF
                        diff_us = (now_us - ts_us) & 0xFFFFFFFF
                        self.stats["latency_ms"] = max(0.0, diff_us / 1000.0)
                        self.stats["decode_ms"] = self.decoder.last_decode_time_ms

                        now_p = time.perf_counter()
                        frame_times.append(now_p)
                        while frame_times and now_p - frame_times[0] > 1.0:
                            frame_times.pop(0)
                        self.stats["fps"] = len(frame_times)
            except Exception:
                pass

    def _input_send_loop(self):
        """Polls input and transmits to host at ~120 Hz."""
        interval = 1.0 / 120.0
        target_addr = (self.host_ip, self.udp_input_port)

        while self.running:
            t0 = time.perf_counter()
            if self.input_reader:
                pkt = self.input_reader.sample_input()
                try:
                    self.udp_input_sock.sendto(pkt, target_addr)
                except Exception:
                    pass

            elapsed = time.perf_counter() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self):
        self.running = False
        if self.tcp_sock:
            try:
                self.tcp_sock.close()
            except Exception:
                pass
        if self.udp_video_sock:
            try:
                self.udp_video_sock.close()
            except Exception:
                pass
        if self.udp_input_sock:
            try:
                self.udp_input_sock.close()
            except Exception:
                pass
        print("[Client] Stopped SplitScreenP2P Client.")
