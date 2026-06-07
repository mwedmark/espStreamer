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
import numpy as np
from streamer_machinecode import STREAMER_PRG, STREAMER_CRT

_ZERO_BYTES = b"\x00" * 8192
_ZERO_MV = memoryview(_ZERO_BYTES)

class FrameBufferPool:
    """Preallocated bytearrays to avoid GC pressure during streaming."""
    def __init__(self):
        # Padded/page arrays (8192/1024/1024), payload buffers (11000/11000), chunk header (2)
        self.bitmap_pages = bytearray(8192)
        self.screen_pages = bytearray(1024)
        self.color_pages = bytearray(1024)
        self.prev_color_pages = bytearray(1024)
        self.payload = bytearray(11000)
        self.delta_payload = bytearray(11000)
        self.chunk_header = bytearray(2)
        
        # Pre-wrap them in memoryviews
        self.bitmap_pages_mv = memoryview(self.bitmap_pages)
        self.screen_pages_mv = memoryview(self.screen_pages)
        self.color_pages_mv = memoryview(self.color_pages)
        self.prev_color_pages_mv = memoryview(self.prev_color_pages)
        self.payload_mv = memoryview(self.payload)
        self.delta_payload_mv = memoryview(self.delta_payload)

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
        self.bitmap_buffers_mv = [None, None]
        self.screen_buffers = [None, None]
        self.screen_buffers_mv = [None, None]
        self.frame_count = 0
        self.delta_threshold = 0.90
        self.bytes_sent = 0
        self.total_ratio_sum = 0.0
        self.ratio_count = 0
        self.connection_start_time = None
        self.pool = FrameBufferPool()

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
            self.bitmap_buffers_mv = [None, None]
            self.screen_buffers = [None, None]
            self.screen_buffers_mv = [None, None]

            self.ser.reset_output_buffer()

            print(f"Connected to KFF on {port}")
            print("Ready for chunked data flow.")
            self.connection_start_time = time.time()
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
        self.bitmap_buffers_mv = [None, None]
        self.screen_buffers = [None, None]
        self.screen_buffers_mv = [None, None]
        self.connection_start_time = None
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
            self.bitmap_buffers_mv = [None, None]
            self.screen_buffers = [None, None]
            self.screen_buffers_mv = [None, None]
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

                # Slicing bytes object directly (fast C slicing)
                bitmap_len = min(len(bitmap), 8000)
                self.pool.bitmap_pages[:bitmap_len] = bitmap[:bitmap_len]
                if bitmap_len < 8000:
                    self.pool.bitmap_pages[bitmap_len:8000] = _ZERO_MV[:8000 - bitmap_len]

                screen_len = min(len(screen), 1000)
                self.pool.screen_pages[:screen_len] = screen[:screen_len]
                if screen_len < 1000:
                    self.pool.screen_pages[screen_len:1000] = _ZERO_MV[:1000 - screen_len]

                color_len = min(len(color), 1000)
                self.pool.color_pages[:color_len] = color[:color_len]
                if color_len < 1000:
                    self.pool.color_pages[color_len:1000] = _ZERO_MV[:1000 - color_len]

                mode_changed = self.prev_mode != mode_byte
                if mode_changed:
                    self.full_refresh_frames = max(self.full_refresh_frames, 2)

                force_full_refresh = self.full_refresh_frames > 0

                # Compare prev_screen and prev_color directly without allocation
                if self.prev_screen is None:
                    screen_changed = True
                else:
                    screen_changed = mode_changed or self.prev_screen != self.pool.screen_pages[:1000]

                if self.prev_color is None:
                    color_changed = True
                else:
                    color_changed = mode_changed or self.prev_color != self.pool.color_pages[:1000]

                if screen_changed:
                    self.screen_refresh_frames = 2

                send_screen = force_full_refresh or self.screen_refresh_frames > 0
                send_color = force_full_refresh or color_changed

                flags = (0x01 if send_screen else 0x00) | (
                    0x02 if send_color else 0x00
                )

                # Build full payload in pool.payload
                payload_buf = self.pool.payload
                payload_buf[0] = mode_byte
                payload_buf[1] = bg_color & 0xFF
                payload_buf[2] = flags
                payload_buf[3] = 0
                payload_buf[4:8004] = self.pool.bitmap_pages[:8000]

                payload_len = 8004
                if send_screen:
                    payload_buf[payload_len : payload_len + 1000] = self.pool.screen_pages[:1000]
                    payload_len += 1000
                if send_color:
                    payload_buf[payload_len : payload_len + 1000] = self.pool.color_pages[:1000]
                    payload_len += 1000

                payload_view = self.pool.payload_mv[:payload_len]
                used_delta = False
                target_buffer = self.next_buffer

                def page_records(curr_mv, prev_mv, page_count):
                    if prev_mv is None:
                        return None
                    curr_arr = np.frombuffer(curr_mv, dtype=np.uint8)
                    prev_arr = np.frombuffer(prev_mv, dtype=np.uint8)
                    limit = page_count * 256
                    curr_pages = curr_arr[:limit].reshape(page_count, 256)
                    prev_pages = prev_arr[:limit].reshape(page_count, 256)
                    diff_mask = np.any(curr_pages != prev_pages, axis=1)
                    changed_pages = np.where(diff_mask)[0]
                    records = []
                    for page in changed_pages:
                        start = page * 256
                        end = start + 256
                        records.append((page, curr_mv[start:end]))
                    return records

                if not force_full_refresh:
                    bitmap_records = page_records(
                        self.pool.bitmap_pages_mv, self.bitmap_buffers_mv[target_buffer], 32
                    )
                    screen_records = page_records(
                        self.pool.screen_pages_mv, self.screen_buffers_mv[target_buffer], 4
                    )
                    color_records = page_records(
                        self.pool.color_pages_mv,
                        self.pool.prev_color_pages_mv if self.prev_color is not None else None,
                        4,
                    )

                    if (
                        bitmap_records is not None
                        and screen_records is not None
                        and color_records is not None
                    ):
                        changed_count = len(bitmap_records) + len(screen_records) + len(color_records)
                        # Only use delta if change rate is below threshold
                        if (changed_count / 40.0) < self.delta_threshold:
                            # Construct delta payload in self.pool.delta_payload
                            dp = self.pool.delta_payload
                            dp[0] = mode_byte
                            dp[1] = bg_color & 0xFF
                            dp[2] = 0x80
                            dp[3] = len(bitmap_records)
                            dp[4] = len(screen_records)
                            dp[5] = len(color_records)
                            dp[6] = 0
                            dp[7] = 0

                            dp_len = 8
                            for records in (bitmap_records, screen_records, color_records):
                                for page, page_data in records:
                                    dp[dp_len] = page
                                    dp[dp_len + 1] = 0
                                    dp[dp_len + 2] = 0
                                    dp[dp_len + 3] = 0
                                    dp_len += 4
                                    dp[dp_len : dp_len + 256] = page_data
                                    dp_len += 256

                            if dp_len < payload_len:
                                payload_view = self.pool.delta_payload_mv[:dp_len]
                                used_delta = True

                offset = 0
                self.ser.timeout = 2.0

                while offset < len(payload_view):
                    req = self.ser.read(2)
                    if len(req) < 2:
                        print(f"Chunk request timeout at offset {offset}.")
                        return False
                    else:
                        chunk_size = req[0] + req[1] * 256

                    if chunk_size == 0:
                        continue

                    remaining = len(payload_view) - offset
                    actual_size = min(chunk_size, remaining)
                    chunk_mv = payload_view[offset : offset + actual_size]

                    self.pool.chunk_header[0] = actual_size & 0xFF
                    self.pool.chunk_header[1] = (actual_size >> 8) & 0xFF

                    self.ser.write(self.pool.chunk_header)
                    self.ser.write(chunk_mv)
                    self.ser.flush()

                    offset += actual_size

                self.prev_mode = mode_byte

                # Copy buffer contents in-place to avoid allocations
                if self.bitmap_buffers[target_buffer] is None:
                    self.bitmap_buffers[target_buffer] = bytearray(8192)
                    self.bitmap_buffers_mv[target_buffer] = memoryview(self.bitmap_buffers[target_buffer])
                self.bitmap_buffers[target_buffer][:] = self.pool.bitmap_pages

                if self.screen_buffers[target_buffer] is None:
                    self.screen_buffers[target_buffer] = bytearray(1024)
                    self.screen_buffers_mv[target_buffer] = memoryview(self.screen_buffers[target_buffer])
                self.screen_buffers[target_buffer][:] = self.pool.screen_pages

                if self.prev_screen is None:
                    self.prev_screen = bytearray(1000)
                self.prev_screen[:] = self.pool.screen_pages[:1000]

                if self.prev_color is None:
                    self.prev_color = bytearray(1000)
                self.prev_color[:] = self.pool.color_pages[:1000]
                self.pool.prev_color_pages[:1000] = self.pool.color_pages[:1000]

                if self.full_refresh_frames > 0:
                    self.full_refresh_frames -= 1
                if send_screen and not used_delta:
                    self.screen_refresh_frames -= 1
                elif used_delta:
                    self.screen_refresh_frames = 0
                self.next_buffer ^= 1
                self.frame_count += 1

                # Update metrics
                actual_len = len(payload_view)
                self.bytes_sent += actual_len
                ratio = actual_len / max(1, payload_len)
                self.total_ratio_sum += ratio
                self.ratio_count += 1

                # Log metrics every 100 frames
                if self.frame_count > 0 and self.frame_count % 100 == 0:
                    avg_ratio = self.total_ratio_sum / max(1, self.ratio_count)
                    print(f"[Metrics] Frame {self.frame_count}: avg compression ratio: {avg_ratio:.2%}, total bytes sent: {self.bytes_sent:,} bytes")

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
            self.bitmap_buffers_mv = [None, None]
            self.screen_buffers = [None, None]
            self.screen_buffers_mv = [None, None]
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
            "bytes_sent": self.bytes_sent,
            "total_ratio_sum": self.total_ratio_sum,
            "ratio_count": self.ratio_count,
            "connection_start_time": self.connection_start_time,
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
