"""
Integration test for SplitScreenP2P: Host, Client, Video Streaming, and Gamepad Input.
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from splitscreen_p2p.network import HostServer, StreamClient

def test_streaming():
    print("--- Starting End-to-End P2P Streaming Test ---")
    host = HostServer(force_demo=True, target_fps=30)
    host.start()
    time.sleep(0.4)

    client = StreamClient(host_ip="127.0.0.1")
    connected = client.connect()
    assert connected, "Client failed to connect to host"
    print(f"Client connected! Slot: {client.slot_id}, Crop: {client.crop_rect}")

    # Allow frames and input packets to flow
    time.sleep(1.5)

    assert client.latest_frame is not None, "Client received no frames"
    print(f"Client latest frame shape: {client.latest_frame.shape}")
    print(f"Client stats: FPS={client.stats['fps']}, Decode={client.stats['decode_ms']:.2f}ms, Latency={client.stats['latency_ms']:.2f}ms")
    print(f"Host peer frames sent: {host.peers[client.slot_id].stats['frames_sent']}")

    assert host.peers[client.slot_id].stats['frames_sent'] > 10, "Host did not send enough frames"
    assert client.latest_frame.shape == (540, 960, 3), f"Unexpected frame shape {client.latest_frame.shape}"

    client.stop()
    host.stop()
    print("--- End-to-End P2P Streaming Test PASSED! ---")

if __name__ == "__main__":
    test_streaming()
