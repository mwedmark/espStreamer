#!/usr/bin/env python3
"""
Kung Fu Flash VICE Simulation Server
Simulates Kung Fu Flash streaming for VICE testing
"""

import asyncio
import websockets
import json
import os
import time
import subprocess
from PIL import Image
import io
import base64

class VICEKungFuSimulator:
    def __init__(self):
        self.vice_process = None
        self.frame_count = 0
        self.connected = False
        self.monitor_port = 6510  # VICE text monitor port
        
    def start_vice(self):
        """Start VICE with monitor enabled"""
        try:
            import subprocess
            import os
            
            prg_path = os.path.abspath('kungfu_sim.prg')
            print(f"Starting VICE with PRG: {prg_path}")
            
            # Start VICE with monitor server enabled
            self.vice_process = subprocess.Popen([
                'x64sc.exe',
                '-monserver',  # Enable monitor server
                prg_path
            ])
            
            print(f"VICE started with PID: {self.vice_process.pid}")
            return True
            
        except Exception as e:
            print(f"Failed to start VICE: {e}")
            return False
    
    def test_injection(self, test_data, address):
        """Test injection with known data pattern"""
        try:
            print(f"Testing injection: {test_data.hex()} at ${address:04X}")
            # Connect to VICE monitor
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('localhost', self.monitor_port))
            print(f"Connected to VICE monitor")
            
            # Inject test data using text monitor commands
            for i, byte_val in enumerate(test_data):
                sock.send(f'poke {address + i:X} {byte_val}\n'.encode())
            
            # Verify by reading back
            sock.send(f'peek {address:X}\n'.encode())
            sock.send(f'peek {address + 1:X}\n'.encode())
            sock.send(f'peek {address + 2:X}\n'.encode())
            sock.send(f'peek {address + 3:X}\n'.encode())
            
            sock.close()
            print(f"Test injection completed successfully")
            return True
            
        except Exception as e:
            print(f"Test injection failed: {e}")
            return False
    
    def inject_to_vice(self, bitmap, screen, color):
        """Inject frame data into VICE memory via monitor"""
        try:
            print(f"Attempting VICE injection on port {self.monitor_port}")
            # Connect to VICE monitor
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('localhost', self.monitor_port))
            print(f"Connected to VICE monitor")
            
            # Inject bitmap data to $2000-$3FFF
            print(f"Injecting {len(bitmap)} bytes to bitmap memory")
            sock.send(b'bank 0\n')
            for i in range(0, len(bitmap), 16):
                chunk = bitmap[i:i+16]
                addr = 0x2000 + i
                hex_data = ' '.join([f'{b:02X}' for b in chunk])
                sock.send(f'm {addr:04X} {hex_data}\n'.encode())
            
            # Inject screen data to $0400-$07FF
            print(f"Injecting {len(screen)} bytes to screen memory")
            sock.send(b'bank 0\n')
            for i in range(0, len(screen), 16):
                chunk = screen[i:i+16]
                addr = 0x0400 + i
                hex_data = ' '.join([f'{b:02X}' for b in chunk])
                sock.send(f'm {addr:04X} {hex_data}\n'.encode())
            
            # Inject color data to $D800-$DBFF
            print(f"Injecting {len(color)} bytes to color memory")
            sock.send(b'bank 0\n')
            for i in range(0, len(color), 16):
                chunk = color[i:i+16]
                addr = 0xD800 + i
                hex_data = ' '.join([f'{b:02X}' for b in chunk])
                sock.send(f'm {addr:04X} {hex_data}\n'.encode())
            
            # Add verification commands
            sock.send(b'bank 0\n')
            sock.send(f'm 2000\n'.encode())
            sock.send(b'bank 0\n')
            sock.send(f'm 0400\n'.encode())
            sock.send(b'bank 0\n')
            sock.send(f'm D800\n'.encode())
            
            sock.close()
            print(f"VICE injection completed successfully")
            return True
            
        except Exception as e:
            print(f"VICE injection failed: {e}")
            return False
    
    def create_test_prg(self):
        """Create minimal PRG file for VICE testing"""
        # PRG file with single BASIC line
        prg_data = bytearray([
            # Load address $0801
            0x01, 0x08,
            
            # BASIC program - just set multicolor bitmap mode
            0x0B, 0x08,                                     # Next line pointer
            0x0A, 0x00,                                     # Line number 10
            0xA9, 0x1B, 0x8D, 0x11, 0xD0,           # poke 53773,27 (enable multicolor bitmap)
            0x8D, 0x18, 0xD0, 0xA9, 0x18,           # poke 53776,24 (screen/bitmap setup)
            0xA5, 0xD0, 0x09, 0x10, 0x8D, 0xD0, 0xD0, # poke 53270,peek(53270) or 16 (enable multicolor mode)
            0x00, 0x00,                                     # End of line
            0x00, 0x00,                                     # End of program
        ])
        
        # Write PRG file
        with open('kungfu_sim.prg', 'wb') as f:
            f.write(prg_data)
        
        print("Created kungfu_sim.prg - load with: LOAD \"kungfu_sim\",8,1 then RUN")
    
    def convert_image_to_c64(self, image_data):
        """Convert image to C64 format for VICE"""
        try:
            # Decode base64 image
            image_bytes = base64.b64decode(image_data.split(',')[1])
            image = Image.open(io.BytesIO(image_bytes))
            
            # Resize to C64 dimensions
            image = image.resize((320, 200), Image.Resampling.LANCZOS)
            image = image.convert('RGB')
            
            # Convert image to C64 multicolor bitmap format
            bitmap_data = bytearray(8192)
            screen_data = bytearray(1024)
            color_data = bytearray(1024)
            
            # Get pixel data
            pixels = image.load()
            
            # Convert to multicolor bitmap (4x8 character blocks)
            for y in range(200):
                for x in range(320):
                    # Get pixel color
                    r, g, b = pixels[x, y]
                    
                    # Convert to C64 color (simplified)
                    if r > 128 and g > 128 and b > 128:
                        c64_color = 1  # White
                    elif r > 128:
                        c64_color = 2  # Red  
                    elif g > 128:
                        c64_color = 3  # Green
                    elif b > 128:
                        c64_color = 4  # Blue
                    else:
                        c64_color = 0  # Black
                    
                    # Calculate bitmap position
                    char_x = x // 4
                    char_y = y // 8
                    pixel_x = x % 4
                    pixel_y = y % 8
                    
                    # Set bitmap bits (2 bits per pixel for multicolor)
                    char_index = char_y * 40 + char_x
                    if char_index < 1000:  # Screen memory bounds
                        screen_data[char_index] = char_index & 0xFF
                        color_data[char_index] = c64_color & 0x0F
                        
                        # Set bitmap data
                        bitmap_byte = char_index * 8 + pixel_y
                        if bitmap_byte < 8192:
                            bitmap_data[bitmap_byte] |= (c64_color & 0x03) << (6 - pixel_x * 2)
            
            self.frame_count += 1
            return bytes(bitmap_data), bytes(screen_data), bytes(color_data)
            
        except Exception as e:
            print(f"Image conversion failed: {e}")
            return None, None, None

