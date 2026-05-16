#!/usr/bin/env python3
"""
Kung Fu Flash WebSocket Server
Bridges ESPStreamer web app to real Kung Fu Flash cartridge via EF3 USB protocol.
Uses CDC serial port (pyserial) and EFSTART:PRG handshake.
"""

import asyncio
import websockets
import json
import serial
import serial.tools.list_ports
import struct
import time
import threading
import base64

# ---------------------------------------------------------------------------
# Embedded C64 Streamer PRG (6502 machine code)
# ---------------------------------------------------------------------------
# This PRG loads at $0801 with a BASIC SYS 2061 stub.
# It sets up multicolor bitmap mode, then enters a loop:
#   1. Send ACK byte ($FF) via $DE0A to signal "ready for frame"
#   2. Read 2 bytes: mode, bg_color
#   3. Read 8000 bytes bitmap  → $2000
#   4. Read 1000 bytes screen  → $0400
#   5. Read 1000 bytes color   → $D800
#   6. Apply VIC settings, loop
#
# USB I/O registers (EF3-compatible, exposed by KFF firmware):
#   $DE08 = USB data read
#   $DE09 = USB status (bit7: RXF# active-low, bit6: TXE# active-low)
#   $DE0A = USB data write
# ---------------------------------------------------------------------------

def add_rel(code, opcode, target_addr, current_addr):
    disp = target_addr - (current_addr + 2)
    if disp < -128 or disp > 127:
        raise ValueError(f"Branch out of range: {disp}")
    code += [opcode, disp & 0xFF]

