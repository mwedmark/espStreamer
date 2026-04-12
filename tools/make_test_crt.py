#!/usr/bin/env python3
"""
make_test_crt.py  -  EasyFlash full-pipeline test
==================================================
Key finding from previous tests:
  - VIC-II $D020/$D021/$D018 writes work from Ultimax (I/O area) OK
  - Color RAM $D800 writes work from Ultimax (I/O area) OK
  - Screen RAM $0400-$07FF writes from Ultimax are IGNORED by VICE ✗
  - BUT: $0801+ is above screen RAM and should be writable in Ultimax

This test mirrors the EXACT ESP32 CRT architecture:
  Phase 1 (ROMH $E000): copies Phase 2 to RAM at $0200,  JMP $0200
  Phase 2 (RAM $0200):  copies ROML bank 1 to $0801     (bank 1, full 8KB)
                        disables EasyFlash cart
                        sets border = RED (checkpoint: Phase 2 reached)
                        JMP $0801
  Payload  (RAM $0801): actual program, does ALL screen ops in normal mode
                        sets border = YELLOW (checkpoint: payload reached)
                        clears screen, sets color RAM, writes HELLO WORLD

Diagnostic:
  RED border after boot   -> Phase 2 ran, $DE02/$DFFF disable attempted
  YELLOW border           -> Payload at $0801 ran successfully (full pipeline OK)
  White/blue stripes      -> Screen clear still Ultimax-blocked (disable failed)
  Clean HELLO WORLD       -> Full success! OK
"""

import struct

# ── Payload program (assembled for runtime $0801) ─────────────────────────
# This is what gets copied to $0801 by Phase 2 and runs in (hopefully) normal mode.
# BNE offsets: both loops have 13-byte body -> BNE rel = -15 = 0xF1 OK

payload_asm = bytes([
    # --- try to disable cart again (belt & suspenders) ---
    0xA9,0x03,              # LDA #$03  invisible mode
    0x8D,0x02,0xDE,         # STA $DE02  (VICE mode reg)
    0x8D,0xFF,0xDF,         # STA $DFFF  (real-HW mode reg)
    # --- CPU init ---
    0x78,                   # SEI
    0xD8,                   # CLD
    0xA9,0x37, 0x85,0x01,   # LDA #$37 ; STA $01
    # --- VIC-II ---
    0xA9,0x1B, 0x8D,0x11,0xD0,   # text mode, DEN=1
    0xA9,0xC8, 0x8D,0x16,0xD0,   # standard CSEL/xscroll
    0xA9,0x15, 0x8D,0x18,0xD0,   # screen@$0400, charROM@$1000
    0xA9,0x07, 0x8D,0x20,0xD0,   # YELLOW border  <- checkpoint!
    0xA9,0x06, 0x8D,0x21,0xD0,   # BLUE background
    # --- clear screen $0400-$07FF with space ($20) ---
    0xA9,0x20, 0xA2,0x00,
    #   clear_loop: (13-byte body -> BNE rel=-15=0xF1)
    0x9D,0x00,0x04,         # STA $0400,X
    0x9D,0x00,0x05,         # STA $0500,X
    0x9D,0x00,0x06,         # STA $0600,X
    0x9D,0x00,0x07,         # STA $0700,X
    0xE8,                   # INX
    0xD0,0xF1,              # BNE clear_loop  (-15=0xF1 OK)
    # --- set color RAM $D800-$DBFF to WHITE ($01) ---
    0xA9,0x01, 0xA2,0x00,
    #   col_loop: (13-byte body -> BNE rel=-15=0xF1)
    0x9D,0x00,0xD8,         # STA $D800,X
    0x9D,0x00,0xD9,         # STA $D900,X
    0x9D,0x00,0xDA,         # STA $DA00,X
    0x9D,0x00,0xDB,         # STA $DB00,X
    0xE8,                   # INX
    0xD0,0xF1,              # BNE col_loop   (-15=0xF1 OK)
    # --- write HELLO WORLD to $0400-$040A ---
    # C64 uppercase screen codes: A-Z = 1-26, space=32
    0xA9,0x08, 0x8D,0x00,0x04,   # H
    0xA9,0x05, 0x8D,0x01,0x04,   # E
    0xA9,0x0C, 0x8D,0x02,0x04,   # L
    0xA9,0x0C, 0x8D,0x03,0x04,   # L
    0xA9,0x0F, 0x8D,0x04,0x04,   # O
    0xA9,0x20, 0x8D,0x05,0x04,   # (space)
    0xA9,0x17, 0x8D,0x06,0x04,   # W
    0xA9,0x0F, 0x8D,0x07,0x04,   # O
    0xA9,0x12, 0x8D,0x08,0x04,   # R
    0xA9,0x0C, 0x8D,0x09,0x04,   # L
    0xA9,0x04, 0x8D,0x0A,0x04,   # D
    # --- infinite loop ---
    # JMP self: address = $0801 + len(above) = computed below
])
# Append JMP self
inf_addr = 0x0801 + len(payload_asm)
payload_asm = payload_asm + bytes([0x4C, inf_addr & 0xFF, (inf_addr >> 8) & 0xFF])

