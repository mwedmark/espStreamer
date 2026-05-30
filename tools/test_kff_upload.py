import serial
import serial.tools.list_ports
import time
import os

def build_mini_prg():
    """Builds the minimal border color PRG."""
    code = []
    code += [0x01, 0x08] # Load addr
    code += [0x0B, 0x08, 0x0A, 0x00, 0x9E, 0x32, 0x30, 0x36, 0x31, 0x00, 0x00, 0x00]
    # $080D:
    code += [0x78]              # SEI
    code += [0xA9, 0x35]        # LDA #$35
    code += [0x85, 0x01]        # STA $01
    # $0812:
    code += [0xAD, 0x09, 0xDE]  # LDA $DE09 (Status)
    code += [0x4A, 0x4A, 0x4A, 0x4A] # LSR x4 (Show bits 4-7)
    code += [0x8D, 0x20, 0xD0]  # STA $D020 (Border shows bits 4-7)
    code += [0x4C, 0x12, 0x08]  # JMP $0812
    return bytes(code)

def run_test():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports found!")
        return
    
    # Auto-pick the one that worked before if possible, or just ask
    idx = 0
    if len(ports) > 1:
        for i, p in enumerate(ports):
            print(f"{i}: {p.device} ({p.description})")
        val = input(f"Select port [0-{len(ports)-1}] (default 0): ")
        if val.strip(): idx = int(val)
    
    port = ports[idx].device
    print(f"Connecting to {port}...")
    
    try:
        ser = serial.Serial(port, 115200, timeout=2)
        ser.dtr = True
        ser.rts = True
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.5)
    except Exception as e:
        print(f"Failed to open port: {e}")
        return

    # 1. Handshake
    print("Sending EFSTART:PRG handshake...")
    ser.write(b'EFSTART:PRG\x00')
    resp = ser.read(5)
    if not resp or resp[0] not in [ord('L'), ord('W')]:
        print(f"Handshake failed or KFF not in menu. Got: {resp.hex()}")
        ser.close()
        return
    print(f"KFF Ready (Response: {chr(resp[0])})")

    # 2. Upload PRG
    prg_data = build_mini_prg()
    print(f"Uploading {len(prg_data)} bytes...")
    
    offset = 0
    while offset < len(prg_data):
        # KFF asks for a chunk size (2 bytes LE)
        size_req = ser.read(2)
        if len(size_req) < 2:
            print("Chunk request timeout")
            break
        
        req_len = size_req[0] + size_req[1] * 256
        if req_len == 0: break
        
        chunk = prg_data[offset : offset + req_len]
        actual_len = len(chunk)
        
        # Send actual size (2 bytes LE)
        ser.write(bytes([actual_len & 0xFF, (actual_len >> 8) & 0xFF]))
        # Send data
        ser.write(chunk)
        ser.flush()
        
        offset += actual_len
        print(f"  Sent {offset}/{len(prg_data)} bytes")

    # Send final 0-length chunk if needed
    # (KFF sometimes asks for one more if we hit exact multiple)
    ser.timeout = 0.5
    size_req = ser.read(2)
    if len(size_req) == 2:
        ser.write(b'\x00\x00')
        ser.flush()

    print("Upload complete! C64 should be running the code.")
    time.sleep(1)

    # 3. Burst Test
    print("Starting status burst test...")
    try:
        while True:
            print("Sending burst (100 bytes)...")
            ser.write(b'\x00' * 100)
            ser.flush()
            time.sleep(2)
            
            print("Idle (Waiting)...")
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        ser.close()

if __name__ == "__main__":
    run_test()
