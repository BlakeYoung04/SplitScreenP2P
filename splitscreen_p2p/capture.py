"""
SplitScreenP2P Capture and Cropping Engine
Supports live screen capture (DXCam / MSS / Pillow) and a built-in
interactive synthetic split-screen game canvas for zero-dependency demos and tests.
"""

import time
import math
import numpy as np
import cv2
from typing import Tuple, Optional, Dict, Any

# Crop mode presets
MODE_2P_HORIZONTAL = "2P_HORIZONTAL"
MODE_2P_VERTICAL = "2P_VERTICAL"
MODE_4P_QUADRANT = "4P_QUADRANT"
MODE_CUSTOM = "CUSTOM"


def compute_crop_rect(mode: str, slot_id: int, total_w: int, total_h: int) -> Tuple[int, int, int, int]:
    """
    Computes (x, y, w, h) for a given player slot (1 to 4).
    """
    half_w = total_w // 2
    half_h = total_h // 2

    if mode == MODE_2P_HORIZONTAL:
        if slot_id == 1:
            return 0, 0, total_w, half_h
        else:
            return 0, half_h, total_w, half_h

    elif mode == MODE_2P_VERTICAL:
        if slot_id == 1:
            return 0, 0, half_w, total_h
        else:
            return half_w, 0, half_w, total_h

    elif mode == MODE_4P_QUADRANT:
        if slot_id == 1:  # Top-Left
            return 0, 0, half_w, half_h
        elif slot_id == 2:  # Top-Right
            return half_w, 0, half_w, half_h
        elif slot_id == 3:  # Bottom-Left
            return 0, half_h, half_w, half_h
        else:  # Bottom-Right (Slot 4)
            return half_w, half_h, half_w, half_h

    # Default fallback full screen
    return 0, 0, total_w, total_h