print(f"Payload: {len(payload_asm)} bytes  ($0801–${0x0801 + len(payload_asm) - 1:04X})")
assert len(payload_asm) <= 8192, "Payload too big for one ROML bank"

# Verify BNE offsets in payload
base = 0x0801
# find clear_loop and col_loop offsets
# clear_loop starts at offset 41 (after LDA #$20, LDX #$00)
clear_loop_off = 8+2+4+6+6+6+6+4   # first 8 header bytes + SEI+CLD+LDA/STA etc
# Actually let's just calculate from byte array
cl_start = None
col_start = None
idx = 0
# scan for the A9,20 (LDA #$20)
for i in range(len(payload_asm)-1):
    if payload_asm[i] == 0xA9 and payload_asm[i+1] == 0x20 and cl_start is None:
        cl_start = i + 4  # skip LDA#$20 + LDX#$00
        break

for i in range(cl_start, len(payload_asm)-1):
    if payload_asm[i] == 0xA9 and payload_asm[i+1] == 0x01 and col_start is None:
        col_start = i + 4
        break

cl_bne_off = cl_start + 13   # 4xSTA(12) + INX(1) = 13 bytes before BNE
col_bne_off = col_start + 13

cl_rel = (base + cl_start) - (base + cl_bne_off + 2)
col_rel = (base + col_start) - (base + col_bne_off + 2)

print(f"  clear_loop BNE: target=${base+cl_start:04X}, pc_after=${base+cl_bne_off+2:04X}, rel={cl_rel} = 0x{cl_rel&0xFF:02X}")
print(f"  col_loop   BNE: target=${base+col_start:04X}, pc_after=${base+col_bne_off+2:04X}, rel={col_rel} = 0x{col_rel&0xFF:02X}")
assert payload_asm[cl_bne_off+1] == (cl_rel & 0xFF), f"clear_loop BNE mismatch: expected 0x{cl_rel&0xFF:02X} got 0x{payload_asm[cl_bne_off+1]:02X}"
assert payload_asm[col_bne_off+1] == (col_rel & 0xFF), f"col_loop BNE mismatch: expected 0x{col_rel&0xFF:02X} got 0x{payload_asm[col_bne_off+1]:02X}"
print("  BNE offsets match embedded bytes OK")

