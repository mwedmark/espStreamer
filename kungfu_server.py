#!/usr/bin/env python3
"""
Kung Fu Flash WebSocket Server
Bridges ESPStreamer web app to USB Kung Fu Flash cartridge
"""

import asyncio
import websockets
import json
import usb.core
import usb.util
import time
import numpy as np
from PIL import Image
import io
import base64

class KungFuFlashStreamer:
    def __init__(self):
        self.device = None
        self.vid = 0x0483  # Example vendor ID - replace with actual
        self.pid = 0x5740  # Example product ID - replace with actual
        self.connected = False
    
    def connect(self):
        """Connect to Kung Fu Flash device"""
        try:
            self.device = usb.core.find(idVendor=self.vid, idProduct=self.pid)
            if self.device is None:
                print("Kung Fu Flash not found")
                return False
            
            # Detach kernel driver if attached
            for cfg in self.device:
                for intf in cfg:
                    if self.device.is_kernel_driver_active(intf.bInterfaceNumber):
                        self.device.detach_kernel_driver(intf.bInterfaceNumber)
            
            self.device.set_configuration()
            self.connected = True
            print("Connected to Kung Fu Flash")
            return True
            
        except Exception as e:
            print(f"USB connection failed: {e}")
            return False
    
    def write_bank(self, bank, address, data):
        """Write data to flash bank"""
        if not self.connected:
            return False
        
        try:
            # Build command packet for standard firmware
            packet = bytearray([0x02, bank, (address >> 8) & 0xFF, address & 0xFF])
            packet.extend(data)
            
            # Send via USB bulk transfer
            bytes_written = self.device.write(0x01, packet)
            time.sleep(0.1)  # Flash programming delay
            
            return bytes_written == len(packet)
            
        except Exception as e:
            print(f"Write failed: {e}")
            return False
    
    def stream_frame(self, bitmap_data, screen_data, color_data):
        """Stream complete frame to C64"""
        if not self.connected:
            return False
        
        try:
            print(f"Streaming frame: bitmap={len(bitmap_data)}B, screen={len(screen_data)}B, color={len(color_data)}B")
            
            # Write to flash banks
            success = True
            success &= self.write_bank(0, 0x8000, bitmap_data)  # 8KB bitmap
            success &= self.write_bank(1, 0xA000, screen_data)  # 1KB screen  
            success &= self.write_bank(2, 0xE000, color_data)   # 1KB color
            
            if success:
                print("Frame sent to C64 successfully")
            else:
                print("Failed to send frame to C64")
            
            return success
            
        except Exception as e:
            print(f"Stream frame failed: {e}")
            return False
    
    def convert_image_to_c64(self, image_data):
        """Convert image data to C64 format"""
        try:
            # Decode base64 image
            image_bytes = base64.b64decode(image_data.split(',')[1])
            image = Image.open(io.BytesIO(image_bytes))
            
            # Resize to C64 dimensions
            image = image.resize((320, 200), Image.Resampling.LANCZOS)
            
            # Convert to RGB
            image = image.convert('RGB')
            
            # Simple C64 conversion (multicolor mode)
            bitmap_data = bytearray(8192)
            screen_data = bytearray(1024)
            color_data = bytearray(1024)
            
            # Fill with test pattern for now
            for i in range(8192):
                bitmap_data[i] = i % 16
            
            for i in range(1024):
                screen_data[i] = (i % 256)
                color_data[i] = (i % 16)
            
            return bytes(bitmap_data), bytes(screen_data), bytes(color_data)
            
        except Exception as e:
            print(f"Image conversion failed: {e}")
            return None, None, None

class WebSocketServer:
    def __init__(self):
        self.streamer = KungFuFlashStreamer()
        self.clients = set()
    
    async def handle_client(self, websocket, path):
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
            data = json.loads(message)
            command = data.get('command')
            
            if command == 'connect':
                success = self.streamer.connect()
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'connect',
                    'success': success,
                    'message': 'Connected' if success else 'Connection failed'
                }))
            
            elif command == 'stream_frame':
                image_data = data.get('image_data')
                if image_data:
                    bitmap, screen, color = self.streamer.convert_image_to_c64(image_data)
                    if bitmap and screen and color:
                        success = self.streamer.stream_frame(bitmap, screen, color)
                        await websocket.send(json.dumps({
                            'type': 'response',
                            'command': 'stream_frame',
                            'success': success,
                            'message': 'Frame streamed' if success else 'Stream failed'
                        }))
                    else:
                        await websocket.send(json.dumps({
                            'type': 'response',
                            'command': 'stream_frame',
                            'success': False,
                            'message': 'Image conversion failed'
                        }))
            
            elif command == 'status':
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'status',
                    'connected': self.streamer.connected,
                    'message': 'Connected' if self.streamer.connected else 'Disconnected'
                }))
            
        except Exception as e:
            print(f"Message handling failed: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': str(e)
            }))
    
    async def broadcast(self, message):
        """Broadcast message to all connected clients"""
        if self.clients:
            await asyncio.gather(
                *[client.send(message) for client in self.clients],
                return_exceptions=True
            )

async def main():
    server = WebSocketServer()
    
    print("Starting Kung Fu Flash WebSocket Server...")
    print("WebSocket server will run on ws://localhost:8765")
    
    async with websockets.serve(server.handle_client, "localhost", 8765):
        print("Server running. Press Ctrl+C to stop.")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
