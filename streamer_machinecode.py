#!/usr/bin/env python3
"""
Shared C64 streamer machine code generation.
Contains 6502 assembler helpers and builders for PRG/CRT/EasyFlash binaries.
Used by both backend_kungfu.py and kungfu_server.py.
"""

import struct


def add_rel(code, opcode, target_addr, current_addr):
    disp = target_addr - (current_addr + 2)
    if disp < -128 or disp > 127:
        raise ValueError(f"Branch out of range: {disp}")
    code += [opcode, disp & 0xFF]


def _build_streamer_code(base_addr):
    """Build the C64 streamer machine code using EasyFlash 3 chunked request protocol."""
    code = []

    # --- Machine Code Start ---
    code += [0x78]  # SEI
    code += [0xD8]  # CLD
    code += [0xA9, 0x35, 0x85, 0x01]  # I/O visible

    # Set CIA2 data direction: bits 0-1 as output for VIC bank select
    code += [0xAD, 0x02, 0xDD]  # LDA $DD02
    code += [0x09, 0x03]  # ORA #$03
    code += [0x8D, 0x02, 0xDD]  # STA $DD02

    # Set VIC to bank 0 ($0000-$3FFF): DD00 bits 0-1 = 11
    code += [0xAD, 0x00, 0xDD]  # LDA $DD00
    code += [0x09, 0x03]  # ORA #$03
    code += [0x8D, 0x00, 0xDD]  # STA $DD00

    # Double buffer flag at $03
    code += [0xA9, 0x00, 0x85, 0x03]  # LDA #0; STA $03

    jmp_start = base_addr + len(code)
    code += [0x4C, 0x00, 0x00]  # JMP main_loop

    # --- Subroutine: ef3usb_fread (4x Unrolled + SMC) ---
    fread_addr = base_addr + len(code)

    wait_tx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x50, wait_tx_1, base_addr + len(code))  # BVC
    code += [0x8E, 0x0A, 0xDE]  # STX $DE0A

    wait_tx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x50, wait_tx_2, base_addr + len(code))  # BVC
    code += [0x8C, 0x0A, 0xDE]  # STY $DE0A

    wait_rx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x10, wait_rx_1, base_addr + len(code))  # BPL
    code += [0xAE, 0x0A, 0xDE, 0x86, 0x04]  # LDX $DE0A, STX $04

    wait_rx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x10, wait_rx_2, base_addr + len(code))  # BPL
    code += [0xAC, 0x0A, 0xDE, 0x84, 0x05]  # LDY $DE0A, STY $05

    code += [0x46, 0x05, 0x66, 0x04]  # LSR $05, ROR $04
    code += [0x46, 0x05, 0x66, 0x04]  # LSR $05, ROR $04

    code += [0xA5, 0x04, 0x49, 0xFF, 0xAA]  # LDA $04, EOR #$FF, TAX
    code += [0xA5, 0x05, 0x49, 0xFF, 0x85, 0xFE]  # LDA $05, EOR #$FF, STA $FE

    code += [0xA5, 0xFC]  # LDA $FC
    smc_lo_patches = []
    smc_hi_patches = []

    code += [0x8D, 0x00, 0x00]  # STA smc1+1
    smc_lo_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00]  # STA smc2+1
    smc_lo_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00]  # STA smc3+1
    smc_lo_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00]  # STA smc4+1
    smc_lo_patches.append(len(code) - 2)

    code += [0xA5, 0xFD]  # LDA $FD
    code += [0x8D, 0x00, 0x00]  # STA smc1+2
    smc_hi_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00]  # STA smc2+2
    smc_hi_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00]  # STA smc3+2
    smc_hi_patches.append(len(code) - 2)
    code += [0x8D, 0x00, 0x00]  # STA smc4+2
    smc_hi_patches.append(len(code) - 2)

    code += [0xA0, 0x00]  # LDY #0

    jmp_inc_fwd = len(code)
    code += [0x4C, 0x00, 0x00]  # JMP incCounter

    get_bytes_addr = base_addr + len(code)

    smc_inst_addrs = []
    for i in range(4):
        wait_rx = base_addr + len(code)
        code += [0x2C, 0x09, 0xDE]  # BIT $DE09
        add_rel(code, 0x10, wait_rx, base_addr + len(code))  # BPL

        code += [0xAD, 0x0A, 0xDE]  # LDA $DE0A

        smc_inst_addrs.append(base_addr + len(code))
        code += [0x99, 0x00, 0x00]  # STA $0000,Y

        code += [0xC8]  # INY

    bne_page = len(code)
    code += [0xD0, 0x00]  # BNE skip_page_inc

    for i in range(4):
        code += [
            0xEE,
            (smc_inst_addrs[i] + 2) & 0xFF,
            (smc_inst_addrs[i] + 2) >> 8,
        ]  # INC smc+2

    skip_page_addr = base_addr + len(code)
    code[bne_page + 1] = (skip_page_addr - (base_addr + bne_page + 2)) & 0xFF

    inc_counter_addr = base_addr + len(code)
    code[jmp_inc_fwd + 1] = inc_counter_addr & 0xFF
    code[jmp_inc_fwd + 2] = (inc_counter_addr >> 8) & 0xFF

    code += [0xE8]  # INX
    add_rel(code, 0xD0, get_bytes_addr, base_addr + len(code))  # BNE get_bytes
    code += [0xE6, 0xFE]  # INC $FE
    add_rel(code, 0xD0, get_bytes_addr, base_addr + len(code))  # BNE get_bytes

    code += [0x60]  # RTS

    for i in range(4):
        code[smc_lo_patches[i]] = (smc_inst_addrs[i] + 1) & 0xFF
        code[smc_lo_patches[i] + 1] = (smc_inst_addrs[i] + 1) >> 8
        code[smc_hi_patches[i]] = (smc_inst_addrs[i] + 2) & 0xFF
        code[smc_hi_patches[i] + 1] = (smc_inst_addrs[i] + 2) >> 8

    # --- Subroutine: ef3usb_fread8 ---
    fread8_addr = base_addr + len(code)

    wait_tx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x50, wait_tx_1, base_addr + len(code))  # BVC
    code += [0x8E, 0x0A, 0xDE]  # STX $DE0A

    wait_tx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x50, wait_tx_2, base_addr + len(code))  # BVC
    code += [0x8C, 0x0A, 0xDE]  # STY $DE0A

    wait_rx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x10, wait_rx_1, base_addr + len(code))  # BPL
    code += [0xAE, 0x0A, 0xDE, 0x86, 0x04]  # LDX $DE0A, STX $04

    wait_rx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x10, wait_rx_2, base_addr + len(code))  # BPL
    code += [0xAC, 0x0A, 0xDE, 0x84, 0x05]  # LDY $DE0A, STY $05

    code += [0x46, 0x05, 0x66, 0x04]  # LSR $05, ROR $04
    code += [0x46, 0x05, 0x66, 0x04]  # LSR $05, ROR $04
    code += [0x46, 0x05, 0x66, 0x04]  # LSR $05, ROR $04

    code += [0xA5, 0x04, 0x49, 0xFF, 0xAA]  # LDA $04, EOR #$FF, TAX
    code += [0xA5, 0x05, 0x49, 0xFF, 0x85, 0xFE]  # LDA $05, EOR #$FF, STA $FE

    code += [0xA5, 0xFC]  # LDA $FC
    smc8_lo_patches = []
    smc8_hi_patches = []
    for i in range(8):
        code += [0x8D, 0x00, 0x00]  # STA smc+1
        smc8_lo_patches.append(len(code) - 2)

    code += [0xA5, 0xFD]  # LDA $FD
    for i in range(8):
        code += [0x8D, 0x00, 0x00]  # STA smc+2
        smc8_hi_patches.append(len(code) - 2)

    code += [0xA0, 0x00]  # LDY #0

    jmp8_inc_fwd = len(code)
    code += [0x4C, 0x00, 0x00]  # JMP incCounter

    get8_bytes_addr = base_addr + len(code)
    smc8_inst_addrs = []
    for i in range(8):
        wait_rx = base_addr + len(code)
        code += [0x2C, 0x09, 0xDE]  # BIT $DE09
        add_rel(code, 0x10, wait_rx, base_addr + len(code))  # BPL

        code += [0xAD, 0x0A, 0xDE]  # LDA $DE0A
        smc8_inst_addrs.append(base_addr + len(code))
        code += [0x99, 0x00, 0x00]  # STA $0000,Y
        code += [0xC8]  # INY

    bne8_page = len(code)
    code += [0xD0, 0x00]  # BNE skip_page_inc

    for i in range(8):
        code += [
            0xEE,
            (smc8_inst_addrs[i] + 2) & 0xFF,
            (smc8_inst_addrs[i] + 2) >> 8,
        ]  # INC smc+2

    skip8_page_addr = base_addr + len(code)
    code[bne8_page + 1] = (skip8_page_addr - (base_addr + bne8_page + 2)) & 0xFF

    inc8_counter_addr = base_addr + len(code)
    code[jmp8_inc_fwd + 1] = inc8_counter_addr & 0xFF
    code[jmp8_inc_fwd + 2] = (inc8_counter_addr >> 8) & 0xFF

    code += [0xE8]  # INX
    add_rel(code, 0xD0, get8_bytes_addr, base_addr + len(code))  # BNE get_bytes
    code += [0xE6, 0xFE]  # INC $FE
    beq8_done = len(code)
    code += [0xF0, 0x00]  # BEQ done
    code += [0x4C, get8_bytes_addr & 0xFF, (get8_bytes_addr >> 8) & 0xFF]  # JMP get_bytes
    done8_addr = base_addr + len(code)
    code[beq8_done + 1] = (done8_addr - (base_addr + beq8_done + 2)) & 0xFF
    code += [0x60]  # RTS

    for i in range(8):
        code[smc8_lo_patches[i]] = (smc8_inst_addrs[i] + 1) & 0xFF
        code[smc8_lo_patches[i] + 1] = (smc8_inst_addrs[i] + 1) >> 8
        code[smc8_hi_patches[i]] = (smc8_inst_addrs[i] + 2) & 0xFF
        code[smc8_hi_patches[i] + 1] = (smc8_inst_addrs[i] + 2) >> 8

    # --- Subroutine: ef3usb_fread16 ---
    fread16_addr = base_addr + len(code)

    wait_tx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x50, wait_tx_1, base_addr + len(code))  # BVC
    code += [0x8E, 0x0A, 0xDE]  # STX $DE0A

    wait_tx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x50, wait_tx_2, base_addr + len(code))  # BVC
    code += [0x8C, 0x0A, 0xDE]  # STY $DE0A

    wait_rx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x10, wait_rx_1, base_addr + len(code))  # BPL
    code += [0xAE, 0x0A, 0xDE, 0x86, 0x04]  # LDX $DE0A, STX $04

    wait_rx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x10, wait_rx_2, base_addr + len(code))  # BPL
    code += [0xAC, 0x0A, 0xDE, 0x84, 0x05]  # LDY $DE0A, STY $05

    code += [0x46, 0x05, 0x66, 0x04]  # LSR $05, ROR $04
    code += [0x46, 0x05, 0x66, 0x04]  # LSR $05, ROR $04
    code += [0x46, 0x05, 0x66, 0x04]  # LSR $05, ROR $04
    code += [0x46, 0x05, 0x66, 0x04]  # LSR $05, ROR $04

    code += [0xA5, 0x04, 0x49, 0xFF, 0xAA]  # LDA $04, EOR #$FF, TAX
    code += [0xA5, 0x05, 0x49, 0xFF, 0x85, 0xFE]  # LDA $05, EOR #$FF, STA $FE

    code += [0xA5, 0xFC]  # LDA $FC
    smc16_lo_patches = []
    smc16_hi_patches = []
    for i in range(16):
        code += [0x8D, 0x00, 0x00]  # STA smc+1
        smc16_lo_patches.append(len(code) - 2)

    code += [0xA5, 0xFD]  # LDA $FD
    for i in range(16):
        code += [0x8D, 0x00, 0x00]  # STA smc+2
        smc16_hi_patches.append(len(code) - 2)

    code += [0xA0, 0x00]  # LDY #0

    jmp16_inc_fwd = len(code)
    code += [0x4C, 0x00, 0x00]  # JMP incCounter

    get16_bytes_addr = base_addr + len(code)
    smc16_inst_addrs = []
    for i in range(16):
        wait_rx = base_addr + len(code)
        code += [0x2C, 0x09, 0xDE]  # BIT $DE09
        add_rel(code, 0x10, wait_rx, base_addr + len(code))  # BPL

        code += [0xAD, 0x0A, 0xDE]  # LDA $DE0A
        smc16_inst_addrs.append(base_addr + len(code))
        code += [0x99, 0x00, 0x00]  # STA $0000,Y
        code += [0xC8]  # INY

    bne16_page = len(code)
    code += [0xD0, 0x00]  # BNE skip_page_inc

    for i in range(16):
        code += [
            0xEE,
            (smc16_inst_addrs[i] + 2) & 0xFF,
            (smc16_inst_addrs[i] + 2) >> 8,
        ]  # INC smc+2

    skip16_page_addr = base_addr + len(code)
    code[bne16_page + 1] = (skip16_page_addr - (base_addr + bne16_page + 2)) & 0xFF

    inc16_counter_addr = base_addr + len(code)
    code[jmp16_inc_fwd + 1] = inc16_counter_addr & 0xFF
    code[jmp16_inc_fwd + 2] = (inc16_counter_addr >> 8) & 0xFF

    code += [0xE8]  # INX
    beq16_hi = len(code)
    code += [0xF0, 0x00]  # BEQ high-byte counter
    code += [0x4C, get16_bytes_addr & 0xFF, (get16_bytes_addr >> 8) & 0xFF]  # JMP get_bytes

    hi16_counter_addr = base_addr + len(code)
    code[beq16_hi + 1] = (hi16_counter_addr - (base_addr + beq16_hi + 2)) & 0xFF
    code += [0xE6, 0xFE]  # INC $FE
    beq16_done = len(code)
    code += [0xF0, 0x00]  # BEQ done
    code += [0x4C, get16_bytes_addr & 0xFF, (get16_bytes_addr >> 8) & 0xFF]  # JMP get_bytes
    done16_addr = base_addr + len(code)
    code[beq16_done + 1] = (done16_addr - (base_addr + beq16_done + 2)) & 0xFF
    code += [0x60]  # RTS

    for i in range(16):
        code[smc16_lo_patches[i]] = (smc16_inst_addrs[i] + 1) & 0xFF
        code[smc16_lo_patches[i] + 1] = (smc16_inst_addrs[i] + 1) >> 8
        code[smc16_hi_patches[i]] = (smc16_inst_addrs[i] + 2) & 0xFF
        code[smc16_hi_patches[i] + 1] = (smc16_inst_addrs[i] + 2) >> 8

    # --- Subroutine: ef3usb_fread32 ---
    fread32_addr = base_addr + len(code)

    wait_tx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x50, wait_tx_1, base_addr + len(code))  # BVC
    code += [0x8E, 0x0A, 0xDE]  # STX $DE0A

    wait_tx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x50, wait_tx_2, base_addr + len(code))  # BVC
    code += [0x8C, 0x0A, 0xDE]  # STY $DE0A

    wait_rx_1 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x10, wait_rx_1, base_addr + len(code))  # BPL
    code += [0xAE, 0x0A, 0xDE, 0x86, 0x04]  # LDX $DE0A, STX $04

    wait_rx_2 = base_addr + len(code)
    code += [0x2C, 0x09, 0xDE]  # BIT $DE09
    add_rel(code, 0x10, wait_rx_2, base_addr + len(code))  # BPL
    code += [0xAC, 0x0A, 0xDE, 0x84, 0x05]  # LDY $DE0A, STY $05

    for i in range(5):
        code += [0x46, 0x05, 0x66, 0x04]  # LSR $05, ROR $04

    code += [0xA5, 0x04, 0x49, 0xFF, 0xAA]  # LDA $04, EOR #$FF, TAX
    code += [0xA5, 0x05, 0x49, 0xFF, 0x85, 0xFE]  # LDA $05, EOR #$FF, STA $FE

    code += [0xA5, 0xFC]  # LDA $FC
    smc32_lo_patches = []
    smc32_hi_patches = []
    for i in range(32):
        code += [0x8D, 0x00, 0x00]  # STA smc+1
        smc32_lo_patches.append(len(code) - 2)

    code += [0xA5, 0xFD]  # LDA $FD
    for i in range(32):
        code += [0x8D, 0x00, 0x00]  # STA smc+2
        smc32_hi_patches.append(len(code) - 2)

    code += [0xA0, 0x00]  # LDY #0

    jmp32_inc_fwd = len(code)
    code += [0x4C, 0x00, 0x00]  # JMP incCounter

    get32_bytes_addr = base_addr + len(code)
    smc32_inst_addrs = []
    for i in range(32):
        wait_rx = base_addr + len(code)
        code += [0x2C, 0x09, 0xDE]  # BIT $DE09
        add_rel(code, 0x10, wait_rx, base_addr + len(code))  # BPL

        code += [0xAD, 0x0A, 0xDE]  # LDA $DE0A
        smc32_inst_addrs.append(base_addr + len(code))
        code += [0x99, 0x00, 0x00]  # STA $0000,Y
        code += [0xC8]  # INY

    bne32_page = len(code)
    code += [0xD0, 0x00]  # BNE skip_page_inc

    for i in range(32):
        code += [
            0xEE,
            (smc32_inst_addrs[i] + 2) & 0xFF,
            (smc32_inst_addrs[i] + 2) >> 8,
        ]  # INC smc+2

    skip32_page_addr = base_addr + len(code)
    code[bne32_page + 1] = (skip32_page_addr - (base_addr + bne32_page + 2)) & 0xFF

    inc32_counter_addr = base_addr + len(code)
    code[jmp32_inc_fwd + 1] = inc32_counter_addr & 0xFF
    code[jmp32_inc_fwd + 2] = (inc32_counter_addr >> 8) & 0xFF

    code += [0xE8]  # INX
    beq32_hi = len(code)
    code += [0xF0, 0x00]  # BEQ high-byte counter
    code += [0x4C, get32_bytes_addr & 0xFF, (get32_bytes_addr >> 8) & 0xFF]  # JMP get_bytes

    hi32_counter_addr = base_addr + len(code)
    code[beq32_hi + 1] = (hi32_counter_addr - (base_addr + beq32_hi + 2)) & 0xFF
    code += [0xE6, 0xFE]  # INC $FE
    beq32_done = len(code)
    code += [0xF0, 0x00]  # BEQ done
    code += [0x4C, get32_bytes_addr & 0xFF, (get32_bytes_addr >> 8) & 0xFF]  # JMP get_bytes
    done32_addr = base_addr + len(code)
    code[beq32_done + 1] = (done32_addr - (base_addr + beq32_done + 2)) & 0xFF
    code += [0x60]  # RTS

    for i in range(32):
        code[smc32_lo_patches[i]] = (smc32_inst_addrs[i] + 1) & 0xFF
        code[smc32_lo_patches[i] + 1] = (smc32_inst_addrs[i] + 1) >> 8
        code[smc32_hi_patches[i]] = (smc32_inst_addrs[i] + 2) & 0xFF
        code[smc32_hi_patches[i] + 1] = (smc32_inst_addrs[i] + 2) >> 8

    # --- Subroutine: apply_delta_pages ---
    apply_delta_pages_addr = base_addr + len(code)
    delta_loop_addr = base_addr + len(code)
    code += [0xA5, 0x08]  # LDA $08
    beq_delta_done = len(code)
    code += [0xF0, 0x00]  # BEQ done

    code += [0xA9, 0x08, 0x85, 0xFC]  # $FC = $08
    code += [0xA9, 0x02, 0x85, 0xFD]  # $FD = $02
    code += [0xA2, 0x04, 0xA0, 0x00]  # 4 bytes
    code += [0x20, fread_addr & 0xFF, (fread_addr >> 8) & 0xFF]

    code += [0xA9, 0x00, 0x85, 0xFC]  # $FC = $00
    code += [0xA5, 0x09]  # LDA base high
    code += [0x18]  # CLC
    code += [0x6D, 0x08, 0x02]  # ADC $0208
    code += [0x85, 0xFD]  # STA $FD

    code += [0xA2, 0x00, 0xA0, 0x01]  # X/Y = $0100
    code += [0x20, fread32_addr & 0xFF, (fread32_addr >> 8) & 0xFF]
    code += [0xC6, 0x08]  # DEC $08
    code += [0x4C, delta_loop_addr & 0xFF, (delta_loop_addr >> 8) & 0xFF]
    delta_done_addr = base_addr + len(code)
    code[beq_delta_done + 1] = (delta_done_addr - (base_addr + beq_delta_done + 2)) & 0xFF
    code += [0x60]  # RTS

    # --- Main Loop (Double Buffered) ---
    main_loop_addr = base_addr + len(code)
    code[jmp_start - base_addr + 1] = main_loop_addr & 0xFF
    code[jmp_start - base_addr + 2] = (main_loop_addr >> 8) & 0xFF

    code += [0xA9, 0x00, 0x85, 0xFC]  # $FC = $00
    code += [0xA9, 0x02, 0x85, 0xFD]  # $FD = $02
    code += [0xA2, 0x04, 0xA0, 0x00]  # X = 4, Y = 0 (4 bytes)
    code += [0x20, fread_addr & 0xFF, (fread_addr >> 8) & 0xFF]

    code += [0xA5, 0x03]  # LDA $03
    bne_bank0 = base_addr + len(code)
    code += [0xD0, 0x00]  # BNE write_bank0

    code += [0xA9, 0x60, 0x85, 0x06]  # LDA #$60; STA $06
    code += [0xA9, 0x44, 0x85, 0x07]  # LDA #$44; STA $07
    jmp_do_reads = base_addr + len(code)
    code += [0x4C, 0x00, 0x00]  # JMP do_reads

    write_bank0_addr = base_addr + len(code)
    code[bne_bank0 - base_addr + 1] = (write_bank0_addr - (bne_bank0 + 2)) & 0xFF
    code += [0xA9, 0x20, 0x85, 0x06]  # LDA #$20; STA $06
    code += [0xA9, 0x04, 0x85, 0x07]  # LDA #$04; STA $07

    do_reads_addr = base_addr + len(code)
    code[jmp_do_reads - base_addr + 1] = do_reads_addr & 0xFF
    code[jmp_do_reads - base_addr + 2] = (do_reads_addr >> 8) & 0xFF

    code += [0xAD, 0x02, 0x02]  # LDA $0202
    code += [0x29, 0x80]  # AND #$80
    beq_full_reads = base_addr + len(code)
    code += [0xF0, 0x00]  # BEQ full_reads

    code += [0xA9, 0x04, 0x85, 0xFC]  # $FC = $04
    code += [0xA9, 0x02, 0x85, 0xFD]  # $FD = $02
    code += [0xA2, 0x04, 0xA0, 0x00]  # 4 bytes
    code += [0x20, fread_addr & 0xFF, (fread_addr >> 8) & 0xFF]

    code += [0xAD, 0x03, 0x02, 0x85, 0x08]  # LDA $0203; STA $08
    code += [0xA5, 0x06, 0x85, 0x09]  # LDA $06; STA $09
    code += [
        0x20,
        apply_delta_pages_addr & 0xFF,
        (apply_delta_pages_addr >> 8) & 0xFF,
    ]

    code += [0xAD, 0x04, 0x02, 0x85, 0x08]  # LDA $0204; STA $08
    code += [0xA5, 0x07, 0x85, 0x09]  # LDA $07; STA $09
    code += [
        0x20,
        apply_delta_pages_addr & 0xFF,
        (apply_delta_pages_addr >> 8) & 0xFF,
    ]

    code += [0xAD, 0x05, 0x02, 0x85, 0x08]  # LDA $0205; STA $08
    code += [0xA9, 0xD8, 0x85, 0x09]  # LDA #$D8; STA $09
    code += [
        0x20,
        apply_delta_pages_addr & 0xFF,
        (apply_delta_pages_addr >> 8) & 0xFF,
    ]

    jmp_apply_settings = base_addr + len(code)
    code += [0x4C, 0x00, 0x00]  # JMP apply_settings

    full_reads_addr = base_addr + len(code)
    code[beq_full_reads - base_addr + 1] = (full_reads_addr - (beq_full_reads + 2)) & 0xFF

    code += [0xA9, 0x00, 0x85, 0xFC]  # $FC = $00
    code += [0xA5, 0x06, 0x85, 0xFD]  # LDA $06; STA $FD
    code += [0xA2, 0x40, 0xA0, 0x1F]  # X = $40, Y = $1F (8000 bytes)
    code += [0x20, fread32_addr & 0xFF, (fread32_addr >> 8) & 0xFF]

    code += [0xAD, 0x02, 0x02]  # LDA $0202
    code += [0x29, 0x01]  # AND #$01
    beq_skip_screen = base_addr + len(code)
    code += [0xF0, 0x00]  # BEQ skip_screen
    code += [0xA9, 0x00, 0x85, 0xFC]  # $FC = $00
    code += [0xA5, 0x07, 0x85, 0xFD]  # LDA $07; STA $FD
    code += [0xA2, 0xE8, 0xA0, 0x03]  # X = $E8, Y = $03 (1000 bytes)
    code += [0x20, fread8_addr & 0xFF, (fread8_addr >> 8) & 0xFF]
    skip_screen_addr = base_addr + len(code)
    code[beq_skip_screen - base_addr + 1] = (skip_screen_addr - (beq_skip_screen + 2)) & 0xFF

    code += [0xAD, 0x02, 0x02]  # LDA $0202
    code += [0x29, 0x02]  # AND #$02
    beq_skip_color = base_addr + len(code)
    code += [0xF0, 0x00]  # BEQ skip_color
    code += [0xA9, 0x00, 0x85, 0xFC]  # $FC = $00
    code += [0xA9, 0xD8, 0x85, 0xFD]  # $FD = $D8
    code += [0xA2, 0xE8, 0xA0, 0x03]  # X = $E8, Y = $03 (1000 bytes)
    code += [0x20, fread8_addr & 0xFF, (fread8_addr >> 8) & 0xFF]
    skip_color_addr = base_addr + len(code)
    code[beq_skip_color - base_addr + 1] = (skip_color_addr - (beq_skip_color + 2)) & 0xFF

    apply_settings_addr = base_addr + len(code)
    code[jmp_apply_settings - base_addr + 1] = apply_settings_addr & 0xFF
    code[jmp_apply_settings - base_addr + 2] = (apply_settings_addr >> 8) & 0xFF

    code += [0xAD, 0x01, 0x02]  # LDA $0201
    code += [0x8D, 0x21, 0xD0]  # STA $D021
    code += [0x8D, 0x20, 0xD0]  # STA $D020

    code += [0xAD, 0x00, 0x02]  # LDA $0200
    code += [0xC9, 0x00]  # CMP #$00

    apply_multi_addr = base_addr + len(code)
    code += [0xF0, 0x00]  # BEQ apply_multi

    code += [0xA9, 0x3B, 0x8D, 0x11, 0xD0]  # LDA #$3B; STA $D011
    code += [0xA9, 0x08, 0x8D, 0x16, 0xD0]  # LDA #$08; STA $D016
    code += [0xA9, 0x18, 0x8D, 0x18, 0xD0]  # LDA #$18; STA $D018

    jmp_flip_addr = base_addr + len(code)
    code += [0x4C, 0x00, 0x00]  # JMP do_flip

    patched_multi_addr = base_addr + len(code)
    code[apply_multi_addr - base_addr + 1] = (patched_multi_addr - (apply_multi_addr + 2)) & 0xFF

    code += [0xA9, 0x3B, 0x8D, 0x11, 0xD0]  # LDA #$3B; STA $D011
    code += [0xA9, 0x18, 0x8D, 0x16, 0xD0]  # LDA #$18; STA $D016
    code += [0xA9, 0x18, 0x8D, 0x18, 0xD0]  # LDA #$18; STA $D018

    do_flip_addr = base_addr + len(code)
    code[jmp_flip_addr - base_addr + 1] = do_flip_addr & 0xFF
    code[jmp_flip_addr - base_addr + 2] = (do_flip_addr >> 8) & 0xFF

    code += [0xAD, 0x00, 0xDD]  # LDA $DD00
    code += [0x49, 0x01]  # EOR #$01
    code += [0x8D, 0x00, 0xDD]  # STA $DD00

    code += [0xA5, 0x03]  # LDA $03
    code += [0x49, 0x01]  # EOR #$01
    code += [0x85, 0x03]  # STA $03

    code += [0x4C, main_loop_addr & 0xFF, (main_loop_addr >> 8) & 0xFF]

    return bytes(code)


