import socket
import struct
import select
import time

def test():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(('localhost', 6511)) # binary monitor port
    except Exception as e:
        print("Could not connect to VICE on 6511:", e)
        return

    print("Connected to VICE binary monitor.")

    # Drain initial events (like stopped events or register dumps)
    sock.setblocking(False)
    while True:
        ready = select.select([sock], [], [], 0.5)
        if ready[0]:
            try:
                data = sock.recv(4096)
                if not data: break
                print("Drained initial bytes:", len(data))
            except:
                break
        else:
            break
            
    sock.setblocking(True)

    # Write D020 and D021 to Red (2)
    start_addr = 0xD020
    data = bytes([2, 2])
    end_addr = start_addr + len(data) - 1
    
    body_len = 8 + len(data)
    
    # Header: STX (0x02), API Version (0x02), Body Length (LE), Request ID (LE), Command Type (0x02 for MEM_SET)
    header = struct.pack('<BBIIB', 0x02, 0x02, body_len, 1234, 0x02)
    # Body: Side Effects (1=yes), Start Addr, End Addr, Memspace (0=main), Bank ID (0=CPU)
    body = struct.pack('<BHHBH', 1, start_addr, end_addr, 0, 0)
    
    print(f"Sending header ({len(header)} bytes):", header.hex())
    print(f"Sending body ({len(body)} bytes):", body.hex())
    print(f"Sending data ({len(data)} bytes):", data.hex())
    
    sock.sendall(header + body + data)
    print("Sent data, waiting for response...")
    
    # read response
    while True:
        resp_header = b''
        while len(resp_header) < 12:
            chunk = sock.recv(12 - len(resp_header))
            if not chunk:
                print("Connection closed by VICE")
                return
            resp_header += chunk
            
        print(f"Response header ({len(resp_header)} bytes):", resp_header.hex())
        stx, ver, blen, ctype, err, rid = struct.unpack('<BBIBBI', resp_header)
        print(f"Parsed Resp: STX={stx} Ver={ver} BLen={blen} CType={ctype} Err={err} RID={rid}")
        
        body_data = b''
        if blen > 0:
            bytes_to_read = blen
            while bytes_to_read > 0:
                chunk = sock.recv(min(bytes_to_read, 4096))
                if not chunk: break
                body_data += chunk
                bytes_to_read -= len(chunk)
            print("Response Body:", body_data.hex())
            
        if rid == 1234:
            print(f"Got response for our command! Error code: {err}")
            break
            
if __name__ == '__main__':
    test()
