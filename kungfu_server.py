#!/usr/bin/env python3
"""
Kung Fu Flash WebSocket Server (Thin Launcher)
Bridges ESPStreamer web app to real Kung Fu Flash cartridge via EF3 USB protocol.
Uses CDC serial port (pyserial) and EFSTART:PRG handshake.

This is now a thin launcher that delegates to the unified ws_server.py.
"""

import asyncio
import serial
import serial.tools.list_ports
import threading
import base64
from backend_kungfu import KungFuFlashSerial, STREAMER_PRG, STREAMER_CRT


def get_backend() -> KungFuFlashSerial:
    """Create and configure the KFF backend."""
    return KungFuFlashSerial()


async def main():
    """Run the server with KFF backend."""
    print("=" * 60)
    print("Kung Fu Flash Streaming Server")
    print("=" * 60)
    print(f"Streamer CRT size: {len(STREAMER_CRT)} bytes")
    print()

    # Show available ports
    ports = serial.tools.list_ports.comports()
    if ports:
        print("Available serial ports:")
        for p in ports:
            print(f"  {p.device}: {p.description}")
    else:
        print("No serial ports found.")
    print()

    print("WebSocket server on ws://localhost:8765")
    print()
    print("Usage:")
    print("  1. Copy 'kungfu_viewer.prg' to Kung Fu Flash SD card.")
    print("  2. Boot 'kungfu_viewer.prg' manually on the C64.")
    print("  3. Open ESPStreamer web interface, set to 'Hardware Mode' and click Connect.")
    print("  4. Click 'Start Stream' to send frames!")
    print()

    backend = get_backend()
    
    from ws_server import start_server
    await start_server(backend, "Kung Fu Flash (Serial CDC)", host="localhost", port=8765)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
