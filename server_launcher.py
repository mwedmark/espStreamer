#!/usr/bin/env python3
"""
Server Launcher
Starts the appropriate backend WebSocket server based on command-line arguments.
"""

import argparse
import sys
from backend_kungfu import KungFuFlashSerial
from backend_vice import VICEKungFuSimulator
from ws_server import run_server


def main():
    parser = argparse.ArgumentParser(
        description="Start a streaming backend server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python server_launcher.py --backend kung_fu --port 8765
  python server_launcher.py --backend vice --port 8766
  python server_launcher.py --backend kung_fu  (default: localhost:8765)
        """,
    )

    parser.add_argument(
        "--backend",
        choices=["kung_fu", "vice"],
        default="kung_fu",
        help="Which backend to use (default: kung_fu)",
    )

    parser.add_argument(
        "--host",
        default="localhost",
        help="WebSocket server host (default: localhost)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="WebSocket server port (default: 8765)",
    )

    parser.add_argument(
        "--vice-port",
        type=int,
        default=6511,
        help="VICE binary monitor port (only for VICE backend, default: 6511)",
    )

    args = parser.parse_args()

    # Create the appropriate backend
    if args.backend == "kung_fu":
        backend = KungFuFlashSerial()
        backend_name = "Kung Fu Flash"
    elif args.backend == "vice":
        backend = VICEKungFuSimulator()
        backend_name = f"VICE Emulator (port {args.vice_port})"
    else:
        print(f"Unknown backend: {args.backend}")
        sys.exit(1)

    # Start the server
    print(f"Starting {backend_name} backend server...")
    print(f"Listening on {args.host}:{args.port}")
    print()

    run_server(backend, backend_name, args.host, args.port)


if __name__ == "__main__":
    main()
