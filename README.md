# SplitScreenP2P

> **Off-Grid Peer-to-Peer Split-Screen Desktop Streamer & Anti-Screen-Peeking System**  
> *Developed for Network Application Design Course Project*

---

## 🎮 Overview

**SplitScreenP2P** solves two fundamental issues with local multiplayer gaming:
1. **Screen Peeking / Cheating**: In tactical split-screen titles, players easily glance at each other's viewports. SplitScreenP2P captures the host screen, crops **only** the designated player quadrant, and streams that sub-screen to the client.
2. **Router & Internet Dependence**: It functions **completely off-grid** over direct Wi-Fi links (Wi-Fi Direct / Local Hotspot / Ad-Hoc) without requiring any external router or internet connectivity.

Furthermore, remote clients' physical controllers (Xbox, PlayStation, Switch, or WASD keyboard) are streamed back to the host at 120 Hz and injected as independent virtual Xbox 360 controllers via the **ViGEmBus** kernel driver.

```
       +-------------------------------------------------------------+
       |                         Host Machine                        |
       |  +-------------------------------------------------------+  |
       |  |  DirectX / PipeWire Screen Capture (1920x1080 60 FPS)  |  |
       |  +-------------------------------------------------------+  |
       |                             |                               |
       |                 Crop Engine / Slicer                        |
       |         +------------+---------------+------------+         |
       |         |            |               |            |         |
       |     [Player 1]   [Player 2]      [Player 3]   [Player 4]    |
       |       Local       Crop Q2         Crop Q3      Crop Q4      |
       +---------|------------|---------------|------------|---------+
                 |            | (UDP 50001)   | (UDP)      | (UDP)
                 |            v               v            v
           [Local Monitor] [Client 1]      [Client 2]   [Client 3]
                              ^
                              | (UDP 50002 Gamepad Telemetry @ 120Hz)
                              +-- ViGEmBus Virtual Controller Injection
```

---

## ✨ Features

- **Sub-Quadrant Slicing**: Streams only 25% of the total pixel canvas per client, drastically reducing bandwidth and decode load.
- **Ultra-Low Latency Protocol**:
  - **TCP (Port 50000)**: Session negotiation, dynamic crop geometry, and sync.
  - **UDP (Port 50001)**: MTU-safe fragmented video streaming with anti-jitter frame flush.
  - **UDP (Port 50002)**: Low-latency 24-byte gamepad telemetry at 120–250 Hz.
  - **UDP (Port 50003)**: Discovery beacon for zero-configuration host connection.
- **Hardware Virtual Controller Injection**: Seamless ViGEmBus driver integration turns client inputs into authentic Xbox 360 gamepads.
- **Built-in Interactive Synthetic Demo Canvas**: An animated 4-player split-screen arena to test and demo the system anywhere without needing an active video game.
- **Lightweight & Self-Contained**: Single `.exe` Windows binary (no external DLLs required) and sandbox-ready Linux Flatpak.

---

## 🚀 Quick Start

### Running the Pre-Compiled Windows Executable
The compiled standalone executable is located in `dist/SplitScreenP2P.exe`.
```powershell
# Launch interactive GUI launcher
.\dist\SplitScreenP2P.exe

# Or start directly in Host mode with demo canvas:
.\dist\SplitScreenP2P.exe --host --demo

# Or join as client (auto-discovers host on Wi-Fi Direct):
.\dist\SplitScreenP2P.exe --client

# Run self-test suite:
.\dist\SplitScreenP2P.exe --test
```

### Running from Source
```powershell
# Setup virtual environment
uv venv .venv
.\.venv\Scripts\python.exe -m pip install -e .

# Launch application
.\.venv\Scripts\python.exe -m splitscreen_p2p
```

---

## 📡 Off-Grid Wi-Fi Direct / Hotspot Setup

SplitScreenP2P requires **no router and no internet**:

### Windows Host:
1. Open **Settings -> Network & Internet -> Mobile Hotspot** and switch it **ON**.
2. Connect peer devices directly to the hotspot Wi-Fi network.
3. The Host IP is typically `192.168.137.1` (the client will also auto-discover it via UDP beacon).

### Linux Host:
```bash
nmcli dev wifi hotspot ifname wlan0 ssid SplitP2P password splitscreen123
```

---

## 📦 Packaging

### 1. Windows Standalone Executable (.exe)
```powershell
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --onefile --paths . --name SplitScreenP2P --add-binary "splitscreen_p2p\ViGEmClient.dll;splitscreen_p2p" --add-binary "splitscreen_p2p\ViGEmClient.dll;." splitscreen_p2p\main.py
```
Output: `dist/SplitScreenP2P.exe` (Self-contained, includes embedded `ViGEmClient.dll`).

### 2. Linux Flatpak (.flatpak)
```bash
chmod +x packaging/build_flatpak.sh
./packaging/build_flatpak.sh
```
Output: `SplitScreenP2P.flatpak`.

---

## 📑 Course Submission Documents

- **Phase 1 Approval Document**: [docs/phase1_project_topic_approval.md](docs/phase1_project_topic_approval.md)
- **Phase 2 Design Report**: [docs/phase2_design_report.md](docs/phase2_design_report.md)
- **Architecture & Implementation Plan**: [Implementation Plan Artifact](../../../brain/39726c17-1375-4b74-8c06-4863cc24d5e9/split_screen_p2p_plan.md)
