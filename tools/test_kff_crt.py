import struct
import serial
import serial.tools.list_ports
import time

def build_ef_crt():
    """Builds a minimal 16KB EasyFlash CRT with the Blind Reader code."""
    # CRT Header
    header = b"C64 CARTRIDGE   "
    header += struct.pack(">I", 0x40)    # Header size
    header += struct.pack(">H", 0x0100)  # Version
    header += struct.pack(">H", 32)      # EasyFlash type
    header += b"\x00"                    # EXROM
    header += b"\x00"                    # GAME
    header += b"\x00" * 6                # Reserved
    header += b"KFF MINI TEST".ljust(32, b"\x00")

    # CHIP Packet (16KB Bank 0)
    # Code starts at $8000
    rom_data = bytearray(16384)
    
    # Cold start vectors at $BFFC
    rom_data[0x3FFC] = 0x00
    rom_data[0x3FFD] = 0x80
    rom_data[0x3FFE] = 0x00
    rom_data[0x3FFF] = 0x80
    
    # CBM signature at $8000
    rom_data[0:9] = b"\x00\x80\x00\x80\xC3\xC2\xCD\x38\x30"
    
    # Code at $8009
    # SEI, LDA #$35, STA $01
    code = [0x78, 0xA9, 0x35, 0x85, 0x01]
    # LDA #$00, STA $D020, STA $D021
    code += [0xA9, 0x00, 0x8D, 0x20, 0xD0, 0x8D, 0x21, 0xD0]
    # Loop: LDA $DE08, STA $D020, JMP Loop
    code += [0xAD, 0x08, 0xDE, 0x8D, 0x20, 0xD0, 0x4C, 0x16, 0x80]
    
    rom_data[0x09 : 0x09 + len(code)] = bytes(code)
    
    chip_header = b"CHIP"
    chip_header += struct.pack(">I", 16384 + 0x10) # Packet size
    chip_header += struct.pack(">H", 0x0000)        # ROM type
    chip_header += struct.pack(">H", 0x0000)        # Bank
    chip_header += struct.pack(">H", 0x8000)        # Load addr
    chip_header += struct.pack(">H", 16384)         # Size
    
    return header + chip_header + rom_data

def run_test():
    # 1. Generate CRT
    crt_data = build_ef_crt()
    with open("kff_mini_test.crt", "wb") as f:
        f.write(crt_data)
    print("Created 'kff_mini_test.crt'.")

    # 2. Serial Setup
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports found!")
        return
    
    idx = 0
    if len(ports) > 1:
        for i, p in enumerate(ports):
            print(f"{i}: {p.device} ({p.description})")
        val = input(f"Select port [0-{len(ports)-1}] (default 0): ")
        if val.strip(): idx = int(val)
    
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

    print("\n--- EASYFLASH CRT TEST ---")
    print("1. Copy 'kff_mini_test.crt' to your SD card.")
    print("2. Load it as an EasyFlash cartridge on your C64.")
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