def _build_streamer_crt():
    """Build an EasyFlash 3 CRT containing the streamer code."""
    header = b"C64 CARTRIDGE   "
    header += struct.pack(">I", 0x40)
    header += struct.pack(">H", 0x0100)
    header += struct.pack(">H", 32)
    header += b"\x00"
    header += b"\x00"
    header += b"\x00" * 6
    header += b"ESPSTREAMER".ljust(32, b"\x00")

    rom_data = bytearray(16384)

    rom_data[0x3FFC] = 0x00
    rom_data[0x3FFD] = 0x80
    rom_data[0x3FFE] = 0x00
    rom_data[0x3FFF] = 0x80

    rom_data[0:9] = b"\x00\x80\x00\x80\xC3\xC2\xCD\x38\x30"

    code = _build_streamer_code(0x8009)
    rom_data[0x09 : 0x09 + len(code)] = code

    chip_header = b"CHIP"
    chip_header += struct.pack(">I", 16384 + 0x10)
    chip_header += struct.pack(">H", 0x0000)
    chip_header += struct.pack(">H", 0x0000)
    chip_header += struct.pack(">H", 0x8000)
    chip_header += struct.pack(">H", 16384)

    return header + chip_header + rom_data


def _build_streamer_prg():
    """Build the C64 streamer PRG."""
    code = [
        0x01,
        0x08,
        0x0B,
        0x08,
        0x0A,
        0x00,
        0x9E,
        0x32,
        0x30,
        0x36,
        0x31,
        0x00,
        0x00,
        0x00,
    ]

    code.extend(_build_streamer_code(0x080D))

    return bytes(code)


STREAMER_PRG = _build_streamer_prg()
STREAMER_CRT = _build_streamer_crt()
