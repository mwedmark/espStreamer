#!/usr/bin/env python3
"""
WIC-64 WiFi Streaming Server (Thin Launcher)
Streams to WIC-64 parallel User Port WiFi module over TCP.

This is now a thin launcher that delegates to the unified ws_server.py.
"""

import asyncio
from backend_wic64 import WIC64Backend


def get_backend():
    """Create and configure the WIC-64 backend."""
    return WIC64Backend(listen_port=8768)


async def main():
    """Run the server with WIC-64 backend."""
    print("=" * 60)
    print("WIC-64 WiFi Streaming Server")
    print("=" * 60)
    print("WebSocket server on ws://0.0.0.0:8765")
    print("TCP Stream server on port 8768")
    print()
    print("Usage:")
    print("  1. Connect C64 and WIC-64 to your local WiFi.")
    print("  2. Load and run 'wic64_viewer.prg' on the C64:")
    print("     LOAD \"http://<PC_IP>:8765/wic64_viewer.prg\",137")
    print("  3. Open ESPStreamer web interface, set to 'WIC-64 WiFi' and click Connect.")
    print("  4. Click 'Start Stream' to send frames!")
    print()

    backend = get_backend()
    backend.connect()
    
    from ws_server import start_server
    await start_server(backend, "WIC-64 WiFi Target", host="0.0.0.0", port=8765)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
