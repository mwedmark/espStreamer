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
        
    def setup_default(self):
        """Initial connection setup"""
        if not self.monitor.connect():
            return False
        self.monitor.resume_execution()
        return True

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
            if isinstance(message, bytes):
                # Binary payload format:
                # byte 0: mode (0=multicolor, 1=hires)
                # byte 1: background color
                # bytes 2..8001: Bitmap RAM (8000 bytes)
                # bytes 8002..9001: Screen RAM (1000 bytes)
                # bytes 9002..10001: Color RAM (1000 bytes)
                
                if len(message) < 10002:
                    print(f"Received binary payload too small: {len(message)}")
                    return
                
                mode = message[0]
                bg_color = message[1]
                bitmap = message[2:8002]
                screen = message[8002:9002]
                color = message[9002:10002]
                
                if self.simulator.monitor.sock:
                    # Write VICE registers based on mode
                    if mode == 1: # Hires
                        self.simulator.monitor.write_memory(0xD011, bytes([0x3B]), side_effects=True)
                        self.simulator.monitor.write_memory(0xD016, bytes([0xC8]), side_effects=True)
                    else: # Multicolor
                        self.simulator.monitor.write_memory(0xD011, bytes([0x3B]), side_effects=True)
                        self.simulator.monitor.write_memory(0xD016, bytes([0xD8]), side_effects=True)
                        
                    self.simulator.monitor.write_memory(0xD018, bytes([0x18]), side_effects=True)
                    self.simulator.monitor.write_memory(0xD020, bytes([0x00]), side_effects=True) # Border black
                    self.simulator.monitor.write_memory(0xD021, bytes([bg_color]), side_effects=True) # Background color
                    
                    # Write RAM blocks
                    self.simulator.monitor.write_memory(0x2000, bitmap)
                    self.simulator.monitor.write_memory(0x0400, screen)
                    success = self.simulator.monitor.write_memory(0xD800, color, side_effects=True)
                    
                    self.simulator.frame_count += 1
                    self.simulator.monitor.resume_execution()
                    
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'command': 'stream_frame',
                        'success': success,
                        'message': f'Frame {self.simulator.frame_count} (Bin) transferred to VICE' if success else 'Transfer failed'
                    }))
                else:
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'command': 'stream_frame',
                        'success': False,
                        'message': 'Not connected to VICE'
                    }))
                return

            data = json.loads(message)
            command = data.get('command')
            
            if command == 'connect':
                print("Processing connect command")
                # Connect and setup VICE
                success = self.simulator.setup_default()
                
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'connect',
                    'success': success,
                    'message': 'VICE connected' if success else 'Failed to connect to VICE binary monitor on port 6511. Make sure VICE is running with -binarymonitor.'
                }))
            
            elif command == 'stream_frame':
                # Deprecated JSON/Base64 image stream fallback
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'stream_frame',
                    'success': False,
                    'message': 'Please use binary streaming for frames'
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
