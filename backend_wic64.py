#!/usr/bin/env python3
"""
WIC-64 target platform backend implementation.
Hosts a TCP socket server that pushes digitized frame/delta data to C64 clients.
"""

import socket
import threading
import time
from typing import Dict, Optional
import numpy as np
from backend_base import StreamingBackend

_ZERO_BYTES = b"\x00" * 8192
_ZERO_MV = memoryview(_ZERO_BYTES)


class WIC64FrameBufferPool:
    """Preallocated bytearrays to avoid GC pressure during streaming."""
    def __init__(self):
        self.bitmap_pages = bytearray(8192)
        self.screen_pages = bytearray(1024)
        self.color_pages = bytearray(1024)
        self.prev_color_pages = bytearray(1024)
        self.payload = bytearray(11000)
        self.delta_payload = bytearray(11000)
        
        self.bitmap_pages_mv = memoryview(self.bitmap_pages)
        self.screen_pages_mv = memoryview(self.screen_pages)
        self.color_pages_mv = memoryview(self.color_pages)
        self.prev_color_pages_mv = memoryview(self.prev_color_pages)
        self.payload_mv = memoryview(self.payload)
        self.delta_payload_mv = memoryview(self.delta_payload)


class WIC64Backend(StreamingBackend):
    """WIC-64 TCP Socket Streaming backend."""

    def __init__(self, listen_port: int = 8768):
        self.listen_port = listen_port
        self.server_sock: Optional[socket.socket] = None
        self.client_sock: Optional[socket.socket] = None
        self.client_addr = None
        self._connected = False
        self._viewer_running = False
        self.lock = threading.RLock()
        self.server_thread: Optional[threading.Thread] = None
        self.running = False

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
        self.bytes_sent = 0
        self.delta_threshold = 0.90
        self.total_ratio_sum = 0.0
        self.ratio_count = 0
        self.connection_start_time = None
        self.pool = WIC64FrameBufferPool()

    def connect(self, port=None) -> bool:
        """Start the TCP streaming server."""
        if port is not None:
            try:
                self.listen_port = int(port)
            except ValueError:
                pass

        with self.lock:
            if self.running:
                return True

            print(f"Starting WIC-64 TCP Stream server on port {self.listen_port}...")
            try:
                self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.server_sock.bind(("0.0.0.0", self.listen_port))
                self.server_sock.listen(1)
                self.server_sock.settimeout(1.0)
                self.running = True
                self._connected = True
                self._viewer_running = True # Set to True so ws_server allows stream_frame
                self.connection_start_time = time.time()
            except Exception as e:
                print(f"Failed to start WIC-64 TCP server: {e}")
                self.disconnect()
                return False

            self.server_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.server_thread.start()
            return True

    def _listen_loop(self):
        """Background thread accepting client connection from C64/WIC-64."""
        while self.running:
            try:
                sock, addr = self.server_sock.accept()
                print(f"WIC-64 Client connected from {addr}")
                with self.lock:
                    if self.client_sock:
                        try:
                            self.client_sock.close()
                        except:
                            pass
                    self.client_sock = sock
                    self.client_addr = addr
                    self.reset_stream_buffers("new client connection")
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error accepting WIC-64 connection: {e}")
                break

    def disconnect(self) -> bool:
        """Stop server and close connections."""
        with self.lock:
            self.running = False
            self._connected = False
            self._viewer_running = False

            if self.client_sock:
                try:
                    self.client_sock.close()
                except:
                    pass
                self.client_sock = None
                self.client_addr = None

            if self.server_sock:
                try:
                    self.server_sock.close()
                except:
                    pass
                self.server_sock = None

            self.connection_start_time = None
            print("WIC-64 backend disconnected.")
            return True

    def send_viewer(self, viewer_data: bytes = None) -> bool:
        """Viewer is hosted via HTTP in ws_server, returning True here."""
        print("WIC-64 viewer requested. It will be served via HTTP bootstrap.")
        return True

    def stream_frame(
        self, mode: int, bg_color: int, bitmap: bytes, screen: bytes, color: bytes
    ) -> bool:
        """Stream a single frame to the connected WIC-64 TCP client."""
        # Ensure we have an active client socket
        client = None
        with self.lock:
            client = self.client_sock

        if not client:
            # We silently consume frames if no C64 has connected yet
            return True

        with self.lock:
            try:
                mode_byte = mode & 0xFF

                # Pre-processing frame slices into memory pool arrays
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

                # Prepare full frame payload
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
                        if (changed_count / 40.0) < self.delta_threshold:
                            # Build delta payload
                            dp = self.pool.delta_payload
                            dp[0] = mode_byte
                            dp[1] = bg_color & 0xFF
                            dp[2] = 0x80  # Delta flag
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

                # Write to TCP socket client with chunk-level handshakes for VICE emulated WIC-64 compatibility
                try:
                    print(f"WIC-64 DEBUG: streaming frame {self.frame_count}. client={self.client_addr}, size={len(payload_view)}, used_delta={used_delta}")
                    
                    def send_chunk_and_wait_ack(chunk_name, chunk):
                        print(f"WIC-64 DEBUG: sending {chunk_name} ({len(chunk)} bytes)...")
                        self.client_sock.sendall(chunk)
                        print(f"WIC-64 DEBUG: waiting for {chunk_name} ACK...")
                        self.client_sock.settimeout(5.0)
                        ack = self.client_sock.recv(1)
                        self.client_sock.settimeout(None)
                        if not ack:
                            raise socket.error("Empty ACK received (client disconnected).")
                        print(f"WIC-64 DEBUG: {chunk_name} ACK received ({ack})")

                    if not used_delta:
                        # Header (4 bytes)
                        send_chunk_and_wait_ack("header", payload_view[0:4])
                        
                        # Bitmap (8000 bytes)
                        send_chunk_and_wait_ack("bitmap", payload_view[4:8004])
                        
                        curr_offset = 8004
                        if send_screen:
                            send_chunk_and_wait_ack("screen", payload_view[curr_offset : curr_offset + 1000])
                            curr_offset += 1000
                        if send_color:
                            send_chunk_and_wait_ack("color", payload_view[curr_offset : curr_offset + 1000])
                            curr_offset += 1000
                    else:
                        num_bitmap_pages = payload_view[3]
                        num_screen_pages = payload_view[4]
                        num_color_pages = payload_view[5]
                        total_pages = num_bitmap_pages + num_screen_pages + num_color_pages
                        
                        send_chunk_and_wait_ack("delta_header", payload_view[0:4])
                        send_chunk_and_wait_ack("delta_ext_header", payload_view[4:8])
                        
                        curr_offset = 8
                        for p_idx in range(total_pages):
                            # Send page header (4 bytes)
                            send_chunk_and_wait_ack(f"page_{p_idx}_header", payload_view[curr_offset : curr_offset + 4])
                            curr_offset += 4
                            # Send page data (256 bytes)
                            send_chunk_and_wait_ack(f"page_{p_idx}_data", payload_view[curr_offset : curr_offset + 256])
                            curr_offset += 256
                except Exception as socket_err:
                    print(f"WIC-64 socket send failed: {socket_err}. Client disconnected.")
                    try:
                        self.client_sock.close()
                    except:
                        pass
                    self.client_sock = None
                    self.client_addr = None
                    return False

                # Update internal state / buffer copies
                self.prev_mode = mode_byte
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

                if self.frame_count > 0 and self.frame_count % 100 == 0:
                    avg_ratio = self.total_ratio_sum / max(1, self.ratio_count)
                    print(f"[WIC-64 Metrics] Frame {self.frame_count}: avg compression ratio: {avg_ratio:.2%}, total bytes sent: {self.bytes_sent:,} bytes")

                return True

            except Exception as e:
                print(f"WIC-64 stream frame failed: {e}")
                return False

    def reset(self) -> bool:
        """Reset frame counters."""
        with self.lock:
            self.frame_count = 0
            self.bytes_sent = 0
            self.total_ratio_sum = 0.0
            self.ratio_count = 0
        return True

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
        print(f"WIC-64 stream buffers reset ({reason}); forcing two full C64 refreshes.")
        return True

    def get_status(self) -> Dict:
        """Get current status metrics."""
        client_ip = self.client_addr[0] if self.client_addr else None
        return {
            "connected": self._connected,
            "viewer_running": self._viewer_running,
            "port": self.listen_port,
            "client_ip": client_ip,
            "frame_count": self.frame_count,
            "is_viewer_running": self._viewer_running,
            "backend_name": "WIC-64 WiFi Target",
            "bytes_sent": self.bytes_sent,
            "total_ratio_sum": self.total_ratio_sum,
            "ratio_count": self.ratio_count,
            "connection_start_time": self.connection_start_time,
            "message": f"Connected to C64 client at {client_ip}"
            if client_ip
            else "Server listening. Connect C64 client.",
        }

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_viewer_running(self) -> bool:
        return self._viewer_running

    def __del__(self):
        self.disconnect()