# ── Phase 2 (assembled for runtime $0200) ─────────────────────────────────
# nBanks = 1 -> CMP #2 (= nBanks+1)
n_banks = 1
phase2 = bytes([
    0xA9,0x01,              # $0200 LDA #1  first data bank
    0x85,0xFD,              # $0202 STA $FD
    0xA9,0x01,              # $0204 LDA #1  dst lo ($0801)
    0x85,0xFB,              # $0206 STA $FB
    0xA9,0x08,              # $0208 LDA #$08  dst hi
    0x85,0xFC,              # $020A STA $FC
    # copy_bank ($020C):
    0xA5,0xFD,              # LDA $FD
    0x8D,0x00,0xDE,         # STA $DE00  select bank
    0xA9,0x00, 0x85,0xFE,   # LDA #0 ; STA $FE  src lo
    0xA9,0x80, 0x85,0xFF,   # LDA #$80 ; STA $FF  src hi -> $8000
    0xA9,0x20,              # LDA #$20
    0x8D,0x00,0x03,         # STA $0300  page counter (32 pages)
    # page_loop ($021E):
    0xA0,0x00,              # LDY #0
    # byte_loop ($0220):
    0xB1,0xFE,              # LDA ($FE),Y
    0x91,0xFB,              # STA ($FB),Y
    0xC8,                   # INY
    0xD0,0xF9,              # BNE byte_loop  (rel=-7)
    0xE6,0xFC,              # INC $FC
    0xE6,0xFF,              # INC $FF
    0xCE,0x00,0x03,         # DEC $0300
    0xD0,0xEE,              # BNE page_loop  (rel=-18)
    0xE6,0xFD,              # INC $FD
    0xA5,0xFD,              # LDA $FD
    0xC9,(n_banks+1),       # CMP #nBanks+1
    0xD0,0xD4,              # BNE copy_bank  (rel=-44)
    # done: disable cart, set RED border (checkpoint), JMP $0801
    0xA9,0x03,              # LDA #$03  invisible mode
    0x8D,0x02,0xDE,         # STA $DE02  VICE mode
    0x8D,0xFF,0xDF,         # STA $DFFF  real-HW mode
    0xA9,0x02,              # LDA #$02  RED border = checkpoint: Phase2 done
    0x8D,0x20,0xD0,         # STA $D020
    0x4C,0x01,0x08,         # JMP $0801
])

print(f"Phase 2: {len(phase2)} bytes (${0x0200:04X}–${0x0200+len(phase2)-1:04X})")

# Verify key Phase 2 BNE offsets
b2 = 0x0200
# byte_loop BNE at relative offset 32+2=34 -> absolute $0222; PC_after=$0227; target=$0220
# DEC $0300 / BNE page_loop: at relative 39+2=41? let me check positions
# BNE copy_bank: 
copy_bank_abs = b2 + 12   # 12 bytes of init
# CMP and BNE: at offset 48,50 of phase2
cmp_idx = next(i for i in range(len(phase2)) if phase2[i]==0xC9)
bne_cb_pc_after = b2 + cmp_idx + 4  # CMP(2) + BNE(2)
bne_cb_rel = copy_bank_abs - bne_cb_pc_after
print(f"  copy_bank BNE: target=${copy_bank_abs:04X}, pc_after=${bne_cb_pc_after:04X}, rel={bne_cb_rel} = 0x{bne_cb_rel&0xFF:02X}")
assert phase2[cmp_idx+3] == (bne_cb_rel & 0xFF), f"copy_bank BNE mismatch!"
print("  Phase 2 copy_bank BNE OK")

# ── Phase 1 (assembled for runtime $E000) ─────────────────────────────────
p2_len = len(phase2)          # 72 bytes
p1_ldx = p2_len - 1           # LDX #71 = copy 72 bytes (index 71..0)
romh_p2_start = 0x17          # Phase 2 starts at ROMH offset $17 = $E017

