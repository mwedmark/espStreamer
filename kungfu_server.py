#!/usr/bin/env python3
"""
Kung Fu Flash WebSocket Server
Bridges ESPStreamer web app to real Kung Fu Flash cartridge via EF3 USB protocol.
Uses CDC serial port (pyserial) and EFSTART:PRG handshake.
"""

import asyncio
import websockets
import json
import serial
import serial.tools.list_ports
import time
import threading
import base64

# Machine code functions (add_rel, _build_streamer_code, etc.) are now in streamer_machinecode.py
from streamer_machinecode import STREAMER_PRG, STREAMER_CRT

# Export viewer binaries to disk for direct use
with open("kungfu_viewer.prg", "wb") as f:
    f.write(STREAMER_PRG)

with open("kungfu_viewer.crt", "wb") as f:
    f.write(STREAMER_CRT)


# ---------------------------------------------------------------------------
# Kung Fu Flash Serial Interface
# ---------------------------------------------------------------------------

class KungFuFlashSerial:
    """Communicates with KFF via CDC serial port using EF3 USB protocol."""

    def __init__(self):
        self.ser = None
        self.port_name = None
        self.connected = False
        self.viewer_running = False
        self.lock = threading.Lock()
        self.prev_mode = None
        self.prev_screen = None
        self.prev_color = None
        self.screen_refresh_frames = 0
        self.full_refresh_frames = 0
        self.next_buffer = 1
        self.bitmap_buffers = [None, None]
        self.screen_buffers = [None, None]

    def reset_stream_buffers(self, reason="manual"):
        """Invalidate host-side history and force both C64 banks to be rewritten."""
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

    @staticmethod
    def find_kff_port():
        """Try to auto-detect KFF serial port (CDC/ACM device)."""
        ports = serial.tools.list_ports.comports()
        candidates = []
        for p in ports:
            desc = (p.description or '').lower()
            # KFF shows as "USB Serial Device" or "Serial USB device"
            if 'serial' in desc or 'acm' in desc or 'cdc' in desc:
                candidates.append(p.device)
            # STM32 VCP
            if p.vid == 0x0483:
                candidates.append(p.device)
        return candidates

    def connect(self, port=None):
        """Connect to KFF serial port."""
        try:
            if port is None:
                candidates = self.find_kff_port()
                if not candidates:
                    print("No KFF serial port found. Available ports:")
                    for p in serial.tools.list_ports.comports():
                        print(f"  {p.device}: {p.description} (VID={p.vid} PID={p.pid})")
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
                write_timeout=2
            )
            self.ser.dtr = True
            self.ser.rts = True
            self.port_name = port
            self.connected = True
            self.viewer_running = True # Assume viewer is started manually
            self.prev_mode = None
            self.prev_screen = None
            self.prev_color = None
            self.screen_refresh_frames = 0
            self.full_refresh_frames = 0
            self.next_buffer = 1
            self.bitmap_buffers = [None, None]
            self.screen_buffers = [None, None]

            # Do NOT flush input buffer because C64 might have already sent a chunk request!
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
        self.connected = False
        self.viewer_running = False
        self.prev_mode = None
        self.prev_screen = None
        self.prev_color = None
        self.screen_refresh_frames = 0
        self.full_refresh_frames = 0
        self.next_buffer = 1
        self.bitmap_buffers = [None, None]
        self.screen_buffers = [None, None]
        print("Disconnected from KFF")

    def send_viewer_prg(self, prg_file="viewer.prg"):
        """Send the streamer PRG to KFF via EFSTART:PRG handshake."""
        if not self.ser:
            return False

        try:
            import os
            # Flush
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.1)

            if os.path.exists(prg_file):
                print(f"Found {prg_file} on disk, loading custom PRG...")
                with open(prg_file, "rb") as f:
                    prg_data = f.read()
            else:
                print(f"Using internal STREAMER_PRG...")
                prg_data = STREAMER_PRG
            print(f"Sending streamer PRG ({len(prg_data)} bytes) via EFSTART:PRG...")

            # --- EFSTART:PRG handshake ---
            max_retries = 10
            for attempt in range(max_retries):
                # Send handshake string
                handshake = b'EFSTART:PRG\x00'
                self.ser.write(handshake)
                self.ser.flush()

                # Read 5-byte response
                resp = self.ser.read(5)
                if len(resp) < 5:
                    print(f"  Handshake timeout (got {len(resp)} bytes)")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    return False

                print(f"  Response: [{chr(resp[0]) if resp[0] > 31 else '?'}] ({resp.hex()})")

                if resp[0] == ord('W'):
                    print("  KFF waiting, retrying...")
                    time.sleep(1)
                    continue
                elif resp[0] == ord('L'):
                    print("  KFF ready to load!")
                    break
                else:
                    print(f"  Unexpected response: {resp}")
                    return False
            else:
                print("  Max retries reached")
                return False

            # --- Send PRG data in chunks ---
            offset = 0
            while offset < len(prg_data):
                # Read chunk size request (2 bytes LE)
                size_req = self.ser.read(2)
                if len(size_req) < 2:
                    print(f"  Chunk size request timeout")
                    return False

                chunk_size = size_req[0] + size_req[1] * 256
                if chunk_size == 0:
                    break

                # Prepare chunk
                remaining = len(prg_data) - offset
                actual_size = min(chunk_size, remaining)
                chunk = prg_data[offset:offset + actual_size]

                # Send actual size (2 bytes LE)
                self.ser.write(bytes([actual_size & 0xFF, (actual_size >> 8) & 0xFF]))
                # Send data
                self.ser.write(chunk)
                self.ser.flush()

                offset += actual_size
                print(f"  Sent {offset}/{len(prg_data)} bytes")

            # If the file size was an exact multiple of the requested chunk size,
            # KFF will request another chunk. We must send a 0-length response.
            if offset >= len(prg_data) and actual_size == chunk_size:
                try:
                    self.ser.timeout = 0.5
                    size_req = self.ser.read(2)
                    if len(size_req) == 2:
                        self.ser.write(bytes([0x00, 0x00]))
                        self.ser.flush()
                except:
                    pass

            print("Streamer PRG sent successfully!")
            print("Kung Fu Flash has now launched the PRG.")
            print("Waiting for frames...")
            time.sleep(0.5)
            # Do not flush here: the freshly launched viewer may already have
            # sent its first 2-byte chunk request while we were waiting.
            self.viewer_running = True
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

    def stream_frame(self, mode, bg_color, bitmap, screen, color):
        """Stream a single frame to the C64 viewer using chunked flow."""
        if not self.ser or not self.viewer_running:
            return False

        with self.lock:
            try:
                mode_byte = mode & 0xFF
                bitmap_data = bytes(bitmap[:8000]).ljust(8000, b'\x00')
                screen_data = bytes(screen[:1000]).ljust(1000, b'\x00')
                color_data = bytes(color[:1000]).ljust(1000, b'\x00')
                bitmap_pages = bitmap_data.ljust(8192, b'\x00')
                screen_pages = screen_data.ljust(1024, b'\x00')
                color_pages = color_data.ljust(1024, b'\x00')

                mode_changed = self.prev_mode != mode_byte
                if mode_changed:
                    self.full_refresh_frames = max(self.full_refresh_frames, 2)

                force_full_refresh = self.full_refresh_frames > 0
                screen_changed = mode_changed or self.prev_screen != screen_data
                color_changed = mode_changed or self.prev_color != color_data

                if screen_changed:
                    # Screen RAM is double-buffered, so update both banks.
                    self.screen_refresh_frames = 2

                send_screen = force_full_refresh or self.screen_refresh_frames > 0
                send_color = force_full_refresh or color_changed

                flags = (0x01 if send_screen else 0x00) | (0x02 if send_color else 0x00)
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
                    bitmap_records = page_records(bitmap_pages, self.bitmap_buffers[target_buffer], 32)
                    screen_records = page_records(screen_pages, self.screen_buffers[target_buffer], 4)
                    color_records = page_records(color_pages, self.prev_color.ljust(1024, b'\x00') if self.prev_color else None, 4)

                    if bitmap_records is not None and screen_records is not None and color_records is not None:
                        delta_payload = bytes([mode_byte, bg_color & 0xFF, 0x80, len(bitmap_records)])
                        delta_payload += bytes([len(screen_records), len(color_records), 0, 0])
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
                    # Read chunk request from C64 (2 bytes LE)
                    req = self.ser.read(2)
                    if len(req) < 2:
                        print(f"Chunk request timeout at offset {offset}. C64 did not request more data.")
                        return False
                    else:
                        chunk_size = req[0] + req[1] * 256
                        
                    if chunk_size == 0:
                        print("C64 requested 0 bytes? Ignoring and trying again...")
                        continue
                        
                    remaining = len(payload) - offset
                    actual_size = min(chunk_size, remaining)
                    chunk = payload[offset:offset+actual_size]
                    
                    # Send actual size
                    self.ser.write(bytes([actual_size & 0xFF, (actual_size >> 8) & 0xFF]))
                    # Send chunk
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

                return True

            except Exception as e:
                print(f"Stream frame failed: {e}")
                return False

    def reset_to_menu(self):
        """Reset KFF to menu by opening at 1200 baud."""
        if self.ser:
            port = self.port_name
            self.disconnect()
            try:
                # Opening at 1200 baud triggers reset (Arduino-style)
                s = serial.Serial(port=port, baudrate=1200)
                time.sleep(0.5)
                s.close()
                print("Reset signal sent to KFF")
                time.sleep(2)
            except Exception as e:
                print(f"Reset failed: {e}")


