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
    except Exception as e:
        print(f"Failed to open port: {e}")
        return

    print("--- Handshake Test ---")
    print("This test works with the updated 'kungfu_viewer.prg'.")
    print("Please make sure 'kungfu_viewer.prg' is RUNNING on your C64.")
    print("The border should be flashing.")
    print()

    try:
        while True:
            print("Sending Connect byte (0xFF)...")
            ser.write(b'\xFF')
            ser.flush()
            
            print("Reading 1 byte (waiting for ACK $FF)... ", end="", flush=True)
            ack = ser.read(1)
            if len(ack) == 1:
                print(f"SUCCESS! Received: {ack.hex()}")
                if ack[0] == 0xFF:
                    print("This is the correct ACK byte from 'kungfu_viewer.prg'.")
                    print("Now sending 10002 bytes of '1' (White border/bg)...")
                    # mode=0, bg=1, bitmap=all 1s, screen=all 1s, color=all 1s
                    payload = bytes([0, 1]) + b'\x01' * 10000
                    ser.write(payload)
                    ser.flush()
                    print("Sent. C64 should now be processing the frame.")
                else:
                    print(f"Received unexpected byte: {ack.hex()}")
            else:
                print("TIMEOUT. No data received.")
            
            print("Press Ctrl+C to stop, or wait for next attempt...")
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        ser.close()

if __name__ == "__main__":
    run_test()
