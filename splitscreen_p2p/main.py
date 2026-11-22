"""
SplitScreenP2P Main Application Entry Point
Supports CLI flags or direct GUI launch.
"""

import sys
import argparse
from splitscreen_p2p.p2p_wifi import get_wifi_direct_instructions
from splitscreen_p2p.capture import MODE_4P_QUADRANT, MODE_2P_HORIZONTAL, MODE_2P_VERTICAL


def main():
    parser = argparse.ArgumentParser(
        description="SplitScreenP2P: Off-Grid Peer-to-Peer Split-Screen Desktop Streamer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  Launch GUI:           python -m splitscreen_p2p\n"
               "  Host (Interactive):   python -m splitscreen_p2p --host\n"
               "  Host (Demo Canvas):   python -m splitscreen_p2p --host --demo\n"
               "  Join Stream:          python -m splitscreen_p2p --client 192.168.137.1\n"
               "  Auto-Discover Host:   python -m splitscreen_p2p --client\n"
               "  Wi-Fi Direct Guide:   python -m splitscreen_p2p --wifi-help\n"
    )

    parser.add_argument("--host", action="store_true", help="Launch directly in Host Server mode")
    parser.add_argument("--client", nargs="?", const="", default=None,
                        help="Launch directly in Client Viewport mode (optional: pass host IP)")
    parser.add_argument("--demo", action="store_true", help="Force synthetic 4-quadrant interactive demo canvas")
    parser.add_argument("--mode", choices=[MODE_4P_QUADRANT, MODE_2P_HORIZONTAL, MODE_2P_VERTICAL],
                        default=MODE_4P_QUADRANT, help="Split-screen partition mode (default: 4P_QUADRANT)")
    parser.add_argument("--fps", type=int, default=60, help="Target streaming framerate (default: 60)")
    parser.add_argument("--wifi-help", action="store_true", help="Print step-by-step Off-Grid Wi-Fi Direct setup guide")
    parser.add_argument("--test", action="store_true", help="Execute self-test suite and exit")

    args = parser.parse_args()

    if args.wifi_help:
        print(get_wifi_direct_instructions())
        return

    if args.test:
        from tests.test_integration import test_streaming
        test_streaming()
        return

    from splitscreen_p2p.ui import AppUI

    ui = AppUI()
    if args.host:
        ui.force_demo = args.demo
        ui.selected_split_mode = args.mode
        ui.start_host()
    elif args.client is not None:
        target_ip = args.client.strip() if args.client.strip() else None
        ui.start_client(target_ip)
    else:
        # Default: Launch GUI launcher
        ui.run_launcher()


if __name__ == "__main__":
    main()
