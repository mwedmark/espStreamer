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
import struct
import time
import threading

# ---------------------------------------------------------------------------
# Embedded C64 Streamer PRG (6502 machine code)
# ---------------------------------------------------------------------------
# This PRG loads at $0801 with a BASIC SYS 2061 stub.
# It sets up multicolor bitmap mode, then enters a loop:
#   1. Send ACK byte ($FF) via $DE0A to signal "ready for frame"
#   2. Read 2 bytes: mode, bg_color
#   3. Read 8000 bytes bitmap  → $2000
#   4. Read 1000 bytes screen  → $0400
#   5. Read 1000 bytes color   → $D800
#   6. Apply VIC settings, loop
#
# USB I/O registers (EF3-compatible, exposed by KFF firmware):
#   $DE08 = USB data read
#   $DE09 = USB status (bit7: RXF# active-low, bit6: TXE# active-low)
#   $DE0A = USB data write
# ---------------------------------------------------------------------------

def _build_streamer_prg():
    """Build the C64 streamer PRG as a byte array."""
    code = []

    # --- BASIC stub: 10 SYS 2061 ---
    # Load address $0801
    code += [0x01, 0x08]
    # BASIC line: pointer $080B, line 10, SYS token, "2061", end
    code += [0x0B, 0x08, 0x0A, 0x00, 0x9E, 0x32, 0x30, 0x36, 0x31, 0x00, 0x00, 0x00]

    # --- Machine code at $080D ---
    # Init
    code += [0x78]              # SEI
    code += [0xD8]              # CLD
    code += [0xA9, 0x35]        # LDA #$35  (I/O visible, ROMs off)
    code += [0x85, 0x01]        # STA $01
    code += [0xA9, 0x03]        # LDA #$03  (VIC bank 0)
    code += [0x8D, 0x00, 0xDD]  # STA $DD00
    code += [0xA9, 0x3B]        # LDA #$3B  (bitmap mode on)
    code += [0x8D, 0x11, 0xD0]  # STA $D011
    code += [0xA9, 0xD8]        # LDA #$D8  (multicolor)
    code += [0x8D, 0x16, 0xD0]  # STA $D016
    code += [0xA9, 0x18]        # LDA #$18  (screen@$0400, bmp@$2000)
    code += [0x8D, 0x18, 0xD0]  # STA $D018
    code += [0xA9, 0x00]        # LDA #$00
    code += [0x8D, 0x20, 0xD0]  # STA $D020 (border black)
    code += [0x8D, 0x21, 0xD0]  # STA $D021 (bg black)

    # frame_loop ($082F from $080D + 0x22 = $082F)
    fl_offset = len(code)  # offset within code[] including load addr
    fl_addr = 0x0801 + fl_offset - 2  # subtract 2 for load address bytes

    # Send ACK ($FF) to PC
    code += [0xA9, 0xFF]        # LDA #$FF
    wt_off = len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09  (wait_tx)
    code += [0x70, 0xFB]        # BVS wait_tx (-5 → back to BIT)
    code += [0x8D, 0x0A, 0xDE]  # STA $DE0A

    # Read mode byte
    wm_off = len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    code += [0x30, 0xFB]        # BMI wait_mode (-5)
    code += [0xAD, 0x08, 0xDE]  # LDA $DE08
    code += [0x85, 0xFB]        # STA $FB (mode)

    # Read bg_color byte
    wb_off = len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    code += [0x30, 0xFB]        # BMI wait_bg (-5)
    code += [0xAD, 0x08, 0xDE]  # LDA $DE08
    code += [0x85, 0xFC]        # STA $FC (bg_color)

    # Apply mode: if mode==0 → multicolor ($D8), else hires ($C8)
    code += [0xA5, 0xFB]        # LDA $FB
    code += [0xF0, 0x04]        # BEQ +4 → mc_mode
    code += [0xA9, 0xC8]        # LDA #$C8 (hires)
    code += [0xD0, 0x02]        # BNE +2 → set_d016
    # mc_mode:
    code += [0xA9, 0xD8]        # LDA #$D8 (multicolor)
    # set_d016:
    code += [0x8D, 0x16, 0xD0]  # STA $D016
    code += [0xA5, 0xFC]        # LDA $FC
    code += [0x8D, 0x20, 0xD0]  # STA $D020
    code += [0x8D, 0x21, 0xD0]  # STA $D021

    # --- Helper: read N bytes from USB to ($FD),Y ---
    # We'll use inline calls. The copy_data subroutine will be at the end.
    # Parameters: $FD/$FE=dest, X=full pages, $02=tail bytes
    # We compute the subroutine address after emitting the main loop.

    # Read bitmap: 8000 bytes = 31 pages + 64 tail → $2000
    code += [0xA9, 0x00]        # LDA #$00
    code += [0x85, 0xFD]        # STA $FD
    code += [0xA9, 0x20]        # LDA #$20
    code += [0x85, 0xFE]        # STA $FE
    code += [0xA2, 0x1F]        # LDX #31
    code += [0xA9, 0x40]        # LDA #64
    code += [0x85, 0x02]        # STA $02
    jsr1_off = len(code)
    code += [0x20, 0x00, 0x00]  # JSR copy_data (placeholder)

    # Read screen: 1000 bytes = 3 pages + 232 tail → $0400
    code += [0xA9, 0x00]        # LDA #$00
    code += [0x85, 0xFD]        # STA $FD
    code += [0xA9, 0x04]        # LDA #$04
    code += [0x85, 0xFE]        # STA $FE
    code += [0xA2, 0x03]        # LDX #3
    code += [0xA9, 0xE8]        # LDA #232
    code += [0x85, 0x02]        # STA $02
    jsr2_off = len(code)
    code += [0x20, 0x00, 0x00]  # JSR copy_data (placeholder)

    # Read color: 1000 bytes = 3 pages + 232 tail → $D800
    code += [0xA9, 0x00]        # LDA #$00
    code += [0x85, 0xFD]        # STA $FD
    code += [0xA9, 0xD8]        # LDA #$D8
    code += [0x85, 0xFE]        # STA $FE
    code += [0xA2, 0x03]        # LDX #3
    code += [0xA9, 0xE8]        # LDA #232
    code += [0x85, 0x02]        # STA $02
    jsr3_off = len(code)
    code += [0x20, 0x00, 0x00]  # JSR copy_data (placeholder)

    # JMP frame_loop
    code += [0x4C, fl_addr & 0xFF, (fl_addr >> 8) & 0xFF]

    # --- copy_data subroutine ---
    sub_addr = 0x0801 + len(code) - 2
    # Patch JSR addresses
    code[jsr1_off + 1] = sub_addr & 0xFF
    code[jsr1_off + 2] = (sub_addr >> 8) & 0xFF
    code[jsr2_off + 1] = sub_addr & 0xFF
    code[jsr2_off + 2] = (sub_addr >> 8) & 0xFF
    code[jsr3_off + 1] = sub_addr & 0xFF
    code[jsr3_off + 2] = (sub_addr >> 8) & 0xFF

    # copy_data:
    code += [0xE0, 0x00]        # CPX #0
    code += [0xF0, 0x00]        # BEQ tail_only (placeholder, patch below)
    beq_patch = len(code) - 1

    # full_page_loop:
    fpl_addr = 0x0801 + len(code) - 2
    code += [0xA0, 0x00]        # LDY #0
    # full_inner:
    fi_addr = 0x0801 + len(code) - 2
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    code += [0x30, 0xFB]        # BMI full_inner (-5)
    code += [0xAD, 0x08, 0xDE]  # LDA $DE08
    code += [0x91, 0xFD]        # STA ($FD),Y
    code += [0xC8]              # INY
    # BNE full_inner: displacement = fi_addr - (current_addr + 2)
    bne_fi_addr = 0x0801 + len(code) - 2
    disp = fi_addr - (bne_fi_addr + 2)
    code += [0xD0, disp & 0xFF]  # BNE full_inner

    code += [0xE6, 0xFE]        # INC $FE
    code += [0xCA]              # DEX
    # BNE full_page_loop
    bne_fpl_addr = 0x0801 + len(code) - 2
    disp = fpl_addr - (bne_fpl_addr + 2)
    code += [0xD0, disp & 0xFF]  # BNE full_page_loop

    # tail_only:
    tail_addr = 0x0801 + len(code) - 2
    # Patch BEQ
    code[beq_patch] = (tail_addr - (sub_addr + 4)) & 0xFF

    code += [0xA5, 0x02]        # LDA $02
    code += [0xF0, 0x00]        # BEQ done (placeholder)
    beq_done_patch = len(code) - 1

    code += [0xA0, 0x00]        # LDY #0
    # tail_inner:
    ti_addr = 0x0801 + len(code) - 2
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    code += [0x30, 0xFB]        # BMI tail_inner (-5)
    code += [0xAD, 0x08, 0xDE]  # LDA $DE08
    code += [0x91, 0xFD]        # STA ($FD),Y
    code += [0xC8]              # INY
    code += [0xC4, 0x02]        # CPY $02
    # BNE tail_inner
    bne_ti_addr = 0x0801 + len(code) - 2
    disp = ti_addr - (bne_ti_addr + 2)
    code += [0xD0, disp & 0xFF]

    # done:
    done_addr = 0x0801 + len(code) - 2
    code[beq_done_patch] = (done_addr - (tail_addr + 4)) & 0xFF

    code += [0x60]              # RTS

    return bytes(code)


