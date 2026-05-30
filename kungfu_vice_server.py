#!/usr/bin/env python3
"""
Kung Fu Flash VICE Simulation Server (Thin Launcher)
Simulates streaming to VICE via the Binary Monitor Port.

This is now a thin launcher that delegates to the unified ws_server.py.
"""

import asyncio
import socket
import struct
from backend_vice import VICEBinaryMonitor, VICEKungFuSimulator


def get_backend():
    """Create and configure the VICE backend."""
    return VICEKungFuSimulator()


async def main():
    """Run the server with VICE backend."""
    print("Starting Kung Fu Flash VICE Simulation Server...")
    print("WebSocket server will run on ws://localhost:8766")
    print()
    
    print("To test:")
    print("1. Start VICE with binary monitor enabled: x64sc.exe -binarymonitor")
    print("2. Use ESPStreamer web interface to connect in VICE Mode")
    print("3. Stream frames!")
    print()

    backend = get_backend()
    
    from ws_server import start_server
    await start_server(backend, "VICE Simulation (Binary Monitor)", host="localhost", port=8766)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
