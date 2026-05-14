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

def rle_compress(data):
    """PackBits-style RLE: $00-$7F=literal(N+1), $80-$FF=repeat(N-126)."""
    result = bytearray()
    i, n = 0, len(data)
    while i < n:
        # Check for run of 2+ identical bytes
        if i + 1 < n and data[i] == data[i + 1]:
            val = data[i]
            run = 1
            while i + run < n and run < 129 and data[i + run] == val:
                run += 1
            result.append(run + 126)  # $80-$FF
            result.append(val)
            i += run
        else:
            # Literal run
            start = i
            while i < n and (i - start) < 128:
                if i + 1 < n and data[i] == data[i + 1]:
                    break
                i += 1
            lit_len = i - start
            if lit_len == 0:
                lit_len = 1
                i += 1
            result.append(lit_len - 1)  # $00-$7F
            result.extend(data[start:start + lit_len])
    return bytes(result)

def _build_streamer_code(base_addr):
    """Build the C64 streamer machine code using EasyFlash 3 chunked request protocol."""
    code = []

    # --- Machine Code Start ---
    code += [0x78] # SEI
    code += [0xD8] # CLD
    code += [0xA9, 0x35, 0x85, 0x01] # I/O + cartridge visible, BASIC ROM off (RAM at $A000)

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
    
    # --- Subroutine: ef3usb_fread ---
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
    
    code += [0x8A] # TXA
    
    # ef3usb_read_common
    common_addr = base_addr + len(code)
    
    code += [0x49, 0xFF, 0xAA] # EOR #$FF, TAX
    code += [0x98, 0x49, 0xFF, 0x85, 0xFE] # TYA, EOR #$FF, STA $FE (m_size_hi)
    code += [0xA0, 0x00] # LDY #0
    jmp_inc_fwd = len(code)
    code += [0x4C, 0x00, 0x00] # JMP incCounter
    
    # getBytes
    get_bytes_addr = base_addr + len(code)
    wait_rx_3 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE] # BIT $DE09
    add_rel(code, 0x10, wait_rx_3, base_addr + len(code)) # BPL
    code += [0xAD, 0x0A, 0xDE] # LDA $DE0A
    code += [0x91, 0xFC] # STA ($FC),Y
    code += [0xC8] # INY
    bne_inc_fwd = len(code)
    code += [0xD0, 0x00] # BNE incCounter
    code += [0xE6, 0xFD] # INC $FD
    
    # incCounter
    inc_counter_addr = base_addr + len(code)
    code[jmp_inc_fwd + 1] = inc_counter_addr & 0xFF
    code[jmp_inc_fwd + 2] = (inc_counter_addr >> 8) & 0xFF
    code[bne_inc_fwd + 1] = (inc_counter_addr - (base_addr + bne_inc_fwd + 2)) & 0xFF
    
    code += [0xE8] # INX
    add_rel(code, 0xD0, get_bytes_addr, base_addr + len(code)) # BNE getBytes
    code += [0xE6, 0xFE] # INC $FE
    add_rel(code, 0xD0, get_bytes_addr, base_addr + len(code)) # BNE getBytes
    
    # end
    code += [0x60] # RTS

    # --- Subroutine: rle_decode ---
    # Decodes PackBits RLE from $F8/$F9 (src) to $FC/$FD (dest)
    # Input: X = uncomp_size_lo, Y = uncomp_size_hi
    # Format: $00-$7F = literal(N+1 bytes), $80-$FF = repeat(N-126 times)
    rle_decode_addr = base_addr + len(code)

    # Negate output size for countdown counter in $08/$09
    code += [0x8A]                   # TXA
    code += [0x49, 0xFF]             # EOR #$FF
    code += [0x85, 0x08]             # STA $08
    code += [0x98]                   # TYA
    code += [0x49, 0xFF]             # EOR #$FF
    code += [0x85, 0x09]             # STA $09
    code += [0xA0, 0x00]             # LDY #0 (dest index)

    # inc_out: one's complement -> two's complement
    code += [0xE6, 0x08]             # INC $08
    rle_bne_token1 = len(code)
    code += [0xD0, 0x00]             # BNE rle_token (patch)
    code += [0xE6, 0x09]             # INC $09
    rle_bne_token2 = len(code)
    code += [0xD0, 0x00]             # BNE rle_token (patch)
    code += [0x60]                   # RTS (size was 0)

    # rle_token: read control byte from source
    rle_token_addr = base_addr + len(code)
    code[rle_bne_token1 + 1] = (rle_token_addr - (base_addr + rle_bne_token1 + 2)) & 0xFF
    code[rle_bne_token2 + 1] = (rle_token_addr - (base_addr + rle_bne_token2 + 2)) & 0xFF

    code += [0x84, 0x0B]             # STY $0B (save dest Y)
    code += [0xA0, 0x00]             # LDY #0
    code += [0xB1, 0xF8]             # LDA ($F8),Y
    code += [0xE6, 0xF8]             # INC $F8
    code += [0xD0, 0x02]             # BNE +2
    code += [0xE6, 0xF9]             # INC $F9
    # Test bit 7 of token reliably using CMP #$80 (immune to INC side-effects)
    code += [0xC9, 0x80]             # CMP #$80
    rle_bcs_repeat = len(code)
    code += [0xB0, 0x00]             # BCS rle_repeat (patch)

    # Literal run: A+1 bytes
    code += [0xA4, 0x0B]             # LDY $0B (restore dest Y)
    code += [0xAA]                   # TAX
    code += [0xE8]                   # INX (count 1-128)

    rle_lit_addr = base_addr + len(code)
    code += [0x84, 0x0B]             # STY $0B
    code += [0xA0, 0x00]             # LDY #0
    code += [0xB1, 0xF8]             # LDA ($F8),Y
    code += [0xE6, 0xF8]             # INC $F8
    code += [0xD0, 0x02]             # BNE +2
    code += [0xE6, 0xF9]             # INC $F9
    code += [0xA4, 0x0B]             # LDY $0B
    code += [0x91, 0xFC]             # STA ($FC),Y
    code += [0xC8]                   # INY
    code += [0xD0, 0x02]             # BNE +2
    code += [0xE6, 0xFD]             # INC $FD
    code += [0xE6, 0x08]             # INC $08
    code += [0xD0, 0x04]             # BNE +4
    code += [0xE6, 0x09]             # INC $09
    rle_beq_ret1 = len(code)
    code += [0xF0, 0x00]             # BEQ rle_ret (patch)
    code += [0xCA]                   # DEX
    add_rel(code, 0xD0, rle_lit_addr, base_addr + len(code))  # BNE rle_lit
    code += [0x4C, rle_token_addr & 0xFF, (rle_token_addr >> 8) & 0xFF]  # JMP rle_token

    # Repeat: A=$80-$FF, count = A - 126
    rle_repeat_addr = base_addr + len(code)
    code[rle_bcs_repeat + 1] = (rle_repeat_addr - (base_addr + rle_bcs_repeat + 2)) & 0xFF
    code += [0xA4, 0x0B]             # LDY $0B (restore dest Y)
    code += [0x38]                   # SEC
    code += [0xE9, 0x7E]             # SBC #126
    code += [0xAA]                   # TAX (count 2-129)
    code += [0x84, 0x0B]             # STY $0B
    code += [0xA0, 0x00]             # LDY #0
    code += [0xB1, 0xF8]             # LDA ($F8),Y
    code += [0xE6, 0xF8]             # INC $F8
    code += [0xD0, 0x02]             # BNE +2
    code += [0xE6, 0xF9]             # INC $F9
    code += [0xA4, 0x0B]             # LDY $0B

    rle_fill_addr = base_addr + len(code)
    code += [0x91, 0xFC]             # STA ($FC),Y
    code += [0xC8]                   # INY
    code += [0xD0, 0x02]             # BNE +2
    code += [0xE6, 0xFD]             # INC $FD
    code += [0xE6, 0x08]             # INC $08
    code += [0xD0, 0x04]             # BNE +4
    code += [0xE6, 0x09]             # INC $09
    rle_beq_ret2 = len(code)
    code += [0xF0, 0x00]             # BEQ rle_ret (patch)
    code += [0xCA]                   # DEX
    add_rel(code, 0xD0, rle_fill_addr, base_addr + len(code))  # BNE rle_fill
    code += [0x4C, rle_token_addr & 0xFF, (rle_token_addr >> 8) & 0xFF]  # JMP rle_token

    # rle_ret:
    rle_ret_addr = base_addr + len(code)
    code[rle_beq_ret1 + 1] = (rle_ret_addr - (base_addr + rle_beq_ret1 + 2)) & 0xFF
    code[rle_beq_ret2 + 1] = (rle_ret_addr - (base_addr + rle_beq_ret2 + 2)) & 0xFF
    code += [0x60]                   # RTS

    # --- Main Loop (Double Buffered) ---
    # Bank 0: Bitmap $2000, Screen $0400
    # Bank 1: Bitmap $6000, Screen $4400
    # Color RAM $D800 is hardware-fixed (always same)
    main_loop_addr = base_addr + len(code)
    # Patch JMP over subroutines
    code[jmp_start - base_addr + 1] = main_loop_addr & 0xFF
    code[jmp_start - base_addr + 2] = (main_loop_addr >> 8) & 0xFF

    # Read Mode and BG color (2 bytes) -> $0200
    code += [0xA9, 0x00, 0x85, 0xFC] # $FC = $00
    code += [0xA9, 0x02, 0x85, 0xFD] # $FD = $02
    code += [0xA2, 0x02, 0xA0, 0x00] # X = 2, Y = 0 (2 bytes)
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

    # --- Helper: fread comp_size, fread data to $0C00, rle_decode to dest ---
    # Temp buffer at $0C00 (guaranteed RAM, no cartridge overlay)
    TEMP_BUF_HI = 0x0C

    def emit_rle_segment(dest_hi_is_zp, dest_hi_val, uncomp_lo, uncomp_hi):
        """Emit code to: fread(2) comp_size, fread(comp_size) to $0C00, rle_decode to dest."""
        # Save uncomp size
        code.extend([0xA2, uncomp_lo, 0xA0, uncomp_hi])  # LDX #lo; LDY #hi
        code.extend([0x86, 0x0C, 0x84, 0x0D])            # STX $0C; STY $0D

        # fread(2) to get comp_size -> $0204/$0205
        code.extend([0xA9, 0x04, 0x85, 0xFC])  # STA $FC = $04
        code.extend([0xA9, 0x02, 0x85, 0xFD])  # STA $FD = $02
        code.extend([0xA2, 0x02, 0xA0, 0x00])  # X=2, Y=0
        code.extend([0x20, fread_addr & 0xFF, (fread_addr >> 8) & 0xFF])

        # fread(comp_size) -> temp buffer $0C00
        code.extend([0xA9, 0x00, 0x85, 0xFC])  # STA $FC = $00
        code.extend([0xA9, TEMP_BUF_HI, 0x85, 0xFD])  # STA $FD = $0C
        code.extend([0xAE, 0x04, 0x02])        # LDX $0204 (comp_size_lo)
        code.extend([0xAC, 0x05, 0x02])        # LDY $0205 (comp_size_hi)
        code.extend([0x20, fread_addr & 0xFF, (fread_addr >> 8) & 0xFF])

        # Setup rle_decode: src=$0C00, dest from parameter
        code.extend([0xA9, 0x00, 0x85, 0xF8])  # STA $F8 = $00
        code.extend([0xA9, TEMP_BUF_HI, 0x85, 0xF9])  # STA $F9 = $0C
        code.extend([0xA9, 0x00, 0x85, 0xFC])  # STA $FC = $00
        if dest_hi_is_zp:
            code.extend([0xA5, dest_hi_val, 0x85, 0xFD])
        else:
            code.extend([0xA9, dest_hi_val, 0x85, 0xFD])
        code.extend([0xA6, 0x0C, 0xA4, 0x0D])  # LDX $0C; LDY $0D
        code.extend([0x20, rle_decode_addr & 0xFF, (rle_decode_addr >> 8) & 0xFF])

    # Bitmap: dest from $06, 8000 bytes ($1F40)
    emit_rle_segment(True, 0x06, 0x40, 0x1F)

    # Screen: dest from $07, 1000 bytes ($03E8)
    emit_rle_segment(True, 0x07, 0xE8, 0x03)

    # Color: dest $D8, 1000 bytes ($03E8)
    emit_rle_segment(False, 0xD8, 0xE8, 0x03)

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
            self.viewer_running = True
            self._first_frame = True
            return True

        except Exception as e:
            print(f"Failed to send viewer PRG: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stream_frame(self, mode, bg_color, bitmap, screen, color):
        """Stream a single RLE-compressed frame to the C64 viewer."""
        if not self.ser or not self.viewer_running:
            return False

        with self.lock:
            try:
                # Compress each segment
                bmp_data = bytes(bitmap[:8000])
                scr_data = bytes(screen[:1000])
                col_data = bytes(color[:1000])
                while len(bmp_data) < 8000: bmp_data += b'\x00'
                while len(scr_data) < 1000: scr_data += b'\x00'
                while len(col_data) < 1000: col_data += b'\x00'

                bmp_comp = rle_compress(bmp_data)
                scr_comp = rle_compress(scr_data)
                col_comp = rle_compress(col_data)

                total_raw = 10002
                total_comp = 2 + len(bmp_comp) + len(scr_comp) + len(col_comp)
                ratio = total_comp * 100 // total_raw
                print(f"RLE: {total_raw}>{total_comp} ({ratio}%) bmp={len(bmp_comp)} scr={len(scr_comp)} col={len(col_comp)}")

                # Protocol:
                # 1. C64 does fread(2) for mode+bg (standard chunk request)
                # 2. For each segment: C64 sends ready signal [FF,FF],
                #    server streams compressed bytes directly

                # Step 1: Wait for fread(2) request for mode+bg
                # On first frame after PRG load, skip stale EFSTART bytes
                # by reading 2-byte pairs until we get the fread(2) request [02,00]
                if getattr(self, '_first_frame', False):
                    self._first_frame = False
                    self.ser.timeout = 5.0
                    for _attempt in range(10):
                        req = self.ser.read(2)
                        if len(req) < 2:
                            print("Timeout waiting for mode+bg request.")
                            return False
                        chunk_size = req[0] + req[1] * 256
                        if chunk_size == 2:
                            print(f"  mode+bg: req={chunk_size}")
                            break
                        print(f"  Skipped stale bytes: {req.hex()}")
                    else:
                        print("Too many stale bytes, giving up.")
                        return False
                else:
                    self.ser.timeout = 5.0
                    req = self.ser.read(2)
                    if len(req) < 2:
                        print("Timeout waiting for mode+bg request.")
                        return False
                    chunk_size = req[0] + req[1] * 256
                    print(f"  mode+bg: req={chunk_size}")

                # Send actual_size + mode+bg
                mode_bg = bytes([mode & 0xFF, bg_color & 0xFF])
                self.ser.write(bytes([len(mode_bg) & 0xFF, (len(mode_bg) >> 8) & 0xFF]))
                self.ser.write(mode_bg)
                self.ser.flush()

                # Build remaining payload: [comp_size, comp_data] * 3
                payload = b''
                payload += struct.pack('<H', len(bmp_comp)) + bmp_comp
                payload += struct.pack('<H', len(scr_comp)) + scr_comp
                payload += struct.pack('<H', len(col_comp)) + col_comp

                offset = 0
                while offset < len(payload):
                    self.ser.timeout = 5.0
                    req = self.ser.read(2)
                    if len(req) < 2:
                        print(f"  Chunk timeout at payload offset {offset}")
                        return False
                    chunk_size = req[0] + req[1] * 256
                    if chunk_size == 0:
                        continue

                    remaining = len(payload) - offset
                    actual_size = min(chunk_size, remaining)
                    chunk = payload[offset:offset+actual_size]

                    self.ser.write(bytes([actual_size & 0xFF, (actual_size >> 8) & 0xFF]))
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
