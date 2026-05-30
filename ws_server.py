#!/usr/bin/env python3
"""
Unified WebSocket Server
Handles WebSocket connections and routes to any backend implementation.
"""

import asyncio
import websockets
import json
import base64
from typing import Optional
from backend_base import StreamingBackend


class UnifiedWebSocketServer:
    """Generic WebSocket server that works with any StreamingBackend."""

    def __init__(self, backend: StreamingBackend, name: str = "Streaming Backend"):
        self.backend = backend
        self.name = name
        self.clients = set()

    async def handle_client(self, websocket):
        """Handle a new client connection."""
        self.clients.add(websocket)
        print(f"Client connected: {websocket.remote_address}")

        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            print(f"Client disconnected: {websocket.remote_address}")
        finally:
            self.clients.remove(websocket)

    async def handle_message(self, websocket, message):
        """Route incoming messages to backend."""
        try:
            if isinstance(message, bytes):
                # Binary frame payload
                await self._handle_binary_frame(websocket, message)
                return

            # JSON command
            data = json.loads(message)
            command = data.get("command")

            if command == "connect":
                port = data.get("port", None)
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(
                    None, self.backend.connect, port
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "connect",
                            "success": success,
                            "message": f"Connected to {self.name}"
                            if success
                            else f"Failed to connect to {self.name}",
                        }
                    )
                )

            elif command == "disconnect":
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.backend.disconnect)
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "disconnect",
                            "success": success,
                            "message": "Disconnected",
                        }
                    )
                )

            elif command == "get_viewer":
                loop = asyncio.get_event_loop()

                def get_viewer_data():
                    try:
                        from streamer_machinecode import STREAMER_PRG
                        return base64.b64encode(STREAMER_PRG).decode('utf-8')
                    except ImportError:
                        return None

                encoded_prg = await loop.run_in_executor(None, get_viewer_data)
                if encoded_prg:
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "response",
                                "command": "get_viewer",
                                "success": True,
                                "prg_data": encoded_prg,
                                "filename": "kung_fu_viewer.prg",
                            }
                        )
                    )
                else:
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "response",
                                "command": "get_viewer",
                                "success": False,
                                "message": "Viewer not available for this backend",
                            }
                        )
                    )

            elif command == "send_viewer":
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.backend.send_viewer)
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "send_viewer",
                            "success": success,
                            "message": "Viewer sent successfully!"
                            if success
                            else "Failed to send viewer",
                        }
                    )
                )

            elif command == "status":
                status = self.backend.get_status()
                await websocket.send(
                    json.dumps(
                        {"type": "response", "command": "status", **status}
                    )
                )

            elif command == "reset":
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.backend.reset)
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "reset",
                            "success": success,
                            "message": "Reset signal sent" if success else "Reset failed",
                        }
                    )
                )

            elif command == "reset_buffers":
                mode = data.get("mode", "unknown")
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(
                    None, self.backend.reset_stream_buffers, f"mode change to {mode}"
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "reset_buffers",
                            "success": success,
                            "message": "Stream buffers will be fully refreshed",
                        }
                    )
                )

            elif command == "stream_frame":
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "stream_frame",
                            "success": False,
                            "message": "Please use binary streaming for frames",
                        }
                    )
                )

            else:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "error",
                            "message": f"Unknown command: {command}",
                        }
                    )
                )

        except Exception as e:
            print(f"Message handling failed: {e}")
            import traceback
            traceback.print_exc()
            await websocket.send(
                json.dumps({"type": "error", "message": str(e)})
            )

    async def _handle_binary_frame(self, websocket, message: bytes):
        """Handle binary frame streaming."""
        if len(message) < 10002:
            print(f"Binary payload too small: {len(message)}")
            return

        mode = message[0]
        bg_color = message[1]
        bitmap = message[2:8002]
        screen = message[8002:9002]
        color = message[9002:10002]

        if self.backend.is_viewer_running:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                self.backend.stream_frame,
                mode,
                bg_color,
                bitmap,
                screen,
                color,
            )

            status = self.backend.get_status()
            await websocket.send(
                json.dumps(
                    {
                        "type": "response",
                        "command": "stream_frame",
                        "success": success,
                        "frame_count": status.get("frame_count", 0),
                        "message": "Frame sent" if success else "Frame failed",
                    }
                )
            )
        else:
            await websocket.send(
                json.dumps(
                    {
                        "type": "response",
                        "command": "stream_frame",
                        "success": False,
                        "message": "Viewer not running. Send viewer first.",
                    }
                )
            )


async def start_server(
    backend: StreamingBackend,
    backend_name: str,
    host: str = "localhost",
    port: int = 8765,
):
    """Start the unified WebSocket server."""
    server = UnifiedWebSocketServer(backend, backend_name)

    print("=" * 60)
    print(f"Unified WebSocket Server - {backend_name}")
    print("=" * 60)
    print(f"WebSocket server on ws://{host}:{port}")
    print()

    async with websockets.serve(server.handle_client, host, port):
        print("Server running. Press Ctrl+C to stop.")
        await asyncio.Future()


def run_server(
    backend: StreamingBackend,
    backend_name: str = "Backend",
    host: str = "localhost",
    port: int = 8765,
):
    """Convenience function to run server."""
    try:
        asyncio.run(start_server(backend, backend_name, host, port))
    except KeyboardInterrupt:
        print("\nServer stopped.")
