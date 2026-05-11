import serial
import serial.tools.list_ports
import time

def build_mini_prg():
    """Builds a minimal 'Blind Reader' PRG."""
    code = []
    code += [0x01, 0x08] # Load addr
    code += [0x0B, 0x08, 0x0A, 0x00, 0x9E, 0x32, 0x30, 0x36, 0x31, 0x00, 0x00, 0x00]
    # $080D:
    code += [0x78]              # SEI
    code += [0xA9, 0x35]        # LDA #$35
    code += [0x85, 0x01]        # STA $01
    # $0812:
    code += [0xAD, 0x0A, 0xDE]  # LDA $DE0A (KFF Data Read)
    code += [0x8D, 0x20, 0xD0]  # STA $D020 (Border)
    code += [0x4C, 0x12, 0x08]  # JMP $0812
    return bytes(code)

def run_test():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports found!")
        return

    print("Available ports:")
    for i, p in enumerate(ports):
        print(f"{i}: {p.device} ({p.description})")
    
    idx = 0
    if len(ports) > 1:
        try:
            val = input(f"Select port [0-{len(ports)-1}] (default 0): ")
            if val.strip():
                idx = int(val)
        except:
            pass
    
    port = ports[idx].device
    print(f"Connecting to {port}...")
    
    try:
        ser = serial.Serial(port, 115200, timeout=1)
        ser.dtr = True
        ser.rts = True
        time.sleep(0.1) 
    except Exception as e:
        print(f"Failed to open port: {e}")
        return

    # Write the mini PRG to disk
    prg_data = build_mini_prg()
    with open("kff_mini_test.prg", "wb") as f:
        f.write(prg_data)
    
    print("\n--- MANUAL SD CARD TEST ---")
    print("1. Copy 'kff_mini_test.prg' to your SD card.")
    print("2. Load and RUN it manually on your C64.")
    print("3. Verify the GREEN LED on the KFF is ON.")
    print("4. Press Enter here to start sending bytes.")
    input("> ")

    try:
        color = 0
        while True:
            print(f"Sending color {color}...")
            ser.write(bytes([color]))
            ser.flush()
            color = (color + 1) % 16
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        ser.close()

if __name__ == "__main__":
    run_test()