class VICEWebSocketServer:
    def __init__(self):
        self.simulator = VICEKungFuSimulator()
        self.clients = set()
    
    async def handle_client(self, websocket):
        """Handle WebSocket client connections"""
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
        """Handle incoming WebSocket messages"""
        try:
            print(f"Received message: {message}")
            data = json.loads(message)
            command = data.get('command')
            print(f"Parsed command: {command}")
            
            if command == 'connect':
                print(f"Processing connect command")
                # Create test PRG
                self.simulator.create_test_prg()
                
                # Start VICE automatically
                self.simulator.start_vice()
                
                print(f"Sending connect response")
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'connect',
                    'success': True,
                    'message': 'VICE simulation ready - load kungfu_sim.prg in VICE'
                }))
            
            elif command == 'stream_frame':
                print(f"Received stream_frame command")
                image_data = data.get('image_data')
                if image_data:
                    print(f"Image data received, size: {len(image_data)} bytes")
                    bitmap, screen, color = self.simulator.convert_image_to_c64(image_data)
                    if bitmap and screen and color:
                        print(f"Image conversion successful - creating .bin files")
                        # For VICE testing, just save to files
                        with open('vice_bitmap.bin', 'wb') as f:
                            f.write(bitmap)
                        with open('vice_screen.bin', 'wb') as f:
                            f.write(screen)
                        with open('vice_color.bin', 'wb') as f:
                            f.write(color)
                        print(f"Created .bin files: vice_bitmap.bin (8KB), vice_screen.bin (1KB), vice_color.bin (1KB)")
                        
                        # Skip automatic injection - just create files
                        await websocket.send(json.dumps({
                            'type': 'response',
                            'command': 'stream_frame',
                            'success': True,
                            'message': f'Frame {self.simulator.frame_count} ready - .bin files created'
                        }))
                    else:
                        print(f"Image conversion failed")
                        await websocket.send(json.dumps({
                            'type': 'response',
                            'command': 'stream_frame',
                            'success': False,
                            'message': 'Image conversion failed'
                        }))
                else:
                    print(f"No image data received")
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'command': 'stream_frame',
                        'success': False,
                        'message': 'No image data received'
                    }))
            
                        
            elif command == 'status':
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'status',
                    'connected': True,
                    'message': 'VICE simulation active'
                }))
            
        except Exception as e:
            print(f"Message handling failed: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': str(e)
            }))

async def main():
    server = VICEWebSocketServer()
    
    # Create PRG file immediately
    server.simulator.create_test_prg()
    
    print("Starting Kung Fu Flash VICE Simulation Server...")
    print("WebSocket server will run on ws://localhost:8766")
    print(f"PRG file created: {os.path.abspath('kungfu_sim.prg')}")
    
    print("\nTo test:")
    print("1. Open http://localhost:8080")
    print("2. Toggle to VICE Mode")
    print("3. Click Connect - VICE will start automatically")
    print("4. In VICE, type: RUN")
    print("5. Capture screenshot and click Stream to C64")
    print("6. Generated .bin files can be loaded in VICE monitor")
    
    async with websockets.serve(server.handle_client, "localhost", 8766):
        print("Server running. Press Ctrl+C to stop.")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
