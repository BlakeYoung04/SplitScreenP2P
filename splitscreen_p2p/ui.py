"""
SplitScreenP2P Lightweight Hardware-Accelerated UI
Built with Pygame-CE (SDL2). Provides Launcher GUI, Host Monitor, and Client Viewport.
"""

import os
import sys
import time
import pygame
import cv2
import numpy as np
from typing import Optional, Tuple
from splitscreen_p2p.network import HostServer, StreamClient
from splitscreen_p2p.capture import (
    MODE_4P_QUADRANT,
    MODE_2P_HORIZONTAL,
    MODE_2P_VERTICAL
)
from splitscreen_p2p.p2p_wifi import get_local_ip_addresses, get_wifi_direct_instructions


class AppUI:
    """Main UI application for launcher, host monitor, and client renderer."""
    def __init__(self):
        pygame.init()
        pygame.font.init()
        pygame.display.set_caption("SplitScreenP2P - Off-Grid Game Streamer")

        self.font_large = pygame.font.SysFont("Segoe UI", 28, bold=True)
        self.font_med = pygame.font.SysFont("Segoe UI", 20, bold=True)
        self.font_small = pygame.font.SysFont("Segoe UI", 16)
        self.font_mono = pygame.font.SysFont("Consolas", 14)

        self.screen_w = 1000
        self.screen_h = 650
        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()

        # UI State
        self.state = "LAUNCHER"  # "LAUNCHER", "HOST", "CLIENT"
        self.show_wifi_help = False
        self.host_server: Optional[HostServer] = None
        self.stream_client: Optional[StreamClient] = None

        # Launcher inputs
        self.input_ip = ""
        self.input_active = False
        self.selected_split_mode = MODE_4P_QUADRANT
        self.force_demo = False
        self.default_broadcast_fullscreen = False
        self.hud_visible = True
        self.fullscreen = False

    def run_launcher(self):
        """Displays interactive launcher to pick Host or Client mode."""
        running = True
        local_ips = get_local_ip_addresses()
        ip_display = ", ".join(local_ips) if local_ips else "127.0.0.1"

        while running and self.state == "LAUNCHER":
            # Layout Rectangles
            card1_rect = pygame.Rect(80, 130, 390, 420)
            btn1_rect = pygame.Rect(110, 465, 330, 55)
            chk_full_rect = pygame.Rect(110, 375, 320, 26)
            chk_demo_rect = pygame.Rect(110, 415, 260, 26)

            card2_rect = pygame.Rect(530, 130, 390, 420)
            btn2_rect = pygame.Rect(560, 465, 330, 55)
            tb_rect = pygame.Rect(560, 310, 330, 45)

            help_btn_rect = pygame.Rect(320, 580, 360, 42)

            modal_w, modal_h = 740, 510
            modal_rect = pygame.Rect(self.screen_w // 2 - modal_w // 2, self.screen_h // 2 - modal_h // 2, modal_w, modal_h)
            btn_close_help = pygame.Rect(self.screen_w // 2 - 90, modal_rect.bottom - 60, 180, 45)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    return

                elif event.type == pygame.VIDEORESIZE:
                    self.screen_w, self.screen_h = event.w, event.h
                    self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), pygame.RESIZABLE)

                elif event.type == pygame.KEYDOWN:
                    if self.show_wifi_help:
                        if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_h):
                            self.show_wifi_help = False
                    else:
                        if event.key == pygame.K_h:
                            self.show_wifi_help = True
                        elif self.input_active:
                            if event.key == pygame.K_RETURN:
                                self.start_client(self.input_ip.strip() or None)
                            elif event.key == pygame.K_BACKSPACE:
                                self.input_ip = self.input_ip[:-1]
                            elif event.key == pygame.K_ESCAPE:
                                self.input_active = False
                            elif event.key == pygame.K_v and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                                try:
                                    import ctypes
                                    u32 = ctypes.windll.user32
                                    k32 = ctypes.windll.kernel32
                                    if u32.OpenClipboard(0):
                                        h = u32.GetClipboardData(13)  # CF_UNICODETEXT
                                        if h:
                                            ptr = k32.GlobalLock(h)
                                            clip = ctypes.c_wchar_p(ptr).value
                                            k32.GlobalUnlock(h)
                                            for ch in (clip or "").strip():
                                                if ch in "0123456789.:-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_":
                                                    self.input_ip += ch
                                        u32.CloseClipboard()
                                except Exception:
                                    pass
                            else:
                                if event.unicode and event.unicode in "0123456789.:-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_":
                                    self.input_ip += event.unicode

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.show_wifi_help:
                        if btn_close_help.collidepoint(event.pos) or not modal_rect.collidepoint(event.pos):
                            self.show_wifi_help = False
                    else:
                        # Check IP input box click
                        if tb_rect.collidepoint(event.pos):
                            self.input_active = True
                        else:
                            self.input_active = False

                        # Host button
                        if btn1_rect.collidepoint(event.pos):
                            self.start_host()

                        # Client button
                        elif btn2_rect.collidepoint(event.pos):
                            self.start_client(self.input_ip.strip() or None)

                        # Fullscreen broadcast checkbox
                        elif chk_full_rect.collidepoint(event.pos):
                            self.default_broadcast_fullscreen = not self.default_broadcast_fullscreen

                        # Demo checkbox
                        elif chk_demo_rect.collidepoint(event.pos):
                            self.force_demo = not self.force_demo

                        # Help button
                        elif help_btn_rect.collidepoint(event.pos):
                            self.show_wifi_help = True

            # Draw Launcher Base UI
            self.screen.fill((18, 22, 32))  # Dark Slate Background

            # Title Header
            title_surf = self.font_large.render("SplitScreenP2P", True, (0, 220, 255))
            self.screen.blit(title_surf, (80, 40))

            subtitle_surf = self.font_small.render(
                "Off-Grid Peer-to-Peer Split-Screen Desktop Streamer & Anti-Screen-Peeking System",
                True, (170, 185, 205)
            )
            self.screen.blit(subtitle_surf, (80, 80))

            # --- CARD 1: HOST SERVER ---
            pygame.draw.rect(self.screen, (26, 32, 48), card1_rect, border_radius=12)
            pygame.draw.rect(self.screen, (40, 52, 78), card1_rect, width=2, border_radius=12)

            c1_title = self.font_med.render("Host Game Stream", True, (255, 255, 255))
            self.screen.blit(c1_title, (110, 155))

            c1_desc = self.font_small.render("Captures display, partitions viewports,", True, (160, 175, 195))
            c1_desc2 = self.font_small.render("and streams slices to connected peers.", True, (160, 175, 195))
            self.screen.blit(c1_desc, (110, 195))
            self.screen.blit(c1_desc2, (110, 220))

            ip_lbl = self.font_small.render("Your Direct IP(s):", True, (200, 200, 200))
            self.screen.blit(ip_lbl, (110, 265))
            ip_val = self.font_mono.render(ip_display, True, (0, 230, 180))
            self.screen.blit(ip_val, (110, 290))

            mode_lbl = self.font_small.render(f"Split Mode: 4-Player Quadrants", True, (200, 200, 200))
            self.screen.blit(mode_lbl, (110, 335))

            # Broadcast Fullscreen initial checkbox
            chk_f_color = (0, 220, 150) if self.default_broadcast_fullscreen else (60, 70, 90)
            pygame.draw.rect(self.screen, chk_f_color, (110, 377, 18, 18), border_radius=4)
            full_txt = self.font_small.render("Broadcast Fullscreen to all clients", True, (220, 220, 220))
            self.screen.blit(full_txt, (136, 376))

            # Demo checkbox
            chk_color = (0, 220, 150) if self.force_demo else (60, 70, 90)
            pygame.draw.rect(self.screen, chk_color, (110, 417, 18, 18), border_radius=4)
            demo_txt = self.font_small.render("Use Built-in Demo Canvas", True, (220, 220, 220))
            self.screen.blit(demo_txt, (136, 416))

            # Host Button
            pygame.draw.rect(self.screen, (0, 140, 255), btn1_rect, border_radius=8)
            btn1_txt = self.font_med.render("Start Host Server", True, (255, 255, 255))
            self.screen.blit(btn1_txt, (110 + 75, 477))

            # --- CARD 2: JOIN CLIENT ---
            pygame.draw.rect(self.screen, (26, 32, 48), card2_rect, border_radius=12)
            pygame.draw.rect(self.screen, (40, 52, 78), card2_rect, width=2, border_radius=12)

            c2_title = self.font_med.render("Join Peer Stream", True, (255, 255, 255))
            self.screen.blit(c2_title, (560, 155))

            c2_desc = self.font_small.render("Receives your assigned quadrant stream", True, (160, 175, 195))
            c2_desc2 = self.font_small.render("and forwards your gamepad to the host.", True, (160, 175, 195))
            self.screen.blit(c2_desc, (560, 195))
            self.screen.blit(c2_desc2, (560, 220))

            target_lbl = self.font_small.render("Host IP (Click below to edit or type):", True, (200, 200, 200))
            self.screen.blit(target_lbl, (560, 280))

            # IP Textbox
            tb_border = (0, 240, 255) if self.input_active else (70, 90, 120)
            tb_bg = (24, 30, 44) if self.input_active else (16, 20, 30)
            pygame.draw.rect(self.screen, tb_bg, tb_rect, border_radius=6)
            pygame.draw.rect(self.screen, tb_border, tb_rect, width=(2 if self.input_active else 1), border_radius=6)

            cursor_str = "|" if (self.input_active and int(time.time() * 2) % 2 == 0) else ""
            if self.input_ip:
                in_surf = self.font_mono.render(self.input_ip + cursor_str, True, (255, 255, 255))
            else:
                if self.input_active:
                    in_surf = self.font_mono.render(cursor_str or " ", True, (0, 240, 255))
                else:
                    in_surf = self.font_mono.render("Leave blank for Auto-Discovery...", True, (100, 120, 145))
            self.screen.blit(in_surf, (575, 322))

            hint_txt = self.font_small.render("Controller: Auto-detects Xbox, PS, or WASD", True, (140, 190, 150))
            self.screen.blit(hint_txt, (560, 385))

            # Client Button
            pygame.draw.rect(self.screen, (0, 190, 120), btn2_rect, border_radius=8)
            btn2_txt = self.font_med.render("Connect to Host", True, (255, 255, 255))
            self.screen.blit(btn2_txt, (560 + 85, 477))

            # Bottom Wi-Fi Direct Instructions Button
            pygame.draw.rect(self.screen, (32, 42, 64), help_btn_rect, border_radius=6)
            pygame.draw.rect(self.screen, (0, 180, 230), help_btn_rect, width=1, border_radius=6)
            help_txt = self.font_small.render("Press 'H' or Click for Wi-Fi Direct Setup", True, (0, 220, 255))
            self.screen.blit(help_txt, (355, 590))

            # --- MODAL: WI-FI DIRECT / OFFLINE SETUP ---
            if self.show_wifi_help:
                # Dim background
                overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 190))
                self.screen.blit(overlay, (0, 0))

                # Modal Body
                pygame.draw.rect(self.screen, (22, 28, 42), modal_rect, border_radius=14)
                pygame.draw.rect(self.screen, (0, 200, 255), modal_rect, width=2, border_radius=14)

                m_title = self.font_large.render("Off-Grid Wi-Fi Direct / Hotspot Setup", True, (0, 240, 255))
                self.screen.blit(m_title, (modal_rect.x + 30, modal_rect.y + 25))

                sub = self.font_small.render("Connect devices directly with zero external router or internet:", True, (180, 195, 215))
                self.screen.blit(sub, (modal_rect.x + 30, modal_rect.y + 65))

                # Section 1: Windows
                w_title = self.font_med.render("1. Windows Host (Instant Mobile Hotspot):", True, (255, 220, 80))
                self.screen.blit(w_title, (modal_rect.x + 30, modal_rect.y + 105))

                w_steps = [
                    "• Go to Windows Settings -> Network & Internet -> Mobile Hotspot.",
                    "• Toggle Mobile Hotspot to ON (no cellular/WAN required).",
                    "• Client computers connect directly to this Wi-Fi network.",
                    "• Default Host IP: typically 192.168.137.1 (or auto-discovered!)."
                ]
                for idx, line in enumerate(w_steps):
                    t = self.font_small.render(line, True, (210, 220, 235))
                    self.screen.blit(t, (modal_rect.x + 45, modal_rect.y + 135 + idx * 24))

                # Section 2: Linux
                l_title = self.font_med.render("2. Linux Host (NetworkManager Hotspot):", True, (80, 220, 160))
                self.screen.blit(l_title, (modal_rect.x + 30, modal_rect.y + 245))

                l_steps = [
                    "• Run: nmcli dev wifi hotspot ifname wlan0 ssid SplitP2P password splitscreen123",
                    "• Peers connect to SSID 'SplitP2P' with password 'splitscreen123'.",
                    "• Default Host IP: typically 10.42.0.1."
                ]
                for idx, line in enumerate(l_steps):
                    t = self.font_small.render(line, True, (210, 220, 235))
                    self.screen.blit(t, (modal_rect.x + 45, modal_rect.y + 275 + idx * 24))

                # Section 3: Ad-Hoc & Direct Cable
                a_title = self.font_med.render("3. Direct Ethernet Cable / Link-Local:", True, (180, 160, 255))
                self.screen.blit(a_title, (modal_rect.x + 30, modal_rect.y + 365))
                a_step = self.font_small.render("• You can also link two laptops directly via an Ethernet cable with auto IP.", True, (210, 220, 235))
                self.screen.blit(a_step, (modal_rect.x + 45, modal_rect.y + 395))

                # Close Button
                pygame.draw.rect(self.screen, (0, 140, 255), btn_close_help, border_radius=8)
                close_txt = self.font_med.render("Close [ESC]", True, (255, 255, 255))
                self.screen.blit(close_txt, (btn_close_help.x + 35, btn_close_help.y + 10))

            pygame.display.flip()
            self.clock.tick(60)

    def start_host(self):
        """Initializes and runs Host Monitor mode."""
        self.state = "HOST"
        self.host_server = HostServer(force_demo=self.force_demo, split_mode=self.selected_split_mode)
        self.host_server.broadcast_fullscreen = self.default_broadcast_fullscreen
        self.host_server.start()
        self.run_host_monitor()

    def run_host_monitor(self):
        """Renders host view with quadrant overlays and connection statistics."""
        running = True
        pygame.display.set_caption("SplitScreenP2P - Host Monitor [ACTIVE]")

        while running and self.state == "HOST":
            btn_toggle_rect = pygame.Rect(self.screen_w - 325, 14, 310, 32)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        break
                    elif event.key == pygame.K_f:
                        self.host_server.toggle_fullscreen_broadcast()
                    elif event.key == pygame.K_TAB:
                        self.hud_visible = not self.hud_visible
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if btn_toggle_rect.collidepoint(event.pos):
                        self.host_server.toggle_fullscreen_broadcast()
                elif event.type == pygame.VIDEORESIZE:
                    self.screen_w, self.screen_h = event.w, event.h
                    self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), pygame.RESIZABLE)

            frame = self.host_server.latest_full_frame
            if frame is not None:
                # Frame is BGR, convert to RGB for Pygame surface
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                fh, fw = rgb.shape[:2]
                surf = pygame.image.frombuffer(rgb.data, (fw, fh), "RGB")
                surf_scaled = pygame.transform.smoothscale(surf, (self.screen_w, self.screen_h))
                self.screen.blit(surf_scaled, (0, 0))

                # Draw Overlay Quadrant Badges
                hw, hh = self.screen_w // 2, self.screen_h // 2
                slots_info = [
                    (1, "Player 1 (Host)", (0, 0), (0, 160, 255)),
                    (2, "Player 2 (Client)", (hw, 0), (255, 60, 60)),
                    (3, "Player 3 (Client)", (0, hh), (60, 220, 80)),
                    (4, "Player 4 (Client)", (hw, hh), (255, 220, 50))
                ]

                for s_id, s_lbl, (ox, oy), s_color in slots_info:
                    status = "CONNECTED" if (s_id == 1 or s_id in self.host_server.peers) else "WAITING"
                    # Draw subtle quadrant border
                    pygame.draw.rect(self.screen, s_color, (ox, oy, hw, hh), width=2)
                    # Badge
                    badge_rect = pygame.Rect(ox + 10, oy + 10, 240, 32)
                    pygame.draw.rect(self.screen, (15, 20, 30, 200), badge_rect, border_radius=4)
                    badge_txt = self.font_small.render(f"[{status}] {s_lbl}", True, s_color)
                    self.screen.blit(badge_txt, (ox + 16, oy + 15))

            if self.hud_visible:
                # Top Header HUD
                hud_rect = pygame.Rect(10, 10, self.screen_w - 20, 40)
                pygame.draw.rect(self.screen, (10, 15, 25, 220), hud_rect, border_radius=6)
                hud_text = self.font_mono.render(
                    f"HOST ACTIVE | FPS: {self.host_server.fps_meter:.0f} | "
                    f"Peers: {len(self.host_server.peers)}/3 | "
                    f"[TAB: Hide | ESC: Exit]",
                    True, (0, 230, 180)
                )
                self.screen.blit(hud_text, (20, 22))

                # Fullscreen Broadcast Toggle Button
                is_full = self.host_server.broadcast_fullscreen
                btn_color = (235, 110, 0) if is_full else (0, 150, 100)
                pygame.draw.rect(self.screen, btn_color, btn_toggle_rect, border_radius=6)
                btn_label = "[F] FULLSCREEN BROADCAST: ON" if is_full else "[F] SPLIT-SCREEN ACTIVE"
                btn_surf = self.font_mono.render(btn_label, True, (255, 255, 255))
                self.screen.blit(btn_surf, (btn_toggle_rect.x + 12, btn_toggle_rect.y + 7))

                if is_full:
                    # Alert Banner
                    alert_rect = pygame.Rect(self.screen_w // 2 - 260, 56, 520, 28)
                    pygame.draw.rect(self.screen, (210, 40, 0, 230), alert_rect, border_radius=4)
                    alert_txt = self.font_small.render("FULLSCREEN BROADCAST: All clients see FULL display", True, (255, 255, 255))
                    self.screen.blit(alert_txt, (self.screen_w // 2 - 210, 60))

            pygame.display.flip()
            self.clock.tick(60)

        if self.host_server:
            self.host_server.stop()
            self.host_server = None

    def start_client(self, host_ip: Optional[str]):
        """Initializes and runs Client Viewport mode."""
        self.state = "CLIENT"
        self.stream_client = StreamClient(host_ip=host_ip)
        connected = self.stream_client.connect()
        if not connected:
            print("[Client] Connection failed; returning to launcher.")
            self.state = "LAUNCHER"
            return
        self.run_client_viewport()

    def run_client_viewport(self):
        """Renders client viewport containing ONLY the cropped quadrant."""
        running = True
        slot = self.stream_client.slot_id
        pygame.display.set_caption(f"SplitScreenP2P - Player {slot} Viewport [ANTI-PEEKING ACTIVE]")

        while running and self.state == "CLIENT":
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        break
                    elif event.key == pygame.K_F11:
                        self.fullscreen = not self.fullscreen
                        flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
                        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), flags)
                    elif event.key == pygame.K_TAB:
                        self.hud_visible = not self.hud_visible
                elif event.type == pygame.VIDEORESIZE:
                    if not self.fullscreen:
                        self.screen_w, self.screen_h = event.w, event.h
                        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), pygame.RESIZABLE)

            frame = self.stream_client.latest_frame
            if frame is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                fh, fw = rgb.shape[:2]
                surf = pygame.image.frombuffer(rgb.data, (fw, fh), "RGB")
                surf_scaled = pygame.transform.smoothscale(surf, (self.screen_w, self.screen_h))
                self.screen.blit(surf_scaled, (0, 0))
            else:
                self.screen.fill((10, 14, 22))
                waiting_txt = self.font_large.render("Waiting for Host Video Stream...", True, (200, 200, 200))
                self.screen.blit(waiting_txt, (self.screen_w // 2 - 200, self.screen_h // 2 - 20))

            if self.hud_visible:
                # Client Stats HUD
                hud_rect = pygame.Rect(10, 10, self.screen_w - 20, 36)
                pygame.draw.rect(self.screen, (10, 15, 25, 210), hud_rect, border_radius=6)
                stats = self.stream_client.stats
                hud_text = self.font_mono.render(
                    f"PLAYER {slot} | Stream FPS: {stats.get('fps', 0)} | "
                    f"Decode: {stats.get('decode_ms', 0):.1f}ms | Latency: {stats.get('latency_ms', 0):.1f}ms | "
                    f"Anti-Peeking: ACTIVE | [F11: Fullscreen | TAB: HUD]",
                    True, (0, 240, 255)
                )
                self.screen.blit(hud_text, (20, 18))

            pygame.display.flip()
            self.clock.tick(60)

        if self.stream_client:
            self.stream_client.stop()
            self.stream_client = None


def run_app():
    """Main UI entrypoint."""
    ui = AppUI()
    ui.run_launcher()
    pygame.quit()