phase1 = bytes([
    0x78,                       # $E000 SEI
    0xD8,                       # $E001 CLD
    0xA2,0xFF,                  # $E002 LDX #$FF
    0x9A,                       # $E004 TXS
    0xA9,0x37, 0x85,0x01,       # $E005 LDA #$37 ; STA $01
    0xA2, p1_ldx,               # $E009 LDX #(p2_len-1)
    # copy_loop at $E00B:
    0xBD, romh_p2_start, 0xE0,  # $E00B LDA $E017,X
    0x9D, 0x00, 0x02,           # $E00E STA $0200,X
    0xCA,                       # $E011 DEX
    0x10, 0xF7,                 # $E012 BPL copy_loop  (PC=$E014,target=$E00B,rel=-9=0xF7)
    0x4C, 0x00, 0x02,           # $E014 JMP $0200
])
assert len(phase1) == 23, f"Phase1 wrong size: {len(phase1)}"
print(f"Phase 1: {len(phase1)} bytes ($E000-$E016)")
print(f"  LDX #{p1_ldx} (copy {p2_len} bytes of Phase 2 to $0200)")
assert romh_p2_start == len(phase1), f"Phase2 should start at ROMH offset {len(phase1)}, not {romh_p2_start}"

# ── Build ROMH bank (8KB) ─────────────────────────────────────────────────
ROMH = bytearray(0xFF for _ in range(8192))
ROMH[0:len(phase1)] = phase1
ROMH[len(phase1):len(phase1)+len(phase2)] = phase2
ROMH[0x1FFA] = 0x00; ROMH[0x1FFB] = 0xE0  # NMI  -> $E000
ROMH[0x1FFC] = 0x00; ROMH[0x1FFD] = 0xE0  # RESET-> $E000
ROMH[0x1FFE] = 0x01; ROMH[0x1FFF] = 0xE0  # IRQ  -> $E001 (SEI keeps off)

# ── Build ROML bank 1 (8KB) with payload ─────────────────────────────────
ROML1 = bytearray(0xFF for _ in range(8192))
ROML1[0:len(payload_asm)] = payload_asm

# ── CRT file builder ──────────────────────────────────────────────────────
def crt_header(name):
    h = bytearray(64)
    h[0:16] = b"C64 CARTRIDGE   "
    struct.pack_into(">I", h, 0x10, 64)
    struct.pack_into(">H", h, 0x14, 0x0100)
    struct.pack_into(">H", h, 0x16, 32)   # EasyFlash type
    h[0x20:0x20+len(name)] = name.encode("ascii")[:32]
    return bytes(h)

def chip(bank, addr, data):
    pkt = bytearray(16 + 8192)
    pkt[0:4] = b"CHIP"
    struct.pack_into(">I", pkt, 4, 16 + 8192)
    struct.pack_into(">H", pkt, 8,  0)
    struct.pack_into(">H", pkt, 10, bank)
    struct.pack_into(">H", pkt, 12, addr)
    struct.pack_into(">H", pkt, 14, 8192)
    pkt[16:] = data
    return bytes(pkt)

ROML0 = bytes(0xFF for _ in range(8192))  # bank 0 ROML empty

crt = (crt_header("PIPELINE TEST")
       + chip(0, 0x8000, ROML0)
       + chip(0, 0xA000, bytes(ROMH))
       + chip(1, 0x8000, bytes(ROML1))
       + chip(1, 0xA000, ROML0))          # bank 1 ROMH empty

with open("test_hello.crt", "wb") as f:
    f.write(crt)

print(f"\nWritten {len(crt)} bytes -> test_hello.crt")
print()
print("EXPECTED BOOT SEQUENCE:")
print("  1. ROMH $E000: Phase 1 copies Phase 2 to $0200, JMP $0200")
print("  2. RAM  $0200: Phase 2 copies ROML bank1 to $0801, disables cart")
print("            -> border turns RED (Phase 2 checkpoint)")
print("  3. RAM  $0801: Payload VIC-II init, screen clear, HELLO WORLD")
print("            -> border turns YELLOW (payload checkpoint)")
print()
print("RESULT GUIDE:")
print("  YELLOW border + clean HELLO WORLD  -> FULL PIPELINE WORKS OK")
print("  RED border + stripes               -> Phase 2 ran, cart disable failed")
print("  Light-blue border (unchanged)      -> Phase 1/2 didn't run")
print("  Brown/red border + black screen    -> Phase 2 ran, cart disable worked but payload crashed")