# ---------------------------------------------------------------------------
# WebSocket Server
# ---------------------------------------------------------------------------

class WebSocketServer:
    def __init__(self):
        self.kff = KungFuFlashSerial()
        self.clients = set()
        self.frame_count = 0

    async def handle_client(self, websocket):
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
        try:
            if isinstance(message, bytes):
                # Binary frame payload (same format as VICE server)
                if len(message) < 10002:
                    print(f"Binary payload too small: {len(message)}")
                    return

                mode = message[0]
                bg_color = message[1]
                bitmap = message[2:8002]
                screen = message[8002:9002]
                color = message[9002:10002]

                if self.kff.viewer_running:
                    # Run serial I/O in thread to avoid blocking asyncio
                    loop = asyncio.get_event_loop()
                    success = await loop.run_in_executor(
                        None, self.kff.stream_frame,
                        mode, bg_color, bitmap, screen, color
                    )

                    self.frame_count += 1
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'command': 'stream_frame',
                        'success': success,
                        'message': f'Frame {self.frame_count} sent to C64' if success else 'Frame failed'
                    }))
                else:
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'command': 'stream_frame',
                        'success': False,
                        'message': 'Viewer not running. Send viewer PRG first.'
                    }))
                return

            # JSON commands
            data = json.loads(message)
            command = data.get('command')

            if command == 'connect':
                port = data.get('port', None)
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.kff.connect, port)
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'connect',
                    'success': success,
                    'message': f'Connected to {self.kff.port_name}' if success else 'Connection failed. Check COM port.'
                }))

            elif command == 'get_viewer':
                # Send the generated PRG as base64
                encoded_prg = base64.b64encode(STREAMER_PRG).decode('utf-8')
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'get_viewer',
                    'success': True,
                    'prg_data': encoded_prg,
                    'filename': 'kungfu_viewer.prg'
                }))

            elif command == 'send_viewer':
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.kff.send_viewer_prg, "kungfu_viewer.prg")
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'send_viewer',
                    'success': success,
                    'message': 'Viewer sent successfully and is running!' if success else 'Failed to send viewer. Ensure KFF is in menu.'
                }))

            elif command == 'status':
                ports = KungFuFlashSerial.find_kff_port()
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'status',
                    'connected': self.kff.connected,
                    'viewer_running': self.kff.viewer_running,
                    'port': self.kff.port_name,
                    'available_ports': ports,
                    'message': ('Streaming' if self.kff.viewer_running else
                               'Connected' if self.kff.connected else 'Disconnected')
                }))

            elif command == 'reset':
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.kff.reset_to_menu)
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'reset',
                    'success': True,
                    'message': 'Reset signal sent'
                }))

            elif command == 'reset_buffers':
                mode = data.get('mode', 'unknown')
                self.kff.reset_stream_buffers(f"mode change to {mode}")
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'reset_buffers',
                    'success': True,
                    'message': 'C64 stream buffers will be fully refreshed'
                }))

            elif command == 'list_ports':
                ports = []
                for p in serial.tools.list_ports.comports():
                    ports.append({
                        'device': p.device,
                        'description': p.description,
                        'vid': p.vid,
                        'pid': p.pid
                    })
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'list_ports',
                    'ports': ports
                }))

            elif command == 'stream_frame':
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'stream_frame',
                    'success': False,
                    'message': 'Please use binary streaming for frames'
                }))

        except Exception as e:
            print(f"Message handling failed: {e}")
            import traceback
            traceback.print_exc()
            await websocket.send(json.dumps({
                'type': 'error',
                'message': str(e)
            }))


async def main():
    server = WebSocketServer()

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

    async with websockets.serve(server.handle_client, "localhost", 8765):
        print("Server running. Press Ctrl+C to stop.")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
