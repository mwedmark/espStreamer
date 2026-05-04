#!/usr/bin/env python3
"""
Kung Fu Flash VICE Simulation Server
Simulates streaming to VICE via the Binary Monitor Port
"""

import asyncio
import websockets
import json
import os
import struct
import socket
from PIL import Image
import io
import base64

class VICEBinaryMonitor:
    def __init__(self, port=6511):
        self.port = port
        self.sock = None
        
    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(('localhost', self.port))
            print(f"Connected to VICE binary monitor on port {self.port}")
            return True
        except Exception as e:
            print(f"Failed to connect to VICE binary monitor: {e}")
            self.sock = None
            return False

    def disconnect(self):
        if self.sock:
            self.sock.close()
            self.sock = None
            print("Disconnected from VICE binary monitor")

    def write_memory(self, start_addr, data, side_effects=False):
        if not self.sock:
            return False
        
        end_addr = start_addr + len(data) - 1
        body_len = 8 + len(data)
        
        # We will use a specific Request ID to match our response
        request_id = 0x1234
        
        # Header (Request): STX (0x02), API Version (0x02), Body Length (LE), Request ID (LE), Command Type (0x02 for MEM_SET)
        header = struct.pack('<BBIIB', 0x02, 0x02, body_len, request_id, 0x02)
        
        # Body: Side Effects, Start Addr, End Addr, Memspace (0 for Main Mem), Bank ID (0 for CPU)
        body = struct.pack('<BHHBH', 1 if side_effects else 0, start_addr, end_addr, 0, 0)
        
        try:
            # Drain any pending asynchronous events before sending our request
            self.sock.setblocking(False)
            while True:
                try:
                    discard = self.sock.recv(4096)
                    if not discard: break
                except:
                    break
            self.sock.setblocking(True)
            
            self.sock.sendall(header + body + data)
            
            # Read responses until we get the one matching our request_id
            while True:
                resp_header = b''
                while len(resp_header) < 12:
                    chunk = self.sock.recv(12 - len(resp_header))
                    if not chunk:
                        print("Connection closed by VICE")
                        self.disconnect()
                        return False
                    resp_header += chunk
                
                # Response Header: STX (1), API (1), Length (4), Type (1), Error (1), Request ID (4)
                stx, ver, blen, ctype, err, rid = struct.unpack('<BBIBBI', resp_header)
                
                # Drain the body of this response
                body_data = b''
                bytes_to_read = blen
                while bytes_to_read > 0:
                    chunk = self.sock.recv(min(bytes_to_read, 4096))
                    if not chunk: break
                    body_data += chunk
                    bytes_to_read -= len(chunk)
                
                if rid == request_id:
                    if err != 0x00:
                        print(f"VICE returned error {err} for MEM_SET")
                        return False
                    return True
                # If rid == 0xFFFFFFFF, it's an event, loop again to get our response
                
        except Exception as e:
            print(f"Failed to write memory: {e}")
            self.disconnect()
            return False

    def resume_execution(self):
        """Send MON_CMD_EXIT (0xaa) to resume VICE emulator execution"""
        if not self.sock:
            return False
            
        request_id = 0x1235
        # Header: STX (0x02), API Version (0x02), Body Length (0), Request ID (LE), Command Type (0xaa for EXIT/RESUME)
        header = struct.pack('<BBIIB', 0x02, 0x02, 0, request_id, 0xaa)
        
        try:
            self.sock.setblocking(False)
            while True:
                try:
                    discard = self.sock.recv(4096)
                    if not discard: break
                except:
                    break
            self.sock.setblocking(True)
            
            self.sock.sendall(header)
            
            while True:
                resp_header = b''
                while len(resp_header) < 12:
                    chunk = self.sock.recv(12 - len(resp_header))
                    if not chunk: return False
                    resp_header += chunk
                
                stx, ver, blen, ctype, err, rid = struct.unpack('<BBIBBI', resp_header)
                
                body_data = b''
                bytes_to_read = blen
                while bytes_to_read > 0:
                    chunk = self.sock.recv(min(bytes_to_read, 4096))
                    if not chunk: break
                    bytes_to_read -= len(chunk)
                    
                if rid == request_id or ctype == 0xaa:
                    return True
        except Exception as e:
            print(f"Failed to resume execution: {e}")
            return False