def _build_streamer_code(base_addr):
    """Build the C64 streamer machine code using EasyFlash 3 chunked request protocol."""
    code = []

    # --- Machine Code Start ---
    code += [0x78] # SEI
    code += [0xD8] # CLD
    code += [0xA9, 0x35, 0x85, 0x01] # I/O visible

    # Set CIA2 data direction: bits 0-1 as output for VIC bank select
    code += [0xAD, 0x02, 0xDD] # LDA $DD02
    code += [0x09, 0x03]       # ORA #$03
    code += [0x8D, 0x02, 0xDD] # STA $DD02

    # Set VIC to bank 0 ($0000-$3FFF): DD00 bits 0-1 = 11
    code += [0xAD, 0x00, 0xDD] # LDA $DD00
    code += [0x09, 0x03]       # ORA #$03
    code += [0x8D, 0x00, 0xDD] # STA $DD00

    # Double buffer flag at $03:
    #   0 = displaying bank 0, next write goes to bank 1 (back)
    #   1 = displaying bank 1, next write goes to bank 0 (back)
    code += [0xA9, 0x00, 0x85, 0x03] # LDA #0; STA $03

    # Define jump over subroutines
    jmp_start = base_addr + len(code)
    code += [0x4C, 0x00, 0x00] # JMP main_loop
    
    # --- Subroutine: ef3usb_fread (4x Unrolled + SMC) ---
    # Expects X = size low, Y = size high, $FC = buffer ptr
    fread_addr = base_addr + len(code)
    
    # wait_usb_tx_ok
    wait_tx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE] # BIT $DE09
    add_rel(code, 0x50, wait_tx_1, base_addr + len(code)) # BVC
    code += [0x8E, 0x0A, 0xDE] # STX $DE0A
    
    # wait_usb_tx_ok
    wait_tx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE] # BIT $DE09
    add_rel(code, 0x50, wait_tx_2, base_addr + len(code)) # BVC
    code += [0x8C, 0x0A, 0xDE] # STY $DE0A
    
    # wait_usb_rx_ok
    wait_rx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE] # BIT $DE09
    add_rel(code, 0x10, wait_rx_1, base_addr + len(code)) # BPL
    code += [0xAE, 0x0A, 0xDE, 0x86, 0x04] # LDX $DE0A, STX $04
    
    # wait_usb_rx_ok
    wait_rx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE] # BIT $DE09
    add_rel(code, 0x10, wait_rx_2, base_addr + len(code)) # BPL
    code += [0xAC, 0x0A, 0xDE, 0x84, 0x05] # LDY $DE0A, STY $05
    
    # Divide size by 4 to get iteration count (multiples of 4 guaranteed)
    code += [0x46, 0x05, 0x66, 0x04] # LSR $05, ROR $04
    code += [0x46, 0x05, 0x66, 0x04] # LSR $05, ROR $04

    # Setup EOR counting
    code += [0xA5, 0x04, 0x49, 0xFF, 0xAA] # LDA $04, EOR #$FF, TAX
    code += [0xA5, 0x05, 0x49, 0xFF, 0x85, 0xFE] # LDA $05, EOR #$FF, STA $FE
    
    # Initialize SMC base addresses (Low byte)
    code += [0xA5, 0xFC] # LDA $FC
    smc_lo_patches = []
    smc_hi_patches = []
    
    code += [0x8D, 0x00, 0x00] # STA smc1+1
    smc_lo_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00] # STA smc2+1
    smc_lo_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00] # STA smc3+1
    smc_lo_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00] # STA smc4+1
    smc_lo_patches.append(len(code) - 2)
    
    # Initialize SMC base addresses (High byte)
    code += [0xA5, 0xFD] # LDA $FD
    code += [0x8D, 0x00, 0x00] # STA smc1+2
    smc_hi_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00] # STA smc2+2
    smc_hi_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00] # STA smc3+2
    smc_hi_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00] # STA smc4+2
    smc_hi_patches.append(len(code) - 2)
    
    code += [0xA0, 0x00] # LDY #0
    
    # Jump into the decrement logic to start the EOR count properly
    jmp_inc_fwd = len(code)
    code += [0x4C, 0x00, 0x00] # JMP incCounter

    # --- Inner Unrolled Loop ---
    get_bytes_addr = base_addr + len(code)
    
    smc_inst_addrs = []
    for i in range(4):
        # wait_usb_rx_ok
        wait_rx = base_addr + len(code)
        code += [0x2C, 0x09, 0xDE] # BIT $DE09
        add_rel(code, 0x10, wait_rx, base_addr + len(code)) # BPL
        
        code += [0xAD, 0x0A, 0xDE] # LDA $DE0A
        
        # STA abs,Y (SMC instruction)
        smc_inst_addrs.append(base_addr + len(code))
        code += [0x99, 0x00, 0x00] # STA $0000,Y
        
        code += [0xC8] # INY
        
    # Check if Y wrapped to 0 (page boundary)
    bne_page = len(code)
    code += [0xD0, 0x00] # BNE skip_page_inc
    
    # INC high bytes
    for i in range(4):
        code += [0xEE, (smc_inst_addrs[i] + 2) & 0xFF, (smc_inst_addrs[i] + 2) >> 8] # INC smc+2
        
    skip_page_addr = base_addr + len(code)
    code[bne_page + 1] = (skip_page_addr - (base_addr + bne_page + 2)) & 0xFF
    
    # incCounter
    inc_counter_addr = base_addr + len(code)
    code[jmp_inc_fwd + 1] = inc_counter_addr & 0xFF
    code[jmp_inc_fwd + 2] = (inc_counter_addr >> 8) & 0xFF
    
    code += [0xE8] # INX
    add_rel(code, 0xD0, get_bytes_addr, base_addr + len(code)) # BNE get_bytes
    code += [0xE6, 0xFE] # INC $FE
    add_rel(code, 0xD0, get_bytes_addr, base_addr + len(code)) # BNE get_bytes
    
    code += [0x60] # RTS
    
    # Patch SMC initialization
    for i in range(4):
        code[smc_lo_patches[i]] = (smc_inst_addrs[i] + 1) & 0xFF
        code[smc_lo_patches[i] + 1] = (smc_inst_addrs[i] + 1) >> 8
        code[smc_hi_patches[i]] = (smc_inst_addrs[i] + 2) & 0xFF
        code[smc_hi_patches[i] + 1] = (smc_inst_addrs[i] + 2) >> 8

    # --- Subroutine: ef3usb_fread8 (8x Unrolled + SMC) ---
    # Same protocol as fread, for large transfers that are multiples of 8.
    fread8_addr = base_addr + len(code)

    wait_tx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE] # BIT $DE09
    add_rel(code, 0x50, wait_tx_1, base_addr + len(code)) # BVC
    code += [0x8E, 0x0A, 0xDE] # STX $DE0A

    wait_tx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE] # BIT $DE09
    add_rel(code, 0x50, wait_tx_2, base_addr + len(code)) # BVC
    code += [0x8C, 0x0A, 0xDE] # STY $DE0A

    wait_rx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE] # BIT $DE09
    add_rel(code, 0x10, wait_rx_1, base_addr + len(code)) # BPL
    code += [0xAE, 0x0A, 0xDE, 0x86, 0x04] # LDX $DE0A, STX $04

    wait_rx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE] # BIT $DE09
    add_rel(code, 0x10, wait_rx_2, base_addr + len(code)) # BPL
    code += [0xAC, 0x0A, 0xDE, 0x84, 0x05] # LDY $DE0A, STY $05

    # Divide size by 8 to get iteration count.
    code += [0x46, 0x05, 0x66, 0x04] # LSR $05, ROR $04
    code += [0x46, 0x05, 0x66, 0x04] # LSR $05, ROR $04
    code += [0x46, 0x05, 0x66, 0x04] # LSR $05, ROR $04

    code += [0xA5, 0x04, 0x49, 0xFF, 0xAA] # LDA $04, EOR #$FF, TAX
    code += [0xA5, 0x05, 0x49, 0xFF, 0x85, 0xFE] # LDA $05, EOR #$FF, STA $FE

    code += [0xA5, 0xFC] # LDA $FC
    smc8_lo_patches = []
    smc8_hi_patches = []
    for i in range(8):
        code += [0x8D, 0x00, 0x00] # STA smc+1
        smc8_lo_patches.append(len(code) - 2)

    code += [0xA5, 0xFD] # LDA $FD
    for i in range(8):
        code += [0x8D, 0x00, 0x00] # STA smc+2
        smc8_hi_patches.append(len(code) - 2)

    code += [0xA0, 0x00] # LDY #0

    jmp8_inc_fwd = len(code)
    code += [0x4C, 0x00, 0x00] # JMP incCounter

    get8_bytes_addr = base_addr + len(code)
    smc8_inst_addrs = []
    for i in range(8):
        wait_rx = base_addr + len(code)
        code += [0x2C, 0x09, 0xDE] # BIT $DE09
        add_rel(code, 0x10, wait_rx, base_addr + len(code)) # BPL

        code += [0xAD, 0x0A, 0xDE] # LDA $DE0A
        smc8_inst_addrs.append(base_addr + len(code))
        code += [0x99, 0x00, 0x00] # STA $0000,Y
        code += [0xC8] # INY

    bne8_page = len(code)
    code += [0xD0, 0x00] # BNE skip_page_inc

    for i in range(8):
        code += [0xEE, (smc8_inst_addrs[i] + 2) & 0xFF, (smc8_inst_addrs[i] + 2) >> 8] # INC smc+2

    skip8_page_addr = base_addr + len(code)
    code[bne8_page + 1] = (skip8_page_addr - (base_addr + bne8_page + 2)) & 0xFF

    inc8_counter_addr = base_addr + len(code)
    code[jmp8_inc_fwd + 1] = inc8_counter_addr & 0xFF
    code[jmp8_inc_fwd + 2] = (inc8_counter_addr >> 8) & 0xFF

    code += [0xE8] # INX
    add_rel(code, 0xD0, get8_bytes_addr, base_addr + len(code)) # BNE get_bytes
    code += [0xE6, 0xFE] # INC $FE
    beq8_done = len(code)
    code += [0xF0, 0x00] # BEQ done
    code += [0x4C, get8_bytes_addr & 0xFF, (get8_bytes_addr >> 8) & 0xFF] # JMP get_bytes
    done8_addr = base_addr + len(code)
    code[beq8_done + 1] = (done8_addr - (base_addr + beq8_done + 2)) & 0xFF
    code += [0x60] # RTS

    for i in range(8):
        code[smc8_lo_patches[i]] = (smc8_inst_addrs[i] + 1) & 0xFF
        code[smc8_lo_patches[i] + 1] = (smc8_inst_addrs[i] + 1) >> 8
        code[smc8_hi_patches[i]] = (smc8_inst_addrs[i] + 2) & 0xFF
        code[smc8_hi_patches[i] + 1] = (smc8_inst_addrs[i] + 2) >> 8

    # --- Main Loop (Double Buffered) ---
    # Bank 0: Bitmap $2000, Screen $0400
    # Bank 1: Bitmap $6000, Screen $4400
    # Color RAM $D800 is hardware-fixed (always same)
    main_loop_addr = base_addr + len(code)
    # Patch JMP over subroutines
    code[jmp_start - base_addr + 1] = main_loop_addr & 0xFF
    code[jmp_start - base_addr + 2] = (main_loop_addr >> 8) & 0xFF

    # Read Mode and BG color (4 bytes) -> $0200
    code += [0xA9, 0x00, 0x85, 0xFC] # $FC = $00
    code += [0xA9, 0x02, 0x85, 0xFD] # $FD = $02
    code += [0xA2, 0x04, 0xA0, 0x00] # X = 4, Y = 0 (4 bytes)
    code += [0x20, fread_addr & 0xFF, (fread_addr >> 8) & 0xFF]

    # Determine back buffer based on flag at $03
    # $06 = bitmap dest high byte, $07 = screen dest high byte
    code += [0xA5, 0x03]       # LDA $03
    bne_bank0 = base_addr + len(code)
    code += [0xD0, 0x00]       # BNE write_bank0 (patch later)

    # Flag=0: displaying bank 0, write to bank 1
    code += [0xA9, 0x60, 0x85, 0x06] # LDA #$60; STA $06 (bitmap -> $6000)
    code += [0xA9, 0x44, 0x85, 0x07] # LDA #$44; STA $07 (screen -> $4400)
    jmp_do_reads = base_addr + len(code)
    code += [0x4C, 0x00, 0x00]       # JMP do_reads (patch later)

    # write_bank0: Flag=1, displaying bank 1, write to bank 0
    write_bank0_addr = base_addr + len(code)
    code[bne_bank0 - base_addr + 1] = (write_bank0_addr - (bne_bank0 + 2)) & 0xFF
    code += [0xA9, 0x20, 0x85, 0x06] # LDA #$20; STA $06 (bitmap -> $2000)
    code += [0xA9, 0x04, 0x85, 0x07] # LDA #$04; STA $07 (screen -> $0400)

    # do_reads:
    do_reads_addr = base_addr + len(code)
    code[jmp_do_reads - base_addr + 1] = do_reads_addr & 0xFF
    code[jmp_do_reads - base_addr + 2] = (do_reads_addr >> 8) & 0xFF

    # Read Bitmap (8000 bytes) -> dest from $06
    code += [0xA9, 0x00, 0x85, 0xFC] # $FC = $00
    code += [0xA5, 0x06, 0x85, 0xFD] # LDA $06; STA $FD
    code += [0xA2, 0x40, 0xA0, 0x1F] # X = $40, Y = $1F (8000 bytes)
    code += [0x20, fread8_addr & 0xFF, (fread8_addr >> 8) & 0xFF]

    # Read Screen (1000 bytes) -> dest from $07
    code += [0xA9, 0x00, 0x85, 0xFC] # $FC = $00
    code += [0xA5, 0x07, 0x85, 0xFD] # LDA $07; STA $FD
    code += [0xA2, 0xE8, 0xA0, 0x03] # X = $E8, Y = $03 (1000 bytes)
    code += [0x20, fread8_addr & 0xFF, (fread8_addr >> 8) & 0xFF]

    # Read Color (1000 bytes) -> $D800 (hardware-fixed, always same)
    code += [0xA9, 0x00, 0x85, 0xFC] # $FC = $00
    code += [0xA9, 0xD8, 0x85, 0xFD] # $FD = $D8
    code += [0xA2, 0xE8, 0xA0, 0x03] # X = $E8, Y = $03 (1000 bytes)
    code += [0x20, fread8_addr & 0xFF, (fread8_addr >> 8) & 0xFF]

    # Apply VIC Settings
    code += [0xAD, 0x01, 0x02] # LDA $0201 (bg_color)
    code += [0x8D, 0x21, 0xD0] # STA $D021
    code += [0x8D, 0x20, 0xD0] # STA $D020 (border = bg_color)

    code += [0xAD, 0x00, 0x02] # LDA $0200 (mode)
    code += [0xC9, 0x00] # CMP #$00 (0 = Multicolor)

    apply_multi_addr = base_addr + len(code)
    code += [0xF0, 0x00] # BEQ apply_multi (patch later)

    # Hires mode
    code += [0xA9, 0x3B, 0x8D, 0x11, 0xD0] # LDA #$3B; STA $D011
    code += [0xA9, 0x08, 0x8D, 0x16, 0xD0] # LDA #$08; STA $D016
    code += [0xA9, 0x18, 0x8D, 0x18, 0xD0] # LDA #$18; STA $D018

    jmp_flip_addr = base_addr + len(code)
    code += [0x4C, 0x00, 0x00] # JMP do_flip (patch later)

    # apply_multi
    patched_multi_addr = base_addr + len(code)
    code[apply_multi_addr - base_addr + 1] = (patched_multi_addr - (apply_multi_addr + 2)) & 0xFF

    code += [0xA9, 0x3B, 0x8D, 0x11, 0xD0] # LDA #$3B; STA $D011
    code += [0xA9, 0x18, 0x8D, 0x16, 0xD0] # LDA #$18; STA $D016 (multicolor)
    code += [0xA9, 0x18, 0x8D, 0x18, 0xD0] # LDA #$18; STA $D018

    # do_flip: Flip VIC bank and toggle buffer flag
    do_flip_addr = base_addr + len(code)
    code[jmp_flip_addr - base_addr + 1] = do_flip_addr & 0xFF
    code[jmp_flip_addr - base_addr + 2] = (do_flip_addr >> 8) & 0xFF

    # Toggle bit 0 of DD00: 11 (bank 0) <-> 10 (bank 1)
    code += [0xAD, 0x00, 0xDD] # LDA $DD00
    code += [0x49, 0x01]       # EOR #$01
    code += [0x8D, 0x00, 0xDD] # STA $DD00

    # Toggle buffer flag
    code += [0xA5, 0x03]       # LDA $03
    code += [0x49, 0x01]       # EOR #$01
    code += [0x85, 0x03]       # STA $03

    # JMP main_loop
    code += [0x4C, main_loop_addr & 0xFF, (main_loop_addr >> 8) & 0xFF]

    return bytes(code)

