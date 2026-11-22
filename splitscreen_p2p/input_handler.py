"""
SplitScreenP2P Input Handler and Virtual Controller Dispatcher
Handles client-side controller/keyboard capture and host-side virtual controller emulation.
"""

import os
import sys
import time
import ctypes
from typing import Dict, Any, Optional
import pygame
from splitscreen_p2p.protocol import (
    GamepadButtons,
    pack_gamepad_packet,
    unpack_gamepad_packet
)


class XUSBReport(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class ViGEmControllerManager:
    """
    Interfaces with ViGEmClient.dll to spawn real virtual Xbox 360 controllers
    in Windows for connected remote players.
    """
    def __init__(self):
        self.available = False
        self.client = None
        self.targets: Dict[int, Any] = {}
        self.vigem = None

        if sys.platform != "win32":
            return

        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
        dll_path = os.path.join(base_dir, "ViGEmClient.dll")
        if not os.path.exists(dll_path):
            dll_path = os.path.join(base_dir, "splitscreen_p2p", "ViGEmClient.dll")
        if not os.path.exists(dll_path):
            dll_path = "ViGEmClient.dll"

        try:
            self.vigem = ctypes.cdll.LoadLibrary(dll_path)
            self._setup_function_signatures()
            self.client = self.vigem.vigem_alloc()
            ret = self.vigem.vigem_connect(self.client)
            if ret == 0x20000000:  # VIGEM_ERROR_NONE
                self.available = True
                print("[HostInput] ViGEmBus driver connected: Virtual Xbox 360 injection active!")
            else:
                print(f"[HostInput] ViGEm connection returned code: {hex(ret)}")
        except Exception as e:
            print(f"[HostInput] ViGEm unavailable ({e}); using virtual input fallback.")

    def _setup_function_signatures(self):
        v = self.vigem
        v.vigem_alloc.restype = ctypes.c_void_p
        v.vigem_free.argtypes = [ctypes.c_void_p]
        v.vigem_connect.argtypes = [ctypes.c_void_p]
        v.vigem_connect.restype = ctypes.c_uint32
        v.vigem_disconnect.argtypes = [ctypes.c_void_p]

        v.vigem_target_x360_alloc.restype = ctypes.c_void_p
        v.vigem_target_add.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        v.vigem_target_add.restype = ctypes.c_uint32

        v.vigem_target_remove.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        v.vigem_target_free.argtypes = [ctypes.c_void_p]

        v.vigem_target_x360_update.argtypes = [ctypes.c_void_p, ctypes.c_void_p, XUSBReport]
        v.vigem_target_x360_update.restype = ctypes.c_uint32

    def create_controller_for_slot(self, slot_id: int):
        """Spawns an emulated Xbox 360 controller on the host system."""
        if not self.available or slot_id in self.targets:
            return
        target = self.vigem.vigem_target_x360_alloc()
        ret = self.vigem.vigem_target_add(self.client, target)
        if ret == 0x20000000:
            self.targets[slot_id] = target
            print(f"[HostInput] Virtual Xbox 360 controller spawned for Player Slot {slot_id}!")
        else:
            print(f"[HostInput] Failed to add virtual target for slot {slot_id}: {hex(ret)}")
            self.vigem.vigem_target_free(target)

    def update_controller(self, slot_id: int, buttons: int, l_trig: int, r_trig: int,
                          lx: int, ly: int, rx: int, ry: int):
        """Dispatches controller state directly to the virtual Xbox 360 hardware bus."""
        if not self.available:
            return

        target = self.targets.get(slot_id)
        if not target:
            self.create_controller_for_slot(slot_id)
            target = self.targets.get(slot_id)
            if not target:
                return

        report = XUSBReport()
        report.wButtons = buttons & 0xFFFF
        report.bLeftTrigger = l_trig & 0xFF
        report.bRightTrigger = r_trig & 0xFF
        report.sThumbLX = int(lx)
        # Note: Invert Y for XInput standard (up is positive)
        report.sThumbLY = int(-ly)
        report.sThumbRX = int(rx)
        report.sThumbRY = int(-ry)

        self.vigem.vigem_target_x360_update(self.client, target, report)

    def close(self):
        """Cleans up all virtual targets and disconnects from driver."""
        if not self.available or not self.client:
            return
        for slot_id, target in list(self.targets.items()):
            try:
                self.vigem.vigem_target_remove(self.client, target)
                self.vigem.vigem_target_free(target)
            except Exception:
                pass
        self.targets.clear()
        try:
            self.vigem.vigem_disconnect(self.client)
            self.vigem.vigem_free(self.client)
        except Exception:
            pass
        self.available = False

HostInputDispatcher = ViGEmControllerManager


class ClientInputReader:
    """Reads local physical gamepad or falls back to keyboard emulation."""
    def __init__(self, slot_id: int):
        self.slot_id = slot_id
        self.seq = 0
        self.joystick = None
        self._init_joystick()

    def _init_joystick(self):
        try:
            if not pygame.get_init():
                pygame.init()
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            if pygame.joystick.get_count() > 0:
                self.joystick = pygame.joystick.Joystick(0)
                self.joystick.init()
                print(f"[ClientInput] Connected physical gamepad: {self.joystick.get_name()}")
        except Exception as e:
            print(f"[ClientInput] Joystick init notice: {e}")

    def sample_input(self) -> bytes:
        """Polls current hardware controller / keyboard and returns a 24-byte GamepadPacket."""
        self.seq = (self.seq + 1) % 256
        buttons = 0
        l_trig = 0
        r_trig = 0
        lx = 0
        ly = 0
        rx = 0
        ry = 0

        # Check physical gamepad first
        if self.joystick and self.joystick.get_init():
            try:
                # Standard SDL gamepad mapping
                num_axes = self.joystick.get_numaxes()
                if num_axes >= 2:
                    lx = int(self.joystick.get_axis(0) * 32767)
                    ly = int(self.joystick.get_axis(1) * 32767)
                if num_axes >= 4:
                    rx = int(self.joystick.get_axis(2) * 32767)
                    ry = int(self.joystick.get_axis(3) * 32767)
                if num_axes >= 6:
                    # Triggers: -1.0 to 1.0 -> 0 to 255
                    l_val = self.joystick.get_axis(4)
                    r_val = self.joystick.get_axis(5)
                    l_trig = int(max(0, (l_val + 1.0) * 127.5))
                    r_trig = int(max(0, (r_val + 1.0) * 127.5))

                num_btns = self.joystick.get_numbuttons()
                mapping = [
                    (0, GamepadButtons.A),
                    (1, GamepadButtons.B),
                    (2, GamepadButtons.X),
                    (3, GamepadButtons.Y),
                    (4, GamepadButtons.LB),
                    (5, GamepadButtons.RB),
                    (6, GamepadButtons.BACK),
                    (7, GamepadButtons.START),
                    (8, GamepadButtons.GUIDE),
                    (9, GamepadButtons.L_THUMB),
                    (10, GamepadButtons.R_THUMB),
                ]
                for btn_idx, mask in mapping:
                    if btn_idx < num_btns and self.joystick.get_button(btn_idx):
                        buttons |= mask
            except Exception:
                pass

        # Also blend keyboard keys (WASD + Space + Enter + Arrows)
        keys = pygame.key.get_pressed()
        if keys[pygame.K_w]:
            ly = -32000
        elif keys[pygame.K_s]:
            ly = 32000
        if keys[pygame.K_a]:
            lx = -32000
        elif keys[pygame.K_d]:
            lx = 32000

        if keys[pygame.K_UP]:
            ry = -32000
        elif keys[pygame.K_DOWN]:
            ry = 32000
        if keys[pygame.K_LEFT]:
            rx = -32000
        elif keys[pygame.K_RIGHT]:
            rx = 32000

        if keys[pygame.K_SPACE]:
            buttons |= GamepadButtons.A
        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
            buttons |= GamepadButtons.B
        if keys[pygame.K_e]:
            buttons |= GamepadButtons.X
        if keys[pygame.K_q]:
            buttons |= GamepadButtons.Y
        if keys[pygame.K_RETURN]:
            buttons |= GamepadButtons.START
        if keys[pygame.K_ESCAPE]:
            buttons |= GamepadButtons.BACK

        ts_us = int(time.time() * 1_000_000)
        return pack_gamepad_packet(
            slot_id=self.slot_id,
            seq=self.seq,
            buttons=buttons,
            left_trigger=l_trig,
            right_trigger=r_trig,
            thumb_lx=lx,
            thumb_ly=ly,
            thumb_rx=rx,
            thumb_ry=ry,
            client_time_us=ts_us
        )


# Alias for clean architecture naming
HostInputDispatcher = ViGEmControllerManager