class VICEKungFuSimulator:
    def __init__(self):
        self.frame_count = 0
        self.monitor = VICEBinaryMonitor(6511)
        self.is_setup_done = False
        
    def setup_multicolor_grey(self):
        """Configure C64 for Multicolor Grey display via binary monitor"""
        if not self.monitor.connect():
            return False
            
        print("Setting up C64 Multicolor Grey mode...")
        # 1. Enable bitmap mode ($D011)
        self.monitor.write_memory(0xD011, bytes([0x3B]), side_effects=True)
        # 2. Enable multicolor mode ($D016)
        self.monitor.write_memory(0xD016, bytes([0xD8]), side_effects=True)
        # 3. Set screen to $0400, bitmap to $2000 ($D018)
        self.monitor.write_memory(0xD018, bytes([0x18]), side_effects=True)
        # 4. Set Border and Background to Black (0)
        self.monitor.write_memory(0xD020, bytes([0x00, 0x00]), side_effects=True)
        
        # 5. Fill Screen RAM with Dark Grey (11) and Medium Grey (12)
        # 11 = 0x0B, 12 = 0x0C -> 0xBC
        self.monitor.write_memory(0x0400, bytes([0xBC] * 1000), side_effects=False)
        
        # 6. Fill Color RAM with Light Grey (15)
        # 15 = 0x0F
        self.monitor.write_memory(0xD800, bytes([0x0F] * 1000), side_effects=True)
        
        self.monitor.resume_execution()
        
        print("C64 configuration complete.")
        return True
    
    def convert_image_to_grey_bitmap(self, image_data):
        """Convert base64 image to 4-color grey bitmap"""
        try:
            image_bytes = base64.b64decode(image_data.split(',')[1])
            image = Image.open(io.BytesIO(image_bytes))
            
            # Resize to 160x200 (Multicolor resolution)
            resample_filter = getattr(Image, 'Resampling', Image).LANCZOS
            image = image.resize((160, 200), resample_filter)
            image = image.convert('L') # Convert to grayscale
            
            bitmap_data = bytearray(8000)
            pixels = image.load()
            
            for y in range(200):
                for x in range(160):
                    luma = pixels[x, y]
                    
                    if luma < 42:
                        color = 0 # Black -> 00
                    elif luma < 106:
                        color = 1 # Dark Grey -> 01
                    elif luma < 153:
                        color = 2 # Medium Grey -> 10
                    else:
                        color = 3 # Light Grey -> 11
                    
                    # Calculate bitmap position
                    char_x = x // 4
                    char_y = y // 8
                    pixel_x = x % 4
                    pixel_y = y % 8
                    
                    char_index = char_y * 40 + char_x
                    bitmap_byte = char_index * 8 + pixel_y
                    
                    if bitmap_byte < 8000:
                        bitmap_data[bitmap_byte] |= (color & 0x03) << (6 - pixel_x * 2)
            
            self.frame_count += 1
            return bytes(bitmap_data)
            
        except Exception as e:
            print(f"Image conversion failed: {e}")
            return None

class VICEWebSocketServer:
    def __init__(self):
        self.simulator = VICEKungFuSimulator()
        self.clients = set()
    
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
            data = json.loads(message)
            command = data.get('command')
            
            if command == 'connect':
                print("Processing connect command")
                # Connect and setup VICE
                success = self.simulator.setup_multicolor_grey()
                
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'connect',
                    'success': success,
                    'message': 'VICE connected and configured' if success else 'Failed to connect to VICE binary monitor on port 6511. Make sure VICE is running with -binarymonitor.'
                }))
            
            elif command == 'stream_frame':
                image_data = data.get('image_data')
                if image_data:
                    # Perform full setup on first frame (ensures emulator has booted)
                    if not self.simulator.is_setup_done:
                        if self.simulator.setup_multicolor_grey():
                            self.simulator.is_setup_done = True
                        
                    try:
                        bitmap = self.simulator.convert_image_to_grey_bitmap(image_data)
                    except Exception as e:
                        bitmap = None
                        print(f"Conversion exception: {e}")
                        
                    if bitmap and self.simulator.monitor.sock:
                        # Enforce VIC-II registers every frame in case of emulator reset
                        self.simulator.monitor.write_memory(0xD011, bytes([0x3B]), side_effects=True)
                        self.simulator.monitor.write_memory(0xD016, bytes([0xD8]), side_effects=True)
                        self.simulator.monitor.write_memory(0xD018, bytes([0x18]), side_effects=True)
                        self.simulator.monitor.write_memory(0xD020, bytes([0x00, 0x00]), side_effects=True)
                        
                        # Write bitmap directly to VICE memory
                        success = self.simulator.monitor.write_memory(0x2000, bitmap)
                        
                        # Resume emulator so it actually renders the changes!
                        self.simulator.monitor.resume_execution()
                        
                        await websocket.send(json.dumps({
                            'type': 'response',
                            'command': 'stream_frame',
                            'success': success,
                            'message': f'Frame {self.simulator.frame_count} transferred to VICE' if success else 'Transfer failed: write_memory returned False'
                        }))
                    else:
                        error_msg = 'Not connected to VICE' if not self.simulator.monitor.sock else 'Image conversion returned None'
                        print(f"Stream frame failed: {error_msg}")
                        await websocket.send(json.dumps({
                            'type': 'response',
                            'command': 'stream_frame',
                            'success': False,
                            'message': error_msg
                        }))
                else:
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'command': 'stream_frame',
                        'success': False,
                        'message': 'No image data received'
                    }))
                        
            elif command == 'status':
                # Just report status, don't auto-setup during boot
                connected = self.simulator.monitor.sock is not None
                if not connected:
                    connected = self.simulator.monitor.connect()
                    
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'status',
                    'connected': connected,
                    'message': 'VICE connected' if connected else 'VICE disconnected'
                }))
            
        except Exception as e:
            print(f"Message handling failed: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': str(e)
            }))

async def main():
    server = VICEWebSocketServer()
    
    print("Starting Kung Fu Flash VICE Simulation Server...")
    print("WebSocket server will run on ws://localhost:8766")
    
    print("\nTo test:")
    print("1. Start VICE with binary monitor enabled: x64sc.exe -binarymonitor")
    print("2. Use ESPStreamer web interface to connect in VICE Mode")
    print("3. Stream frames!")
    
    async with websockets.serve(server.handle_client, "localhost", 8766):
        print("Server running. Press Ctrl+C to stop.")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