def _build_streamer_crt():
    """Build an EasyFlash 3 CRT containing the streamer code."""
    # CRT Header
    header = b"C64 CARTRIDGE   "
    header += struct.pack(">I", 0x40)    # Header size
    header += struct.pack(">H", 0x0100)  # Version
    header += struct.pack(">H", 32)      # EasyFlash type
    header += b"\x00"                    # EXROM
    header += b"\x00"                    # GAME
    header += b"\x00" * 6                # Reserved
    header += b"ESPSTREAMER".ljust(32, b"\x00")

    # CHIP Packet (16KB Bank 0)
    rom_data = bytearray(16384)
    
    # Cold start vectors at $BFFC
    rom_data[0x3FFC] = 0x00
    rom_data[0x3FFD] = 0x80
    rom_data[0x3FFE] = 0x00
    rom_data[0x3FFF] = 0x80
    
    # CBM signature at $8000
    rom_data[0:9] = b"\x00\x80\x00\x80\xC3\xC2\xCD\x38\x30"
    
    # Code at $8009
    code = _build_streamer_code(0x8009)
    rom_data[0x09 : 0x09 + len(code)] = code
    
    chip_header = b"CHIP"
    chip_header += struct.pack(">I", 16384 + 0x10) # Packet size
    chip_header += struct.pack(">H", 0x0000)        # ROM type
    chip_header += struct.pack(">H", 0x0000)        # Bank
    chip_header += struct.pack(">H", 0x8000)        # Load addr
    chip_header += struct.pack(">H", 16384)         # Size
    
    return header + chip_header + rom_data

