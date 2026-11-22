"""
SplitScreenP2P Low-Latency Video Encoder and Decoder
Uses hardware/optimized JPEG encoding with packet fragmentation.
"""

import time
import cv2
import numpy as np
from typing import List, Tuple, Optional
from splitscreen_p2p.protocol import (
    pack_video_packet,
    MAX_UDP_PAYLOAD,
    VideoFlags
)


class VideoEncoder:
    """Encodes BGR frames into compressed JPEG slices and fragments them into UDP packets."""
    def __init__(self, quality: int = 75, target_resolution: Optional[Tuple[int, int]] = None):
        self.quality = quality
        self.target_resolution = target_resolution
        self.encode_params = [
            int(cv2.IMWRITE_JPEG_QUALITY), self.quality,
            int(cv2.IMWRITE_JPEG_OPTIMIZE), 0,  # Disable multi-pass optimization for speed
        ]
        self.frame_counter = 0

    def encode_and_fragment(
        self,
        frame: np.ndarray,
        slot_id: int
    ) -> Tuple[int, List[bytes], float]:
        """
        Encodes frame slice and returns (frame_id, list_of_udp_packets, encode_time_ms).
        """
        t0 = time.perf_counter()
        self.frame_counter += 1
        frame_id = self.frame_counter

        # Optional downscale if client requested smaller resolution
        if self.target_resolution:
            tw, th = self.target_resolution
            if frame.shape[1] != tw or frame.shape[0] != th:
                frame = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_LINEAR)

        success, encoded = cv2.imencode(".jpg", frame, self.encode_params)
        if not success:
            return frame_id, [], 0.0

        raw_bytes = encoded.tobytes()
        t1 = time.perf_counter()
        encode_time_ms = (t1 - t0) * 1000.0

        # Fragment into MTU chunks
        total_len = len(raw_bytes)
        chunk_size = MAX_UDP_PAYLOAD
        packet_count = (total_len + chunk_size - 1) // chunk_size
        ts_us = int((time.time() * 1_000_000)) & 0xFFFFFFFF

        packets = []
        for idx in range(packet_count):
            start = idx * chunk_size
            end = min(start + chunk_size, total_len)
            chunk = raw_bytes[start:end]

            flags = 0
            if idx == 0:
                flags |= VideoFlags.KEYFRAME
            if idx == packet_count - 1:
                flags |= VideoFlags.LAST_PACKET

            pkt = pack_video_packet(
                slot_id=slot_id,
                flags=flags,
                frame_id=frame_id,
                packet_index=idx,
                packet_count=packet_count,
                timestamp_us=ts_us,
                payload=chunk
            )
            packets.append(pkt)

        return frame_id, packets, encode_time_ms


class VideoDecoder:
    """Decodes compressed image bytes received over UDP into renderable BGR frames."""
    def __init__(self):
        self.last_decode_time_ms = 0.0

    def decode(self, raw_bytes: bytes) -> Optional[np.ndarray]:
        """Decodes raw JPEG byte buffer into numpy array."""
        t0 = time.perf_counter()
        arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        t1 = time.perf_counter()
        if frame is not None:
            self.last_decode_time_ms = (t1 - t0) * 1000.0
        return frame
