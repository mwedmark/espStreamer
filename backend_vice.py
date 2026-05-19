#!/usr/bin/env python3
"""
VICE Emulator Backend
Simulates streaming to VICE via the Binary Monitor Port.
"""

import socket
import struct
from typing import Dict, Optional
from backend_base import StreamingBackend


class VICEBinaryMonitor:
    """Low-level VICE binary monitor protocol."""

    def __init__(self, port: int = 6511):
        self.port = port
        self.sock: Optional[socket.socket] = None

    def connect(self) -> bool:
        """Connect to VICE binary monitor."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(("localhost", self.port))
            print(f"Connected to VICE binary monitor on port {self.port}")
            return True
        except Exception as e:
            print(f"Failed to connect to VICE binary monitor: {e}")
            self.sock = None
            return False

    def disconnect(self):
        """Disconnect from VICE."""
        if self.sock:
            self.sock.close()
            self.sock = None
            print("Disconnected from VICE binary monitor")

    def write_memory(self, start_addr: int, data: bytes, side_effects: bool = False) -> bool:
        """Write memory via VICE binary monitor protocol."""
        if not self.sock:
            return False

        end_addr = start_addr + len(data) - 1
        body_len = 8 + len(data)
        request_id = 0x1234

        header = struct.pack("<BBIIB", 0x02, 0x02, body_len, request_id, 0x02)
        body = struct.pack(
            "<BHHBH", 1 if side_effects else 0, start_addr, end_addr, 0, 0
        )

        try:
            self.sock.setblocking(False)
            while True:
                try:
                    discard = self.sock.recv(4096)
                    if not discard:
                        break
                except:
                    break
            self.sock.setblocking(True)

            self.sock.sendall(header + body + data)

            while True:
                resp_header = b""
                while len(resp_header) < 12:
                    chunk = self.sock.recv(12 - len(resp_header))
                    if not chunk:
                        print("Connection closed by VICE")
                        self.disconnect()
                        return False
                    resp_header += chunk

                stx, ver, blen, ctype, err, rid = struct.unpack("<BBIBBI", resp_header)

                body_data = b""
                bytes_to_read = blen
                while bytes_to_read > 0:
                    chunk = self.sock.recv(min(bytes_to_read, 4096))
                    if not chunk:
                        break
                    body_data += chunk
                    bytes_to_read -= len(chunk)

                if rid == request_id:
                    if err != 0x00:
                        print(f"VICE returned error {err} for MEM_SET")
                        return False
                    return True

        except Exception as e:
            print(f"Failed to write memory: {e}")
            self.disconnect()
            return False

    def resume_execution(self) -> bool:
        """Send MON_CMD_EXIT to resume VICE execution."""
        if not self.sock:
            return False

        request_id = 0x1235
        header = struct.pack("<BBIIB", 0x02, 0x02, 0, request_id, 0xAA)

        try:
            self.sock.setblocking(False)
            while True:
                try:
                    discard = self.sock.recv(4096)
                    if not discard:
                        break
                except:
                    break
            self.sock.setblocking(True)

            self.sock.sendall(header)

            while True:
                resp_header = b""
                while len(resp_header) < 12:
                    chunk = self.sock.recv(12 - len(resp_header))
                    if not chunk:
                        return False
                    resp_header += chunk

                stx, ver, blen, ctype, err, rid = struct.unpack("<BBIBBI", resp_header)

                body_data = b""
                bytes_to_read = blen
                while bytes_to_read > 0:
                    chunk = self.sock.recv(min(bytes_to_read, 4096))
                    if not chunk:
                        break
                    bytes_to_read -= len(chunk)

                if rid == request_id or ctype == 0xAA:
                    return True
        except Exception as e:
            print(f"Failed to resume execution: {e}")
            return False


class VICEBackend(StreamingBackend):
    """VICE emulator backend via binary monitor port."""

    def __init__(self, port: int = 6511):
        self.monitor = VICEBinaryMonitor(port)
        self._connected = False
        self._viewer_running = False
        self.frame_count = 0

    def connect(self, port: Optional[str] = None) -> bool:
        """Connect to VICE binary monitor."""
        if self.monitor.connect():
            self.monitor.resume_execution()
            self._connected = True
            self._viewer_running = True
            return True
        return False

    def disconnect(self) -> bool:
        """Disconnect from VICE."""
        self.monitor.disconnect()
        self._connected = False
        self._viewer_running = False
        return True

    def send_viewer(self, viewer_data: Optional[bytes] = None) -> bool:
        """VICE doesn't need a separate viewer PRG; memory is accessed directly."""
        print("VICE backend: viewer not needed (direct memory access)")
        return True

    def stream_frame(
        self, mode: int, bg_color: int, bitmap: bytes, screen: bytes, color: bytes
    ) -> bool:
        """Stream a frame to VICE by writing memory."""
        if not self.monitor.sock or not self._viewer_running:
            return False

        try:
            # Write VIC registers based on mode
            if mode == 1:  # Hires
                self.monitor.write_memory(0xD011, bytes([0x3B]), side_effects=True)
                self.monitor.write_memory(0xD016, bytes([0xC8]), side_effects=True)
            else:  # Multicolor
                self.monitor.write_memory(0xD011, bytes([0x3B]), side_effects=True)
                self.monitor.write_memory(0xD016, bytes([0xD8]), side_effects=True)

            self.monitor.write_memory(0xD018, bytes([0x18]), side_effects=True)
            self.monitor.write_memory(0xD020, bytes([0x00]), side_effects=True)
            self.monitor.write_memory(0xD021, bytes([bg_color & 0xFF]), side_effects=True)

            # Write RAM blocks
            self.monitor.write_memory(0x2000, bitmap[:8000])
            self.monitor.write_memory(0x0400, screen[:1000])
            success = self.monitor.write_memory(0xD800, color[:1000], side_effects=True)

            if success:
                self.frame_count += 1
                self.monitor.resume_execution()

            return success

        except Exception as e:
            print(f"Stream frame failed: {e}")
            return False

    def reset(self) -> bool:
        """Reset VICE (soft reset via memory write)."""
        if not self.monitor.sock:
            return False
        try:
            self.monitor.write_memory(0xFFFC, bytes([0x00, 0xE5]), side_effects=True)
            return True
        except Exception as e:
            print(f"Reset failed: {e}")
            return False

    def reset_stream_buffers(self, reason: str = "manual") -> bool:
        """VICE doesn't buffer frames; this is a no-op."""
        print(f"Stream buffers reset ({reason}) - VICE direct access mode")
        return True

    def get_status(self) -> Dict:
        """Get current status."""
        connected = self._connected
        if not connected:
            connected = self.monitor.connect()

        return {
            "connected": connected,
            "viewer_running": self._viewer_running,
            "frame_count": self.frame_count,
            "message": "VICE connected" if connected else "VICE disconnected",
        }

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_viewer_running(self) -> bool:
        return self._viewer_running