def _build_streamer_prg():
    """Build the C64 streamer PRG using EasyFlash 3 chunked request protocol."""
    code = [
        0x01, 0x08, # Load address $0801
        0x0B, 0x08, # Pointer to next line ($080B)
        0x0A, 0x00, # Line number 10
        0x9E,       # SYS token
        0x32, 0x30, 0x36, 0x31, # "2061"
        0x00,       # End of line
        0x00, 0x00  # End of program
    ]
    
    # 2061 = $080D. Append machine code running at $080D
    code.extend(_build_streamer_code(0x080D))
    
    return bytes(code)

STREAMER_PRG = _build_streamer_prg()
STREAMER_CRT = _build_streamer_crt()

# Export both so the user can choose their workflow
with open("kungfu_viewer.prg", "wb") as f:
    f.write(STREAMER_PRG)
    
with open("kungfu_viewer.crt", "wb") as f:
    f.write(STREAMER_CRT)


# ---------------------------------------------------------------------------
# Kung Fu Flash Serial Interface
# ---------------------------------------------------------------------------

class KungFuFlashSerial:
    """Communicates with KFF via CDC serial port using EF3 USB protocol."""

    def __init__(self):
        self.ser = None
        self.port_name = None
        self.connected = False
        self.viewer_running = False
        self.lock = threading.Lock()

    @staticmethod
    def find_kff_port():
        """Try to auto-detect KFF serial port (CDC/ACM device)."""
        ports = serial.tools.list_ports.comports()
        candidates = []
        for p in ports:
            desc = (p.description or '').lower()
            # KFF shows as "USB Serial Device" or "Serial USB device"
            if 'serial' in desc or 'acm' in desc or 'cdc' in desc:
                candidates.append(p.device)
            # STM32 VCP
            if p.vid == 0x0483:
                candidates.append(p.device)
        return candidates

    def connect(self, port=None):
        """Connect to KFF serial port."""
        try:
            if port is None:
                candidates = self.find_kff_port()
                if not candidates:
                    print("No KFF serial port found. Available ports:")
                    for p in serial.tools.list_ports.comports():
                        print(f"  {p.device}: {p.description} (VID={p.vid} PID={p.pid})")
                    return False
                port = candidates[0]
                print(f"Auto-detected KFF port: {port}")

            self.ser = serial.Serial(
                port=port,
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2,
                write_timeout=2
            )
            self.ser.dtr = True
            self.ser.rts = True
            self.port_name = port
            self.connected = True
            self.viewer_running = True # Assume viewer is started manually

            # Do NOT flush input buffer because C64 might have already sent a chunk request!
            self.ser.reset_output_buffer()

            print(f"Connected to KFF on {port}")
            print("Ready for chunked data flow.")
            return True

        except Exception as e:
            print(f"Serial connection failed: {e}")
            self.ser = None
            return False

    def disconnect(self):
        """Close serial connection."""
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
            self.ser = None
        self.connected = False
        self.viewer_running = False
        print("Disconnected from KFF")

    def send_viewer_prg(self, prg_file="viewer.prg"):
        """Send the streamer PRG to KFF via EFSTART:PRG handshake."""
        if not self.ser:
            return False

        try:
            import os
            # Flush
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.1)

            if os.path.exists(prg_file):
                print(f"Found {prg_file} on disk, loading custom PRG...")
                with open(prg_file, "rb") as f:
                    prg_data = f.read()
            else:
                print(f"Using internal STREAMER_PRG...")
                prg_data = STREAMER_PRG
            print(f"Sending streamer PRG ({len(prg_data)} bytes) via EFSTART:PRG...")

            # --- EFSTART:PRG handshake ---
            max_retries = 10
            for attempt in range(max_retries):
                # Send handshake string
                handshake = b'EFSTART:PRG\x00'
                self.ser.write(handshake)
                self.ser.flush()

                # Read 5-byte response
                resp = self.ser.read(5)
                if len(resp) < 5:
                    print(f"  Handshake timeout (got {len(resp)} bytes)")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    return False

                print(f"  Response: [{chr(resp[0]) if resp[0] > 31 else '?'}] ({resp.hex()})")

                if resp[0] == ord('W'):
                    print("  KFF waiting, retrying...")
                    time.sleep(1)
                    continue
                elif resp[0] == ord('L'):
                    print("  KFF ready to load!")
                    break
                else:
                    print(f"  Unexpected response: {resp}")
                    return False
            else:
                print("  Max retries reached")
                return False

            # --- Send PRG data in chunks ---
            offset = 0
            while offset < len(prg_data):
                # Read chunk size request (2 bytes LE)
                size_req = self.ser.read(2)
                if len(size_req) < 2:
                    print(f"  Chunk size request timeout")
                    return False

                chunk_size = size_req[0] + size_req[1] * 256
                if chunk_size == 0:
                    break

                # Prepare chunk
                remaining = len(prg_data) - offset
                actual_size = min(chunk_size, remaining)
                chunk = prg_data[offset:offset + actual_size]

                # Send actual size (2 bytes LE)
                self.ser.write(bytes([actual_size & 0xFF, (actual_size >> 8) & 0xFF]))
                # Send data
                self.ser.write(chunk)
                self.ser.flush()

                offset += actual_size
                print(f"  Sent {offset}/{len(prg_data)} bytes")

            # If the file size was an exact multiple of the requested chunk size,
            # KFF will request another chunk. We must send a 0-length response.
            if offset >= len(prg_data) and actual_size == chunk_size:
                try:
                    self.ser.timeout = 0.5
                    size_req = self.ser.read(2)
                    if len(size_req) == 2:
                        self.ser.write(bytes([0x00, 0x00]))
                        self.ser.flush()
                except:
                    pass

            print("Streamer PRG sent successfully!")
            print("Kung Fu Flash has now launched the PRG.")
            print("Waiting for frames...")
            time.sleep(0.5)
            # Do not flush here: the freshly launched viewer may already have
            # sent its first 2-byte chunk request while we were waiting.
            self.viewer_running = True
            return True

        except Exception as e:
            print(f"Failed to send viewer PRG: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stream_frame(self, mode, bg_color, bitmap, screen, color):
        """Stream a single frame to the C64 viewer using chunked flow."""
        if not self.ser or not self.viewer_running:
            return False

        with self.lock:
            try:
                # Payload is exactly 10004 bytes (padded for 4-byte unrolled loop)
                payload = bytes([mode & 0xFF, bg_color & 0xFF, 0, 0])
                payload += bytes(bitmap[:8000])
                payload += bytes(screen[:1000])
                payload += bytes(color[:1000])

                while len(payload) < 10004:
                    payload += b'\x00'

                offset = 0
                self.ser.timeout = 2.0

                while offset < len(payload):
                    # Read chunk request from C64 (2 bytes LE)
                    req = self.ser.read(2)
                    if len(req) < 2:
                        print(f"Chunk request timeout at offset {offset}. C64 did not request more data.")
                        return False
                    else:
                        chunk_size = req[0] + req[1] * 256
                        
                    if chunk_size == 0:
                        print("C64 requested 0 bytes? Ignoring and trying again...")
                        continue
                        
                    remaining = len(payload) - offset
                    actual_size = min(chunk_size, remaining)
                    chunk = payload[offset:offset+actual_size]
                    
                    # Send actual size
                    self.ser.write(bytes([actual_size & 0xFF, (actual_size >> 8) & 0xFF]))
                    # Send chunk
                    self.ser.write(chunk)
                    self.ser.flush()
                    
                    offset += actual_size

                return True

            except Exception as e:
                print(f"Stream frame failed: {e}")
                return False

    def reset_to_menu(self):
        """Reset KFF to menu by opening at 1200 baud."""
        if self.ser:
            port = self.port_name
            self.disconnect()
            try:
                # Opening at 1200 baud triggers reset (Arduino-style)
                s = serial.Serial(port=port, baudrate=1200)
                time.sleep(0.5)
                s.close()
                print("Reset signal sent to KFF")
                time.sleep(2)
            except Exception as e:
                print(f"Reset failed: {e}")


# ---------------------------------------------------------------------------
# WebSocket Server
# ---------------------------------------------------------------------------

class WebSocketServer:
    def __init__(self):
        self.kff = KungFuFlashSerial()
        self.clients = set()
        self.frame_count = 0

    async def handle_client(self, websocket):
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
        try:
            if isinstance(message, bytes):
                # Binary frame payload (same format as VICE server)
                if len(message) < 10002:
                    print(f"Binary payload too small: {len(message)}")
                    return

                mode = message[0]
                bg_color = message[1]
                bitmap = message[2:8002]
                screen = message[8002:9002]
                color = message[9002:10002]

                if self.kff.viewer_running:
                    # Run serial I/O in thread to avoid blocking asyncio
                    loop = asyncio.get_event_loop()
                    success = await loop.run_in_executor(
                        None, self.kff.stream_frame,
                        mode, bg_color, bitmap, screen, color
                    )

                    self.frame_count += 1
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'command': 'stream_frame',
                        'success': success,
                        'message': f'Frame {self.frame_count} sent to C64' if success else 'Frame failed'
                    }))
                else:
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'command': 'stream_frame',
                        'success': False,
                        'message': 'Viewer not running. Send viewer PRG first.'
                    }))
                return

            # JSON commands
            data = json.loads(message)
            command = data.get('command')

            if command == 'connect':
                port = data.get('port', None)
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.kff.connect, port)
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'connect',
                    'success': success,
                    'message': f'Connected to {self.kff.port_name}' if success else 'Connection failed. Check COM port.'
                }))

            elif command == 'get_viewer':
                # Send the generated PRG as base64
                encoded_prg = base64.b64encode(STREAMER_PRG).decode('utf-8')
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'get_viewer',
                    'success': True,
                    'prg_data': encoded_prg,
                    'filename': 'kungfu_viewer.prg'
                }))

            elif command == 'send_viewer':
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.kff.send_viewer_prg, "kungfu_viewer.prg")
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'send_viewer',
                    'success': success,
                    'message': 'Viewer sent successfully and is running!' if success else 'Failed to send viewer. Ensure KFF is in menu.'
                }))

            elif command == 'status':
                ports = KungFuFlashSerial.find_kff_port()
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'status',
                    'connected': self.kff.connected,
                    'viewer_running': self.kff.viewer_running,
                    'port': self.kff.port_name,
                    'available_ports': ports,
                    'message': ('Streaming' if self.kff.viewer_running else
                               'Connected' if self.kff.connected else 'Disconnected')
                }))

            elif command == 'reset':
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.kff.reset_to_menu)
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'reset',
                    'success': True,
                    'message': 'Reset signal sent'
                }))

            elif command == 'list_ports':
                ports = []
                for p in serial.tools.list_ports.comports():
                    ports.append({
                        'device': p.device,
                        'description': p.description,
                        'vid': p.vid,
                        'pid': p.pid
                    })
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'list_ports',
                    'ports': ports
                }))

            elif command == 'stream_frame':
                await websocket.send(json.dumps({
                    'type': 'response',
                    'command': 'stream_frame',
                    'success': False,
                    'message': 'Please use binary streaming for frames'
                }))

        except Exception as e:
            print(f"Message handling failed: {e}")
            import traceback
            traceback.print_exc()
            await websocket.send(json.dumps({
                'type': 'error',
                'message': str(e)
            }))


async def main():
    server = WebSocketServer()

    print("=" * 60)
    print("Kung Fu Flash Streaming Server")
    print("=" * 60)
    print(f"Streamer CRT size: {len(STREAMER_CRT)} bytes")
    print()

    # Show available ports
    ports = serial.tools.list_ports.comports()
    if ports:
        print("Available serial ports:")
        for p in ports:
            print(f"  {p.device}: {p.description}")
    else:
        print("No serial ports found.")
    print()

    print("WebSocket server on ws://localhost:8765")
    print()
    print("Usage:")
    print("  1. Copy 'kungfu_viewer.prg' to Kung Fu Flash SD card.")
    print("  2. Boot 'kungfu_viewer.prg' manually on the C64.")
    print("  3. Open ESPStreamer web interface, set to 'Hardware Mode' and click Connect.")
    print("  4. Click 'Start Stream' to send frames!")
    print()

    async with websockets.serve(server.handle_client, "localhost", 8765):
        print("Server running. Press Ctrl+C to stop.")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
