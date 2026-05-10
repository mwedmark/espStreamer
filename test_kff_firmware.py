import serial
import serial.tools.list_ports
import time

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
    print(f"Connecting to {port} at 115200 baud...")
    
    try:
        ser = serial.Serial(port, 115200, timeout=2)
        ser.dtr = True
        ser.rts = True
        # Flush
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.5)
    except Exception as e:
        print(f"Failed to open port: {e}")
        return

    print("\n--- Firmware Handshake Test ---")
    print("1. Ensure C64 is at the Kung Fu Flash MENU.")
    print("2. I will send 'EFSTART:PRG\\x00' and wait for a response.")
    print()

    handshake = b'EFSTART:PRG\x00'
    
    try:
        for attempt in range(5):
            print(f"Attempt {attempt+1}: Sending handshake... ", end="", flush=True)
            ser.write(handshake)
            ser.flush()
            
            resp = ser.read(5)
            if len(resp) > 0:
                char = chr(resp[0]) if 32 <= resp[0] <= 126 else '?'
                print(f"RECEIVED! Response: [{char}] ({resp.hex()})")
                if resp[0] in [ord('L'), ord('W')]:
                    print("SUCCESS! The Kung Fu Flash firmware is communicating.")
                    return
            else:
                print("Timeout. No response.")
            
            time.sleep(1)
            
        print("\nAll attempts failed. The firmware did not respond.")
        print("Things to check:")
        print("- Is the USB cable a data cable (not just charging)?")
        print("- Try a different USB port on your PC.")
        print("- Ensure no other software (like another terminal) is using the port.")

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        ser.close()

if __name__ == "__main__":
    run_test()
