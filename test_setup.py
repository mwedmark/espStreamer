import socket
import struct
import select

def write_memory(sock, start_addr, data, side_effects=False):
    end_addr = start_addr + len(data) - 1
    body_len = 8 + len(data)
    request_id = 0x1234
    
    header = struct.pack('<BBIIB', 0x02, 0x02, body_len, request_id, 0x02)
    body = struct.pack('<BHHBH', 1 if side_effects else 0, start_addr, end_addr, 0, 0)
    
    sock.setblocking(False)
    while True:
        try:
            discard = sock.recv(4096)
            if not discard: break
        except:
            break
    sock.setblocking(True)
    
    sock.sendall(header + body + data)
    
    while True:
        resp_header = b''
        while len(resp_header) < 12:
            chunk = sock.recv(12 - len(resp_header))
            if not chunk: return False
            resp_header += chunk
        
        stx, ver, blen, ctype, err, rid = struct.unpack('<BBIBBI', resp_header)
        
        body_data = b''
        bytes_to_read = blen
        while bytes_to_read > 0:
            chunk = sock.recv(min(bytes_to_read, 4096))
            if not chunk: break
            bytes_to_read -= len(chunk)
            
        if rid == request_id:
            return True

def resume_execution(sock):
    request_id = 0x1235
    header = struct.pack('<BBIIB', 0x02, 0x02, 0, request_id, 0xaa)
    sock.sendall(header)
    print("Sent resume.")
    while True:
        resp_header = b''
        while len(resp_header) < 12:
            chunk = sock.recv(12 - len(resp_header))
            if not chunk: return False
            resp_header += chunk
        
        stx, ver, blen, ctype, err, rid = struct.unpack('<BBIBBI', resp_header)
        print(f"Resume response: CType={ctype} Err={err} RID={rid}")
        
        body_data = b''
        bytes_to_read = blen
        while bytes_to_read > 0:
            chunk = sock.recv(min(bytes_to_read, 4096))
            if not chunk: break
            bytes_to_read -= len(chunk)
            
        if rid == request_id or ctype == 0xaa or ctype == 0x63:
            return True

def test_setup():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(('localhost', 6511))
    except Exception as e:
        print("Could not connect:", e)
        return
        
    print("Connected!")
    write_memory(sock, 0xD020, bytes([5, 5]), True)
    resume_execution(sock)
    print("Resumed!")

if __name__ == '__main__':
    test_setup()