class SyntheticGameCanvas:
    """
    Simulated 4-Player 3D/2D split-screen game arena.
    Renders 4 distinct quadrants with moving avatars, targets, HUDs, and timestamps.
    Responds to live remote controller inputs so players can play immediately!
    """
    def __init__(self, width: int = 1920, height: int = 1080):
        self.width = width
        self.height = height
        self.half_w = width // 2
        self.half_h = height // 2

        # Positions and angles for 4 players
        self.players = {
            1: {"x": 200, "y": 200, "vx": 0, "vy": 0, "color": (230, 90, 50), "name": "P1 (Host)", "score": 10},
            2: {"x": 200, "y": 200, "vx": 0, "vy": 0, "color": (50, 90, 240), "name": "P2 (Client)", "score": 15},
            3: {"x": 200, "y": 200, "vx": 0, "vy": 0, "color": (50, 200, 70), "name": "P3 (Client)", "score": 8},
            4: {"x": 200, "y": 200, "vx": 0, "vy": 0, "color": (230, 210, 40), "name": "P4 (Client)", "score": 12},
        }
        self.start_time = time.time()
        self.frame_counter = 0

    def update_player_input(self, slot_id: int, lx: float, ly: float, btn_a: bool):
        """Update player avatar dynamics from gamepad stick and buttons."""
        if slot_id in self.players:
            p = self.players[slot_id]
            speed = 8.0
            p["vx"] = (lx / 32768.0) * speed
            p["vy"] = (ly / 32768.0) * speed
            if btn_a:
                p["score"] += 1

    def render(self) -> np.ndarray:
        """Render the complete 1920x1080 split-screen canvas."""
        self.frame_counter += 1
        now = time.time()
        elapsed = now - self.start_time

        canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        quadrant_offsets = {
            1: (0, 0),
            2: (self.half_w, 0),
            3: (0, self.half_h),
            4: (self.half_w, self.half_h),
        }

        bg_tints = {
            1: (20, 25, 45),
            2: (45, 20, 25),
            3: (20, 45, 25),
            4: (40, 40, 20)
        }

        # Render each quadrant independently
        for slot, (ox, oy) in quadrant_offsets.items():
            p = self.players[slot]

            # Background fill
            canvas[oy:oy+self.half_h, ox:ox+self.half_w] = bg_tints[slot]

            # Dynamic target ball moving in each screen
            ball_x = int(ox + self.half_w / 2 + math.cos(elapsed * 2 + slot) * (self.half_w * 0.35))
            ball_y = int(oy + self.half_h / 2 + math.sin(elapsed * 2.5 + slot) * (self.half_h * 0.35))
            cv2.circle(canvas, (ball_x, ball_y), 22, (255, 255, 255), -1)
            cv2.circle(canvas, (ball_x, ball_y), 24, p["color"], 3)

            # Update player avatar position
            # Auto-roam slightly if no input
            if abs(p["vx"]) < 0.1 and abs(p["vy"]) < 0.1:
                auto_vx = math.sin(elapsed * 1.5 + slot * 1.7) * 3
                auto_vy = math.cos(elapsed * 1.3 + slot * 1.2) * 3
                p["x"] += auto_vx
                p["y"] += auto_vy
            else:
                p["x"] += p["vx"]
                p["y"] += p["vy"]

            # Clamp inside quadrant
            p["x"] = max(40, min(self.half_w - 40, p["x"]))
            p["y"] = max(40, min(self.half_h - 40, p["y"]))

            px = int(ox + p["x"])
            py = int(oy + p["y"])

            # Draw player avatar (triangle ship)
            cv2.circle(canvas, (px, py), 26, p["color"], -1)
            cv2.circle(canvas, (px, py), 28, (255, 255, 255), 2)
            cv2.putText(canvas, f"P{slot}", (px - 14, py + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

            # Draw HUD
            hud_y = oy + 35
            cv2.putText(canvas, f"PLAYER {slot} VIEW [{p['name']}]", (ox + 20, hud_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (240, 240, 240), 2)
            cv2.putText(canvas, f"Score: {p['score']} | Frame: {self.frame_counter}", (ox + 20, hud_y + 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 220, 180), 1)

            # High precision latency timer
            ts_text = f"Host Time: {now:.3f} s"
            cv2.putText(canvas, ts_text, (ox + 20, oy + self.half_h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 200, 255), 1)

            # Anti-peeking warning watermark
            cv2.putText(canvas, "ANTI-PEEKING ENABLED (CONFIDENTIAL STREAM)", (ox + self.half_w - 420, oy + self.half_h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 100, 100), 1)

        # Draw cross separator lines
        cv2.line(canvas, (self.half_w, 0), (self.half_w, self.height), (255, 255, 0), 3)
        cv2.line(canvas, (0, self.half_h), (self.width, self.half_h), (255, 255, 0), 3)

        return canvas


class ScreenCaptureEngine:
    """
    Unified capture interface with automatic fallback:
    DXCam -> MSS -> Pillow -> SyntheticGameCanvas.
    """
    def __init__(self, force_demo: bool = False):
        self.force_demo = force_demo
        self.synthetic = SyntheticGameCanvas(1920, 1080)
        self.dxcam_inst = None
        self.mss_inst = None
        self.backend_name = "Synthetic"
        self.last_captured_frame: Optional[np.ndarray] = None
        self.has_desktop_capture = False

        if not force_demo:
            # Try initializing DXCam
            try:
                import dxcam
                self.dxcam_inst = dxcam.create(output_idx=0)
                if self.dxcam_inst:
                    self.backend_name = "DXCam (DirectX DXGI)"
            except Exception:
                self.dxcam_inst = None

            # Try MSS fallback
            if self.dxcam_inst is None:
                try:
                    import mss
                    self.mss_inst = mss.MSS()
                    self.backend_name = "MSS (Desktop GDI)"
                except Exception:
                    self.mss_inst = None

    def grab_full_frame(self) -> np.ndarray:
        """Captures full screen or returns synthetic canvas."""
        if self.force_demo:
            return self.synthetic.render()

        if self.dxcam_inst:
            try:
                frame = self.dxcam_inst.grab()
                if frame is not None:
                    # DXCam returns RGB, convert to BGR for OpenCV
                    bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    self.last_captured_frame = bgr
                    self.has_desktop_capture = True
                    return bgr
                elif self.last_captured_frame is not None:
                    # Screen did not change; reuse cached frame to avoid flickering
                    return self.last_captured_frame
            except Exception:
                pass

        if self.mss_inst:
            try:
                monitor = self.mss_inst.monitors[1]
                sct_img = self.mss_inst.grab(monitor)
                frame = np.array(sct_img)
                bgr = frame[:, :, :3]  # BGRA -> BGR
                self.last_captured_frame = bgr
                self.has_desktop_capture = True
                return bgr
            except Exception:
                pass

        # If desktop frame was previously captured, keep using it (never flicker)
        if self.last_captured_frame is not None:
            return self.last_captured_frame

        # Fallback only when capture is completely unavailable
        return self.synthetic.render()

    def grab_cropped(self, crop_rect: Tuple[int, int, int, int]) -> np.ndarray:
        """Captures full frame and extracts the sub-rectangle."""
        full = self.grab_full_frame()
        x, y, w, h = crop_rect
        fh, fw = full.shape[:2]

        # Clamp boundaries
        x = max(0, min(fw - 1, x))
        y = max(0, min(fh - 1, y))
        w = max(1, min(fw - x, w))
        h = max(1, min(fh - y, h))

        return full[y:y+h, x:x+w]
