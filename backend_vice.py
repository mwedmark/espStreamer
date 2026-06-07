#!/usr/bin/env python3
"""
VICE Backend Implementation for StreamingBackend interface.
Simulates streaming to VICE via the Binary Monitor Port.
"""

from typing import Dict
import socket
import struct
import time


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
        request_id = 0x1234
        
        header = struct.pack('<BBIIB', 0x02, 0x02, body_len, request_id, 0x02)
        body = struct.pack('<BHHBH', 1 if side_effects else 0, start_addr, end_addr, 0, 0)
        
        try:
            self.sock.setblocking(False)
            while True:
                try:
                    discard = self.sock.recv(4096)
                    if not discard: break
                except:
                    break
            self.sock.setblocking(True)
            
            self.sock.sendall(header + body + data)
            
            while True:
                resp_header = b''
                while len(resp_header) < 12:
                    chunk = self.sock.recv(12 - len(resp_header))
                    if not chunk:
                        print("Connection closed by VICE")
                        self.disconnect()
                        return False
                    resp_header += chunk
                
                stx, ver, blen, ctype, err, rid = struct.unpack('<BBIBBI', resp_header)
                
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
        except Exception as e:
            print(f"Failed to write memory: {e}")
            self.disconnect()
            return False

    def resume_execution(self):
        if not self.sock:
            return False
            
        request_id = 0x1235
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
    """VICE backend implementing StreamingBackend interface."""

    def __init__(self):
        self.frame_count = 0
        self.monitor = VICEBinaryMonitor(6511)
        self._is_viewer_running = True
        self.connected = False
        self.bytes_sent = 0
        self.connection_start_time = None
        
    def connect(self, port=None):
        if not self.monitor.connect():
            return False
        self.monitor.resume_execution()
        self.connected = True
        self.connection_start_time = time.time()
        return True

    def disconnect(self):
        self.monitor.disconnect()
        self.connected = False
        self.connection_start_time = None

    def send_viewer(self, viewer_data=None):
        print(f"Would send viewer to VICE")
        return True

    def stream_frame(self, mode, bg_color, bitmap, screen, color):
        if not self.monitor.sock:
            return False
            
        if mode == 1:
            self.monitor.write_memory(0xD011, bytes([0x3B]), side_effects=True)
            self.monitor.write_memory(0xD016, bytes([0xC8]), side_effects=True)
        else:
            self.monitor.write_memory(0xD011, bytes([0x3B]), side_effects=True)
            self.monitor.write_memory(0xD016, bytes([0xD8]), side_effects=True)
            
        self.monitor.write_memory(0xD018, bytes([0x18]), side_effects=True)
        self.monitor.write_memory(0xD020, bytes([0x00]), side_effects=True)
        self.monitor.write_memory(0xD021, bytes([bg_color]), side_effects=True)
        
        self.monitor.write_memory(0x2000, bitmap)
        self.monitor.write_memory(0x0400, screen)
        success = self.monitor.write_memory(0xD800, color, side_effects=True)
        
        self.frame_count += 1
        self.bytes_sent += 10060
        self.monitor.resume_execution()
        
        return success

    def get_status(self):
        return {
            "frame_count": self.frame_count,
            "connected": self.connected,
            "is_viewer_running": self._is_viewer_running,
            "backend_name": "VICE Simulation (Binary Monitor)",
            "bytes_sent": self.bytes_sent,
            "connection_start_time": self.connection_start_time
        }

    def reset(self):
        print("Reset signal sent to VICE")
        return True

    def reset_stream_buffers(self, reason="manual"):
        print(f"Stream buffers reset ({reason}) for VICE backend")
        return True

    @property
    def is_connected(self):
        return self.connected

    @property
    def is_viewer_running(self):
        return self._is_viewer_running

    def __del__(self):
        self.disconnect()