STREAMER_PRG = _build_streamer_prg()


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
                timeout=5,
                write_timeout=5
            )
            self.port_name = port
            self.connected = True
            self.viewer_running = False

            # Flush any stale data
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            print(f"Connected to KFF on {port}")
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
            print("Note: KFF disables its USB port when a PRG runs, so we cannot wait for an ACK.")
            self.viewer_running = True
            return True

        except Exception as e:
            print(f"Failed to send viewer PRG: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stream_frame(self, mode, bg_color, bitmap, screen, color):
        """Stream a single frame to the C64 viewer."""
        if not self.ser or not self.viewer_running:
            return False

        try:
            # Build payload: mode(1) + bg(1) + bitmap(8000) + screen(1000) + color(1000)
            payload = bytes([mode & 0xFF, bg_color & 0xFF])
            payload += bytes(bitmap[:8000])
            payload += bytes(screen[:1000])
            payload += bytes(color[:1000])

            # Pad if necessary
            while len(payload) < 10002:
                payload += b'\x00'

            # Send frame data
            self.ser.write(payload)
            self.ser.flush()

            # Wait for ACK from C64
            self.ser.timeout = 5
            ack = self.ser.read(1)
            if len(ack) == 1 and ack[0] == 0xFF:
                return True
            else:
                print(f"Frame ACK failed (got: {ack.hex() if ack else 'nothing'})")
                return False

        except Exception as e:
            print(f"Stream frame failed: {e}")
            self.viewer_running = False
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

            elif command == 'send_viewer':
                if not self.kff.connected:
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'command': 'send_viewer',
                        'success': False,
                        'message': 'Not connected. Connect first.'
                    }))
                    return

                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.kff.send_viewer_prg)
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'send_viewer',
                    'success': success,
                    'message': 'Viewer running on C64!' if success else 'Failed to send viewer. Make sure KFF is in menu mode.'
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
    print(f"Streamer PRG size: {len(STREAMER_PRG)} bytes")
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
    print("  1. Connect KFF via USB, make sure KFF menu is showing on C64")
    print("  2. Open ESPStreamer web interface")
    print("  3. Set mode to 'Hardware Mode' and click Connect")
    print("  4. Click 'Send Viewer' to boot the streaming viewer on C64")
    print("  5. Stream frames!")
    print()

    async with websockets.serve(server.handle_client, "localhost", 8765):
        print("Server running. Press Ctrl+C to stop.")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
