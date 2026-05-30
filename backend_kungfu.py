#!/usr/bin/env python3
"""
Kung Fu Flash Hardware Backend
Streams to real Kung Fu Flash cartridge via USB serial connection.
"""

import serial
import serial.tools.list_ports
import time
import threading
from typing import Dict, Optional
from streamer_machinecode import STREAMER_PRG, STREAMER_CRT

class KungFuFlashSerial:
    """Kung Fu Flash hardware backend via USB serial."""

    def __init__(self):
        self.ser: Optional[serial.Serial] = None
        self.port_name: Optional[str] = None
        self._connected = False
        self._viewer_running = False
        self.lock = threading.Lock()
        self.prev_mode: Optional[int] = None
        self.prev_screen: Optional[bytes] = None
        self.prev_color: Optional[bytes] = None
        self.screen_refresh_frames = 0
        self.full_refresh_frames = 0
        self.next_buffer = 1
        self.bitmap_buffers = [None, None]
        self.screen_buffers = [None, None]
        self.frame_count = 0

    @staticmethod
    def find_kff_port() -> list:
        """Try to auto-detect KFF serial port."""
        ports = serial.tools.list_ports.comports()
        candidates = []
        for p in ports:
            desc = (p.description or "").lower()
            if "serial" in desc or "acm" in desc or "cdc" in desc:
                candidates.append(p.device)
            if p.vid == 0x0483:
                candidates.append(p.device)
        return candidates

    def connect(self, port: Optional[str] = None) -> bool:
        """Connect to KFF serial port."""
        try:
            if port is None:
                candidates = self.find_kff_port()
                if not candidates:
                    print("No KFF serial port found. Available ports:")
                    for p in serial.tools.list_ports.comports():
                        print(f"  {p.device}: {p.description}")
                    return False
                port = candidates[0]
                print(f"Auto-detected KFF port: {port}")

            self.ser = serial.Serial(
                port=port,
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2,
                write_timeout=2,
            )
            self.ser.dtr = True
            self.port_name = port
            self._connected = True
            self._viewer_running = True
            self.prev_mode = None
            self.prev_screen = None
            self.prev_color = None
            self.screen_refresh_frames = 0
            self.full_refresh_frames = 0
            self.next_buffer = 1
            self.bitmap_buffers = [None, None]
            self.screen_buffers = [None, None]

            self.ser.reset_output_buffer()

            print(f"Connected to KFF on {port}")
            print("Ready for chunked data flow.")
            return True

        except Exception as e:
            print(f"Serial connection failed: {e}")
            self.ser = None
            return False

    def disconnect(self):
        """Close serial connection."""
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
            self.ser = None
        self._connected = False
        self._viewer_running = False
        self.prev_mode = None
        self.prev_screen = None
        self.prev_color = None
        self.screen_refresh_frames = 0
        self.full_refresh_frames = 0
        self.next_buffer = 1
        self.bitmap_buffers = [None, None]
        self.screen_buffers = [None, None]
        print("Disconnected from KFF")

    def send_viewer(self, viewer_data: Optional[bytes] = None) -> bool:
        """Send the streamer PRG to KFF via EFSTART:PRG handshake."""
        if not self.ser:
            return False

        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.1)

            prg_data = viewer_data if viewer_data else STREAMER_PRG
            print(f"Sending streamer PRG ({len(prg_data)} bytes)...")

            max_retries = 10
            for attempt in range(max_retries):
                handshake = b"EFSTART:PRG\x00"
                self.ser.write(handshake)
                self.ser.flush()

                resp = self.ser.read(5)
                if len(resp) < 5:
                    print(f"  Handshake timeout (got {len(resp)} bytes)")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    return False

                if resp[0] == ord("W"):
                    print("  KFF waiting, retrying...")
                    time.sleep(1)
                    continue
                elif resp[0] == ord("L"):
                    print("  KFF ready to load!")
                    break
                else:
                    return False
            else:
                print("  Max retries reached")
                return False

            offset = 0
            actual_size = 0
            chunk_size = 0
            while offset < len(prg_data):
                size_req = self.ser.read(2)
                if len(size_req) < 2:
                    print("  Chunk size request timeout")
                    return False

                chunk_size = size_req[0] + size_req[1] * 256
                if chunk_size == 0:
                    break

                remaining = len(prg_data) - offset
                actual_size = min(chunk_size, remaining)
                chunk = prg_data[offset : offset + actual_size]

                self.ser.write(bytes([actual_size & 0xFF, (actual_size >> 8) & 0xFF]))
                self.ser.write(chunk)
                self.ser.flush()

                offset += actual_size
                print(f"  Sent {offset}/{len(prg_data)} bytes")

            if offset >= len(prg_data) and actual_size > 0 and actual_size == chunk_size:
                try:
                    self.ser.timeout = 0.5
                    size_req = self.ser.read(2)
                    if len(size_req) == 2:
                        self.ser.write(bytes([0x00, 0x00]))
                        self.ser.flush()
                except:
                    pass

            print("Streamer PRG sent successfully!")
            time.sleep(0.5)
            self._viewer_running = True
            self.prev_mode = None
            self.prev_screen = None
            self.prev_color = None
            self.screen_refresh_frames = 0
            self.full_refresh_frames = 0
            self.next_buffer = 1
            self.bitmap_buffers = [None, None]
            self.screen_buffers = [None, None]
            return True

        except Exception as e:
            print(f"Failed to send viewer PRG: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stream_frame(
        self, mode: int, bg_color: int, bitmap: bytes, screen: bytes, color: bytes
    ) -> bool:
        """Stream a single frame to the C64 viewer."""
        if not self.ser or not self._viewer_running:
            return False

        with self.lock:
            try:
                mode_byte = mode & 0xFF
                bitmap_data = bytes(bitmap[:8000]).ljust(8000, b"\x00")
                screen_data = bytes(screen[:1000]).ljust(1000, b"\x00")
                color_data = bytes(color[:1000]).ljust(1000, b"\x00")
                bitmap_pages = bitmap_data.ljust(8192, b"\x00")
                screen_pages = screen_data.ljust(1024, b"\x00")
                color_pages = color_data.ljust(1024, b"\x00")

                mode_changed = self.prev_mode != mode_byte
                if mode_changed:
                    self.full_refresh_frames = max(self.full_refresh_frames, 2)

                force_full_refresh = self.full_refresh_frames > 0
                screen_changed = mode_changed or self.prev_screen != screen_data
                color_changed = mode_changed or self.prev_color != color_data

                if screen_changed:
                    self.screen_refresh_frames = 2

                send_screen = force_full_refresh or self.screen_refresh_frames > 0
                send_color = force_full_refresh or color_changed

                flags = (0x01 if send_screen else 0x00) | (
                    0x02 if send_color else 0x00
                )
                full_payload = bytes([mode_byte, bg_color & 0xFF, flags, 0])
                full_payload += bitmap_data
                if send_screen:
                    full_payload += screen_data
                if send_color:
                    full_payload += color_data

                payload = full_payload
                used_delta = False
                target_buffer = self.next_buffer

                def page_records(current, previous, page_count):
                    records = []
                    if previous is None:
                        return None
                    for page in range(page_count):
                        start = page * 256
                        end = start + 256
                        page_data = current[start:end]
                        if page_data != previous[start:end]:
                            records.append((page, page_data))
                    return records

                if not force_full_refresh:
                    bitmap_records = page_records(
                        bitmap_pages, self.bitmap_buffers[target_buffer], 32
                    )
                    screen_records = page_records(
                        screen_pages, self.screen_buffers[target_buffer], 4
                    )
                    color_records = page_records(
                        color_pages,
                        self.prev_color.ljust(1024, b"\x00")
                        if self.prev_color
                        else None,
                        4,
                    )

                    if (
                        bitmap_records is not None
                        and screen_records is not None
                        and color_records is not None
                    ):
                        delta_payload = bytes(
                            [mode_byte, bg_color & 0xFF, 0x80, len(bitmap_records)]
                        )
                        delta_payload += bytes(
                            [len(screen_records), len(color_records), 0, 0]
                        )
                        for records in (bitmap_records, screen_records, color_records):
                            for page, page_data in records:
                                delta_payload += bytes([page, 0, 0, 0])
                                delta_payload += page_data

                        if len(delta_payload) < len(full_payload):
                            payload = delta_payload
                            used_delta = True

                offset = 0
                self.ser.timeout = 2.0

                while offset < len(payload):
                    req = self.ser.read(2)
                    if len(req) < 2:
                        print(f"Chunk request timeout at offset {offset}.")
                        return False
                    else:
                        chunk_size = req[0] + req[1] * 256

                    if chunk_size == 0:
                        continue

                    remaining = len(payload) - offset
                    actual_size = min(chunk_size, remaining)
                    chunk = payload[offset : offset + actual_size]

                    self.ser.write(
                        bytes([actual_size & 0xFF, (actual_size >> 8) & 0xFF])
                    )
                    self.ser.write(chunk)
                    self.ser.flush()

                    offset += actual_size

                self.prev_mode = mode_byte
                self.bitmap_buffers[target_buffer] = bitmap_pages
                self.screen_buffers[target_buffer] = screen_pages
                self.prev_screen = screen_data
                self.prev_color = color_data
                if self.full_refresh_frames > 0:
                    self.full_refresh_frames -= 1
                if send_screen and not used_delta:
                    self.screen_refresh_frames -= 1
                elif used_delta:
                    self.screen_refresh_frames = 0
                self.next_buffer ^= 1
                self.frame_count += 1

                return True

            except Exception as e:
                print(f"Stream frame failed: {e}")
                return False

    def reset(self) -> bool:
        """Reset KFF to menu."""
        if self.ser:
            port = self.port_name
            self.disconnect()
            try:
                s = serial.Serial(port=port, baudrate=1200)
                time.sleep(0.5)
                s.close()
                print("Reset signal sent to KFF")
                time.sleep(2)
                return True
            except Exception as e:
                print(f"Reset failed: {e}")
                return False
        return False

    def reset_stream_buffers(self, reason: str = "manual") -> bool:
        """Invalidate stream buffers to force full refresh."""
        with self.lock:
            self.prev_mode = None
            self.prev_screen = None
            self.prev_color = None
            self.screen_refresh_frames = 0
            self.full_refresh_frames = 2
            self.next_buffer = 1
            self.bitmap_buffers = [None, None]
            self.screen_buffers = [None, None]
        print(f"Stream buffers reset ({reason}); forcing two full C64 refreshes.")
        return True

    def get_status(self) -> Dict:
        """Get current status."""
        return {
            "connected": self._connected,
            "viewer_running": self._viewer_running,
            "port": self.port_name,
            "frame_count": self.frame_count,
            "is_viewer_running": self._viewer_running,
            "backend_name": "Kung Fu Flash (Serial CDC)",
            "message": "Streaming"
            if self._viewer_running
            else "Connected"
            if self._connected
            else "Disconnected",
        }

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_viewer_running(self) -> bool:
        return self._viewer_running

    def __del__(self):
        self.disconnect()


# Export viewer binaries to disk for direct use
with open("kungfu_viewer.prg", "wb") as f:
    f.write(STREAMER_PRG)

with open("kungfu_viewer.crt", "wb") as f:
    f.write(STREAMER_CRT)
