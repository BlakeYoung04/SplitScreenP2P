"""
SplitScreenP2P Protocol Definitions
Defines wire formats, serialization, packet fragmentation, and reassembly.
"""

import struct
import json
import time
from typing import Optional, Tuple, Dict, Any, List

# Magic Identifiers
VIDEO_MAGIC = 0x5350      # "SP" (SplitP2P Video)
GAMEPAD_MAGIC = 0x4750    # "GP" (GamePad Input)
BEACON_MAGIC = b"SPBC"    # "SPBC" (SplitP2P Beacon Discovery)

# Default Ports
DEFAULT_TCP_PORT = 50000
DEFAULT_UDP_VIDEO_PORT = 50001
DEFAULT_UDP_INPUT_PORT = 50002
DEFAULT_BEACON_PORT = 50003

# MTU safe payload limit (Ethernet MTU 1500 - IP 20 - UDP 8 - Header 16 = 1456; keep at 1350)
MAX_UDP_PAYLOAD = 1350

# Video Header Struct: 
# uint16 magic, uint8 slot, uint8 flags, uint32 frame_id, uint16 pkt_idx, uint16 pkt_cnt, uint32 timestamp_us
# Size: 2 + 1 + 1 + 4 + 2 + 2 + 4 = 16 bytes
VIDEO_HEADER_FORMAT = "!HBBIIHHI"
VIDEO_HEADER_SIZE = struct.calcsize(VIDEO_HEADER_FORMAT)
# Notice: ! = network big endian.
# Let's verify field mapping:
# H: magic (uint16)
# B: slot_id (uint8)
# B: flags (uint8)
# I: frame_id (uint32)
# H: packet_index (uint16)
# H: packet_count (uint16)
# I: timestamp_us (uint32)
# struct format: "!HBB I H H I" -> 2 + 1 + 1 + 4 + 2 + 2 + 4 = 16 bytes!
VIDEO_HEADER_FORMAT = "!HBB I H H I"
VIDEO_HEADER_SIZE = struct.calcsize(VIDEO_HEADER_FORMAT)

# Gamepad Header Struct:
# uint16 magic, uint8 slot, uint8 seq, uint16 buttons, uint8 l_trig, uint8 r_trig,
# int16 lx, int16 ly, int16 rx, int16 ry, uint64 client_time_us
# Size: 2 + 1 + 1 + 2 + 1 + 1 + 2 + 2 + 2 + 2 + 8 = 24 bytes
GAMEPAD_HEADER_FORMAT = "!HBBHBBhhhhQ"
GAMEPAD_HEADER_SIZE = struct.calcsize(GAMEPAD_HEADER_FORMAT)

# Gamepad Button Bitmask Flags
class GamepadButtons:
    A = 1 << 0
    B = 1 << 1
    X = 1 << 2
    Y = 1 << 3
    LB = 1 << 4
    RB = 1 << 5
    BACK = 1 << 6
    START = 1 << 7
    GUIDE = 1 << 8
    L_THUMB = 1 << 9
    R_THUMB = 1 << 10
    DPAD_UP = 1 << 11
    DPAD_DOWN = 1 << 12
    DPAD_LEFT = 1 << 13
    DPAD_RIGHT = 1 << 14

class VideoFlags:
    KEYFRAME = 1 << 0
    LAST_PACKET = 1 << 1


def pack_video_packet(
    slot_id: int,
    flags: int,
    frame_id: int,
    packet_index: int,
    packet_count: int,
    timestamp_us: int,
    payload: bytes
) -> bytes:
    """Serialize a single video frame fragment."""
    header = struct.pack(
        VIDEO_HEADER_FORMAT,
        VIDEO_MAGIC,
        slot_id & 0xFF,
        flags & 0xFF,
        frame_id & 0xFFFFFFFF,
        packet_index & 0xFFFF,
        packet_count & 0xFFFF,
        timestamp_us & 0xFFFFFFFF
    )
    return header + payload


def unpack_video_packet(data: bytes) -> Optional[Tuple[int, int, int, int, int, int, bytes]]:
    """
    Unpack video packet.
    Returns: (slot_id, flags, frame_id, packet_index, packet_count, timestamp_us, payload)
    """
    if len(data) < VIDEO_HEADER_SIZE:
        return None
    magic, slot_id, flags, frame_id, pkt_idx, pkt_cnt, ts_us = struct.unpack_from(VIDEO_HEADER_FORMAT, data, 0)
    if magic != VIDEO_MAGIC:
        return None
    payload = data[VIDEO_HEADER_SIZE:]
    return slot_id, flags, frame_id, pkt_idx, pkt_cnt, ts_us, payload


