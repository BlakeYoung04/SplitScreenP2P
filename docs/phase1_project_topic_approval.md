# Phase 1: Project Topic Approval Request

**Project Title:** SplitScreenP2P: Off-Grid Peer-to-Peer Split-Screen Desktop Streaming & Controller Forwarding System  
**Group Members:** [Member 1], [Member 2], [Member 3], [Member 4]  
**Course:** Network Application Design  
**Date:** November 2026  

---

## 1. Project Background and Motivation
Local split-screen multiplayer gaming has historically offered some of the most engaging cooperative and competitive experiences. However, traditional local split-screen suffers from two critical flaws:
1. **Screen Peeking / Screen Cheating:** In competitive games (first-person shooters, tactical games, racing), players can easily glance at opponents' split quadrants to discover locations, strategies, and resources.
2. **Display Space & Mobility Limits:** Multiple players are crowded around a single monitor or TV, and participants outside of Wi-Fi router range or at outdoor/LAN gatherings cannot play together.

Traditional game streaming solutions (like Steam Remote Play or Moonlight) stream the *entire* display canvas, which leaks the opponent's view and wastes massive bandwidth transmitting unneeded pixels.

## 2. Project Goals & Proposed Solution
**SplitScreenP2P** is an off-grid, low-latency peer-to-peer network application composed of a host server and lightweight clients:
- **Quadrant Screen Slicing:** The host application captures the display in real-time, extracts only the designated viewport rectangle (e.g. Player 2's quadrant), encodes it, and streams only that sub-screen to the corresponding peer.
- **Bandwidth Reduction:** By sending only $1/2$ or $1/4$ of the screen resolution to each client, network overhead and decode latency drop significantly.
- **Off-Grid P2P Networking (Wi-Fi Direct / Local Ad-Hoc):** The system operates entirely without an internet connection or external Wi-Fi router. Nodes communicate via direct wireless links (Wi-Fi Direct / SoftAP link-local networking).
- **Bidirectional Input Forwarding:** Clients capture local physical gamepad inputs and stream telemetry back to the host via low-latency datagrams, where the host injects them as virtual controllers (via virtual bus drivers like ViGEmBus on Windows or uinput on Linux).

## 3. Communication Model & Network Architecture
The application employs a hybrid transport architecture to optimize both reliability and responsiveness:
1. **TCP Control Channel (Port 50000):** Used for connection handshake, display geometry negotiation (crop rectangle $X, Y, W, H$), codec negotiation, session lifecycle, and synchronization heartbeats.
2. **UDP Media Transport (Port 50001):** High-throughput, low-latency video streaming using MTU-bounded custom framed datagrams. Frames are delivered with minimal buffering; out-of-order or late frames are dropped in favor of the latest frame to prevent latency accumulation.
3. **UDP Peripheral Telemetry (Port 50002):** High-frequency (120–250 Hz) client-to-host controller state datagrams (button bitmasks, analog trigger/stick values) with sequence numbering for jitter resistance.

## 4. Platform & Implementation Plan (Extra Credit Objective)
To achieve the 3-point extra credit implementation demo:
- **Server Platform:** Windows (DirectX DXGI Desktop Duplication API + hardware/software low-latency encoding).
- **Client Platforms:** Windows standalone executable (`.exe`) and Linux sandboxed application (`Flatpak`).
- **Input Emulation:** Virtual gamepad injection into host games.
- **Evaluation Metrics:** Measure network glass-to-glass latency, packet loss resilience over Wi-Fi Direct, and CPU/bandwidth consumption comparisons against full-screen streaming.