def pack_gamepad_packet(
    slot_id: int,
    seq: int,
    buttons: int,
    left_trigger: int,
    right_trigger: int,
    thumb_lx: int,
    thumb_ly: int,
    thumb_rx: int,
    thumb_ry: int,
    client_time_us: int
) -> bytes:
    """Serialize a gamepad telemetry packet (24 bytes)."""
    return struct.pack(
        GAMEPAD_HEADER_FORMAT,
        GAMEPAD_MAGIC,
        slot_id & 0xFF,
        seq & 0xFF,
        buttons & 0xFFFF,
        left_trigger & 0xFF,
        right_trigger & 0xFF,
        int(thumb_lx),
        int(thumb_ly),
        int(thumb_rx),
        int(thumb_ry),
        client_time_us
    )


def unpack_gamepad_packet(data: bytes) -> Optional[Dict[str, Any]]:
    """Unpack gamepad telemetry packet."""
    if len(data) < GAMEPAD_HEADER_SIZE:
        return None
    (magic, slot_id, seq, buttons, l_trig, r_trig,
     lx, ly, rx, ry, ts_us) = struct.unpack_from(GAMEPAD_HEADER_FORMAT, data, 0)
    if magic != GAMEPAD_MAGIC:
        return None
    return {
        "slot_id": slot_id,
        "seq": seq,
        "buttons": buttons,
        "left_trigger": l_trig,
        "right_trigger": r_trig,
        "thumb_lx": lx,
        "thumb_ly": ly,
        "thumb_rx": rx,
        "thumb_ry": ry,
        "client_time_us": ts_us
    }


def pack_tcp_message(msg: Dict[str, Any]) -> bytes:
    """Packs a length-prefixed JSON message for the TCP control channel."""
    encoded = json.dumps(msg).encode("utf-8")
    return struct.pack("!I", len(encoded)) + encoded


class TcpStreamReader:
    """Helper to parse length-prefixed TCP messages from a stream."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> List[Dict[str, Any]]:
        self.buffer.extend(data)
        messages = []
        while len(self.buffer) >= 4:
            (length,) = struct.unpack("!I", self.buffer[:4])
            if len(self.buffer) < 4 + length:
                break
            payload = self.buffer[4:4 + length]
            del self.buffer[:4 + length]
            try:
                msg = json.loads(payload.decode("utf-8"))
                messages.append(msg)
            except Exception as e:
                print(f"Error decoding TCP JSON payload: {e}")
        return messages


class VideoFrameReassembler:
    """
    Reassembles fragmented UDP video packets into full JPEG/video frames.
    Automatically discards older frames when newer frames arrive (anti-jitter, zero lag).
    """
    def __init__(self):
        self.current_frame_id = -1
        self.packet_count = 0
        self.received_packets: Dict[int, bytes] = {}
        self.frame_timestamp = 0

    def add_packet(self, data: bytes) -> Optional[Tuple[int, bytes, int]]:
        """
        Processes a UDP packet.
        If this packet completes the current frame, returns: (frame_id, complete_bytes, timestamp_us).
        Otherwise returns None.
        """
        res = unpack_video_packet(data)
        if not res:
            return None
        slot_id, flags, frame_id, pkt_idx, pkt_cnt, ts_us, payload = res

        # Drop old or obsolete frame packets
        if frame_id < self.current_frame_id:
            return None

        # If a newer frame arrived, flush incomplete old frame immediately
        if frame_id > self.current_frame_id:
            self.current_frame_id = frame_id
            self.packet_count = pkt_cnt
            self.received_packets.clear()
            self.frame_timestamp = ts_us

        self.received_packets[pkt_idx] = payload

        # Check if all packets received
        if len(self.received_packets) == self.packet_count:
            # Assemble in order
            ordered_data = bytearray()
            for idx in range(self.packet_count):
                chunk = self.received_packets.get(idx)
                if chunk is None:
                    return None
                ordered_data.extend(chunk)
            complete_frame = bytes(ordered_data)
            ret_frame_id = self.current_frame_id
            ret_ts = self.frame_timestamp
            self.received_packets.clear()
            return ret_frame_id, complete_frame, ret_ts

        return None
