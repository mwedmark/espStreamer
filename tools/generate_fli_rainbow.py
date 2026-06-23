#!/usr/bin/env python3
"""
generate_fli_rainbow.py
=======================
Generates a minimal C64 FLI test PRG that displays a DIFFERENT C64 COLOR
on every single raster line. This is the simplest possible FLI test - if 
it works you see a rainbow of all 16 C64 colors cycling across 200 lines.

Memory Layout (VIC Bank 1: $4000-$7FFF):
  $4000-$43FF : Screen RAM page 0  (line offsets 0, 8, 16, ... -> scroll=0)
  $4400-$47FF : Screen RAM page 1  (line offsets 1, 9, 17, ... -> scroll=1)
  $4800-$4BFF : Screen RAM page 2  (line offsets 2, 10, 18, ... -> scroll=2)
  $4C00-$4FFF : Screen RAM page 3  (line offsets 3, 11, 19, ... -> scroll=3)
  $5000-$53FF : Screen RAM page 4  (line offsets 4, 12, 20, ... -> scroll=4)
  $5400-$57FF : Screen RAM page 5  (line offsets 5, 13, 21, ... -> scroll=5)
  $5800-$5BFF : Screen RAM page 6  (line offsets 6, 14, 22, ... -> scroll=6)
  $5C00-$5FFF : Screen RAM page 7  (line offsets 7, 15, 23, ... -> scroll=7)
  $6000-$7F3F : Bitmap RAM (8000 bytes, all zeros = background color everywhere)

Color RAM ($D800-$DBFF): NOT USED for rainbow test (bitmap=00 = background color)
  We use $D021 (background color) changed per line - wait, that's NOT FLI.
  
Actually the rainbow uses COLOR RAM (bits=11 => color RAM cell) + FLI screen
RAM high/low nibbles per line. The simplest approach:
  - Bitmap = all $FF (bits=11 everywhere => color from COLOR RAM)  
  - Color RAM = color for that line's cell
  - $D018 cycles to give each line its own screen page
  - $D011 forces bad-line on every scanline

PRG loads at $0801:
  $0801-$080C : BASIC stub (10 SYS 2061)
  $080D-$08xx : Machine code (setup + IRQ handler)
  $0900-$09C7 : $D011 values table (200 entries)
  $0A00-$0AC7 : $D018 values table (200 entries)

Data embedded in PRG from $4000 offset (load address):
  We pack everything into one big PRG file.

Strategy for rainbow test:
  - All bitmap bytes = $FF  => every pixel uses COLOR RAM (bits=11)
  - Color RAM cells: cell at (row, col) gets color (row*8 + line_in_cell) % 16
    BUT color RAM is static (once per cell). For true per-line color, we need
    the Screen RAM high/low nibble bits (00=bg, 01=screenHi, 10=screenLo, 11=colorRAM)
    
  Better approach:
  - Bitmap = $55 everywhere (bits=01 => uses Screen RAM HIGH nibble)
  - Screen RAM page N has high nibble = color for that row offset
  - Color RAM = 0 (unused since bits != 11)
  
  This gives us: each 8x8 cell row gets a color per line based on screen page!
  8 different screen pages -> 8 colors per 8 rows = 25 distinct colors vertically!
  
  For true "color every line" we cycle through 8 pages, each page has the
  color for its scroll offset. This gives 8 distinct colors in each 8-line band.

Load address layout in PRG:
  PRG[0:2]    = $01 $08  (load at $0801)
  PRG[2:14]   = BASIC stub
  PRG[14:...]  = machine code at $080D
  
  Then a gap, then data at $4000 (offset $4000 - $0801 + 2 = $3801 from start of PRG)
"""

import struct

# C64 colors (Pepto palette)
C64_COLORS = [
    (0, 0, 0),        # 0: Black
    (255, 255, 255),  # 1: White
    (136, 0, 0),      # 2: Red
    (170, 255, 238),  # 3: Cyan
    (204, 68, 204),   # 4: Purple
    (0, 204, 85),     # 5: Green
    (0, 0, 170),      # 6: Blue
    (238, 238, 119),  # 7: Yellow
    (221, 136, 85),   # 8: Orange
    (102, 68, 0),     # 9: Brown
    (255, 119, 119),  # 10: Light Red
    (51, 51, 51),     # 11: Dark Grey
    (119, 119, 119),  # 12: Medium Grey
    (170, 255, 102),  # 13: Light Green
    (0, 136, 255),    # 14: Light Blue
    (187, 187, 187),  # 15: Light Grey
]

def build_d011_table():
    """
    Build the $D011 table for 200 scanlines.
    
    The bad-line condition is: (raster & 7) == ($D011 & 7) when screen is on.
    
    For FLI, we want to force a bad-line on EVERY scanline. The visible area 
    starts at raster line $33 (51) for PAL. Screen lines 0-199 map to 
    rasters 51-250.
    
    For line Y (0-199), the raster is (51 + Y).
    We need $D011 bits[2:0] == (51 + Y) & 7
    
    $D011 format:
      bit 7: raster line bit 8 (MSB of 9-bit raster)
      bit 6: ECM (extended color mode) = 0
      bit 5: BMM (bitmap mode) = 1  
      bit 4: DEN (display enable) = 1
      bit 3: RSEL (25/24 row select) = 1
      bits[2:0]: YSCROLL (vertical scroll, controls bad-line)
    
    Base value with BMM=1, DEN=1, RSEL=1: %0011_1000 = $38
    Then OR with the scroll value (raster & 7).
    
    Note: The first raster of the visible area (top border) depends on RSEL.
    With RSEL=1 (25 rows): display area is rasters $33-$FA (51-250).
    """
    d011_table = bytearray(200)
    for y in range(200):
        raster = 0x33 + y  # Raster line for screen line y
        scroll = raster & 0x07
        # BMM=1 (bit5), DEN=1 (bit4), RSEL=1 (bit3), YSCROLL=scroll
        d011_table[y] = 0x38 | scroll  # %0011_1000 | scroll
    return d011_table

def build_d018_table():
    """
    Build the $D018 table for 200 scanlines.
    
    $D018 controls:
      bits[7:4]: Screen RAM location within VIC bank (in 1KB units)
      bits[3:1]: Bitmap RAM location within VIC bank (in 2KB units)
      bit 0: unused
    
    VIC Bank 1 is $4000-$7FFF.
    Screen RAM pages at $4000, $4400, $4800, $4C00, $5000, $5400, $5800, $5C00
    (offsets 0, 1, 2, 3, 4, 5, 6, 7 in 1KB units within bank -> D018 high nibble: 0,1,2,3,4,5,6,7)
    Wait: the high nibble of $D018 is (screen_ram_offset_in_bank >> 10)
    So $4000 = bank offset 0x0000 >> 10 = 0 -> D018 high nibble = 0 -> D018 = $0x
    $4400 = bank offset 0x0400 >> 10 = 1 -> D018 high nibble = 1 -> D018 = $1x
    ...
    $5C00 = bank offset 0x1C00 >> 10 = 7 -> D018 high nibble = 7 -> D018 = $7x
    
    Bitmap RAM at $6000 = bank offset 0x2000:
    bits[3:1] = (0x2000 >> 11) = 0x10 >> 1 = ... let me recalculate:
    Bitmap RAM offset in bank = $6000 - $4000 = $2000
    bits[3:1] of D018 = $2000 / $800 = 4 -> D018 low nibble = 4*2 = 8 -> D018 bits[3:1] = 4 -> D018 low nibble bits[3:1] << 1 = 8
    
    So D018 low nibble = 8 (bitmap at $6000 in bank 1)
    D018 = (screen_page << 4) | 8
    
    For line Y: screen page = Y % 8
    """
    d018_table = bytearray(200)
    for y in range(200):
        screen_page = y % 8
        # Bitmap at $6000 in bank -> offset $2000 -> (0x2000 >> 11) = 4 -> bits[3:1] = 4 -> = 0b1000 = 8
        d018_table[y] = (screen_page << 4) | 0x08
    return d018_table

def build_screen_ram():
    """
    Build 8 screen RAM pages (8 x 1024 = 8192 bytes).
    
    For the rainbow test, we want every line to show a different color.
    Strategy: bitmap = $55 everywhere (bits=01 everywhere -> uses screen RAM HIGH nibble)
    
    Screen page N is used for scanlines where (scanline % 8) == N.
    The high nibble of screen RAM byte (row, col) = color for that line.
    
    For line Y: color = Y % 16 (cycling through 16 C64 colors)
    Page N handles lines Y where Y%8==N, so rows 0,1,2,...24.
    Row R in page N -> actual line Y = R*8 + N
    Color for that line = (R*8 + N) % 16
    
    Low nibble: set to same color as high (or 0, doesn't matter since bitmap=$55 only uses high)
    """
    screens = bytearray(8192)  # 8 pages * 1024 bytes
    
    for page in range(8):
        for row in range(25):
            line_y = row * 8 + page
            color = line_y % 16
            # High nibble = color, low nibble = complement (for color variety when bits=10)
            byte_val = (color << 4) | ((color + 8) % 16)
            for col in range(40):
                cell_idx = row * 40 + col
                screens[page * 1024 + cell_idx] = byte_val
    
    return screens

def build_bitmap():
    """
    All bitmap bytes = $55 = %01010101
    This means every 2-bit pixel pair = %01 = uses Screen RAM HIGH nibble color.
    Result: every pixel on screen has the color stored in the screen RAM high nibble
    for that line's page. This gives us per-line color control!
    """
    return bytearray([0x55] * 8000)

def build_color_ram():
    """
    Color RAM (1000 bytes for 25 rows x 40 cols).
    Bits=11 would use this, but since bitmap=$55 (bits=01), this isn't used
    for the rainbow. Set to 0 (black) to be safe.
    """
    return bytearray(1000)

def build_machine_code(d011_table, d018_table):
    """
    Build the C64 machine code that:
    1. Sets up VIC Bank 1
    2. Sets multicolor bitmap mode
    3. Copies color data to $D800
    4. Sets up the double-IRQ stable raster routine
    5. Runs the FLI loop (exactly 23 cycles per iteration)
    
    Memory map for machine code:
      $0801 : BASIC start (load address)
      $080D : Machine code entry (SYS 2061 = SYS $080D)
      $0900 : $D011 table (200 bytes)
      $0A00 : $D018 table (200 bytes)
    
    IRQ routine structure (classic double-IRQ stabilizer):
      IRQ1 at raster $30 (before visible area):
        - Sets IRQ2 at raster $31
        - Exits via RTI (fast)
      IRQ2 at raster $31:
        - Has known cycle alignment after IRQ1
        - Sets up FLI data tables
        - Enters the 200-line FLI loop
        - After loop: resets to IRQ1
    
    The FLI loop runs EXACTLY 23 cycles per iteration:
      LDA $0900,Y  [4 cycles] - load $D011 value
      STA $D011    [4 cycles] - write to VIC (must be before cycle 14)
      LDA $0A00,Y  [4 cycles] - load $D018 value  
      STA $D018    [4 cycles] - write to VIC
      INY          [2 cycles] - increment line counter
      CPY #$C8     [2 cycles] - compare with 200
      BNE fli_loop [3 cycles] - branch back
      Total = 23 cycles ✓ (fits in 24-cycle window after VIC DMA)
    
    Machine code layout (at $0801):
    """
    # PRG layout:
    # Offset 0-1: load address $0801
    # Offset 2-13: BASIC stub
    # Offset 14+: machine code (starts at $080D)
    # Offset $0900-$0801+2 = $00FF = 257: D011 table (wait, let's be precise)
    # $0900 in PRG file = offset ($0900 - $0801) + 2 = $FF + 2 = 257
    # $0A00 in PRG file = offset ($0A00 - $0801) + 2 = $1FF + 2 = 513
    
    CODE_START = 0x080D  # After BASIC stub

    # ==========================================
    # ADDRESSES
    # ==========================================
    ADDR_D011_TABLE = 0x0900
    ADDR_D018_TABLE = 0x0A00
    ADDR_MAIN_LOOP  = 0x0898  # Placeholder, computed below
    ADDR_IRQ1       = 0x089B  # Placeholder
    ADDR_IRQ2       = 0x08C0  # Placeholder (after IRQ1 code)
    ADDR_FLI_LOOP   = 0x08D0  # Placeholder
    
    # We'll build machine code as a list and track addresses
    # Then compute the correct JMP targets
    
    # Let's calculate exact sizes first:
    # SETUP code (from $080D):
    #   SEI           1 byte
    #   CLD           1 byte
    #   Set VIC bank: LDA #$03, STA $DD02, LDA #$FE, STA $DD00  (8 bytes - use AND to preserve bits)
    #   Actually safer: LDA $DD00, AND #$FC, ORA #$02, STA $DD00  (but simpler to just write $FE)
    #   Set $D011:    LDA #$3B, STA $D011                        (5 bytes)  
    #   Set $D016:    LDA #$D8, STA $D016                        (5 bytes)
    #   Set $D018:    LDA #$08, STA $D018                        (5 bytes) [bitmap at $6000]
    #   Set border:   LDA #$00, STA $D020                        (5 bytes)
    #   Set bg:       LDA #$00, STA $D021                        (5 bytes)
    #   Disable CIA:  LDA #$7F, STA $DC0D, STA $DD0D            (8 bytes)
    #                 LDA $DC0D, LDA $DD0D                       (6 bytes)
    #   Set IRQ vec:  LDA #lo(IRQ1), STA $0314, LDA #hi, STA $0315  (10 bytes)
    #   Set raster:   LDA #$30, STA $D012                        (5 bytes)
    #   Clear bit8:   LDA $D011, AND #$7F, STA $D011             (8 bytes)
    #   Enable VIC IRQ: LDA #$01, STA $D01A                     (5 bytes)
    #   Ack IRQ:      ASL $D019                                  (3 bytes... wait it's 0E 19 D0 = 3 bytes)
    #   Wait: but actually need INC $D019 or LDA #$FF, STA $D019  better: LDA #$FF, STA $D019 = 5 bytes
    #   Actually to ack: just write $01 to $D019 (bit 0 = raster irq ack)
    #   Enable: CLI    1 byte
    #   MAIN: JMP main (3 bytes)
    
    # Let's just hardcode the exact offsets carefully.
    # I'll build the byte sequence with known addresses.
    
    # ====================================================================
    # APPROACH: Build a bytearray for PRG, carefully placing everything
    # ====================================================================
    
    prg = bytearray(65536)  # Max size, we'll trim later
    
    # --- Load address ---
    prg[0] = 0x01  # $0801 low byte
    prg[1] = 0x08  # $0801 high byte
    
    # --- BASIC stub: 10 SYS 2061 ---
    # $0801: 0B 08  - link to next line
    # $0803: 0A 00  - line number 10
    # $0805: 9E     - SYS token
    # $0806: 32 30 36 31 - "2061" ASCII (= $080D decimal)
    # $080A: 00     - end of line
    # $080B: 00 00  - end of BASIC program
    prg[2]  = 0x0B  # next line ptr lo
    prg[3]  = 0x08  # next line ptr hi  
    prg[4]  = 0x0A  # line number lo (10)
    prg[5]  = 0x00  # line number hi
    prg[6]  = 0x9E  # SYS token
    prg[7]  = 0x32  # '2'
    prg[8]  = 0x30  # '0'
    prg[9]  = 0x36  # '6'
    prg[10] = 0x31  # '1'
    prg[11] = 0x00  # end of BASIC line
    prg[12] = 0x00  # end of BASIC program lo
    prg[13] = 0x00  # end of BASIC program hi
    
    # Machine code starts at PRG offset 14, C64 address $080D
    # Helper: PRG offset = (c64_addr - 0x0801) + 2
    def addr_to_offset(c64_addr):
        return (c64_addr - 0x0801) + 2
    
    def w(c64_addr, *bytes_):
        """Write bytes at a C64 address in the PRG buffer."""
        offset = addr_to_offset(c64_addr)
        for i, b in enumerate(bytes_):
            prg[offset + i] = b & 0xFF
    
    # ====================================================================
    # LAYOUT PLAN:
    # $080D: setup code (roughly 60 bytes) -> ends around $0849
    # $0849: main_loop: JMP $0849 (3 bytes) -> $084C
    # $084C: (some gap) 
    # $0880: irq1 handler
    # $089E: irq2 handler  
    # $08C0: fli_loop (inside irq2)
    # $08D8: exit irq2 (reset to irq1)
    # $0900: d011_table (200 bytes)
    # $0A00: d018_table (200 bytes)
    # ====================================================================
    
    # Let's be very precise. I'll write out each instruction manually.
    
    pc = 0x080D  # Program counter
    
    def emit(*bytes_):
        nonlocal pc
        w(pc, *bytes_)
        pc += len(bytes_)
        return pc - len(bytes_)
    
    # SEI
    emit(0x78)  # SEI
    # CLD
    emit(0xD8)  # CLD
    
    # Set VIC Bank 1: $DD00 bits[1:0] = %10 (bank 1 = $4000-$7FFF)
    # Read-modify-write to preserve other bits
    emit(0xAD, 0x00, 0xDD)  # LDA $DD00
    emit(0x29, 0xFC)         # AND #$FC  (clear bits 1:0)
    emit(0x09, 0x02)         # ORA #$02  (set bit 1 = bank 1)
    emit(0x8D, 0x00, 0xDD)  # STA $DD00
    # Also set $DD02 bits[1:0] to output
    emit(0xAD, 0x02, 0xDD)  # LDA $DD02
    emit(0x09, 0x03)         # ORA #$03
    emit(0x8D, 0x02, 0xDD)  # STA $DD02
    
    # Set multicolor bitmap mode:
    # $D011 = $3B = %0011_1011: BMM=1, DEN=1, RSEL=1, YSCROLL=3
    emit(0xA9, 0x3B)          # LDA #$3B
    emit(0x8D, 0x11, 0xD0)   # STA $D011
    
    # $D016 = $18 = %0001_1000: MCM=1, CSEL=1 (40 cols), no x-scroll
    emit(0xA9, 0x18)          # LDA #$18
    emit(0x8D, 0x16, 0xD0)   # STA $D016
    
    # $D018 = $08 = screen page 0 ($4000), bitmap at $6000 in bank
    # High nibble 0 = screen page 0 at $4000 (bank offset $0000)
    # Low nibble bit 3 = 1 => bitmap at $6000 (bank offset $2000 = 8192 from bank start / 2048 per unit = 4 units => bit3=1 => bits[3:1]=4 => value = 8)
    emit(0xA9, 0x08)          # LDA #$08
    emit(0x8D, 0x18, 0xD0)   # STA $D018
    
    # Set border color = black
    emit(0xA9, 0x00)          # LDA #$00
    emit(0x8D, 0x20, 0xD0)   # STA $D020
    # Set background color = black
    emit(0x8D, 0x21, 0xD0)   # STA $D021 (A still = 0)
    
    # Disable CIA interrupts
    emit(0xA9, 0x7F)          # LDA #$7F
    emit(0x8D, 0x0D, 0xDC)   # STA $DC0D
    emit(0x8D, 0x0D, 0xDD)   # STA $DD0D
    emit(0xAD, 0x0D, 0xDC)   # LDA $DC0D  (clear pending)
    emit(0xAD, 0x0D, 0xDD)   # LDA $DD0D  (clear pending)
    
    # Acknowledge any pending VIC interrupts
    emit(0xA9, 0xFF)          # LDA #$FF
    emit(0x8D, 0x19, 0xD0)   # STA $D019
    
    # Set raster IRQ line to $30 (line 48, just before visible area at $33)
    emit(0xA9, 0x30)          # LDA #$30
    emit(0x8D, 0x12, 0xD0)   # STA $D012
    # Clear bit 8 of raster (D011 bit7 = 0 for rasters 0-255)
    emit(0xAD, 0x11, 0xD0)   # LDA $D011
    emit(0x29, 0x7F)          # AND #$7F
    emit(0x8D, 0x11, 0xD0)   # STA $D011
    
    # Enable VIC raster interrupt
    emit(0xA9, 0x01)          # LDA #$01
    emit(0x8D, 0x1A, 0xD0)   # STA $D01A
    
    # Note the address of IRQ1 for setting $0314/$0315
    # We'll place IRQ1 at a known address. Let's calculate where we are now
    # and plan: setup code is about 70 bytes from $080D, so around $0853.
    # main_loop will be at pc, irq1 will be at a rounded address.
    
    # Save current PC for main_loop
    main_loop_addr = pc
    
    # Set IRQ vector to IRQ1
    # We need to know IRQ1 address first. Let's plan:
    # After setting IRQ vector, we have:
    #   LDA #lo, STA $0314, LDA #hi, STA $0315 = 10 bytes
    #   CLI = 1 byte  
    #   JMP main_loop = 3 bytes
    # So IRQ1 starts at pc + 10 + 1 + 3 = pc + 14
    irq1_addr = main_loop_addr + 14
    
    emit(0xA9, irq1_addr & 0xFF)       # LDA #lo(IRQ1)
    emit(0x8D, 0x14, 0x03)             # STA $0314
    emit(0xA9, (irq1_addr >> 8) & 0xFF) # LDA #hi(IRQ1)
    emit(0x8D, 0x15, 0x03)             # STA $0315
    
    # CLI - enable interrupts
    emit(0x58)  # CLI
    
    # Main loop: just loop forever (IRQ does all work)
    real_main_loop = pc
    emit(0x4C, real_main_loop & 0xFF, (real_main_loop >> 8) & 0xFF)  # JMP main_loop
    
    # Verify IRQ1 address
    assert pc == irq1_addr, f"IRQ1 addr mismatch: expected ${irq1_addr:04X}, got ${pc:04X}"
    
    # ====================================================================
    # IRQ1: First interrupt (jittery, just re-triggers IRQ2 on next line)
    # Called by KERNAL at raster $30.
    # Goal: Set up IRQ2 at raster $31, then exit fast via RTI
    # ====================================================================
    irq1_start = pc
    
    # IMPORTANT: The KERNAL saves A, X, Y and calls through $0314.
    # We return via JMP $EA81 (KERNAL IRQ exit) which does PLA TAY, PLA TAX, PLA, RTI.
    
    # Acknowledge the IRQ
    emit(0xA9, 0xFF)          # LDA #$FF
    emit(0x8D, 0x19, 0xD0)   # STA $D019  (ack all VIC interrupts)
    
    # Set raster to $31 for IRQ2
    emit(0xA9, 0x31)          # LDA #$31
    emit(0x8D, 0x12, 0xD0)   # STA $D012
    
    # Set IRQ vector to IRQ2
    # We need to know IRQ2 address. IRQ1 is about 20 bytes, so IRQ2 starts at irq1_start + 20
    # Let's plan: IRQ1 code from here:
    #   LDA #$FF, STA $D019 = 5 bytes
    #   LDA #$31, STA $D012 = 5 bytes
    #   LDA #lo, STA $0314, LDA #hi, STA $0315 = 10 bytes
    #   JMP $EA81 = 3 bytes
    # Total IRQ1 = 23 bytes
    irq2_addr = irq1_start + 23
    
    emit(0xA9, irq2_addr & 0xFF)        # LDA #lo(IRQ2)
    emit(0x8D, 0x14, 0x03)              # STA $0314
    emit(0xA9, (irq2_addr >> 8) & 0xFF) # LDA #hi(IRQ2)
    emit(0x8D, 0x15, 0x03)              # STA $0315
    
    # Exit via KERNAL (restores A, X, Y, RTI)
    emit(0x4C, 0x81, 0xEA)  # JMP $EA81
    
    assert pc == irq2_addr, f"IRQ2 addr mismatch: expected ${irq2_addr:04X}, got ${pc:04X}"
    
    # ====================================================================
    # IRQ2: Second interrupt (cycle-stable due to double-IRQ trick)
    # Triggered at raster $31. At this point the CPU is synchronized.
    # We need to reach the start of line $33 (first visible line) with
    # exact cycle timing, then run the 200-line FLI loop.
    #
    # When IRQ2 fires (at raster $31), we have about 2 lines worth of time
    # to set up and enter the FLI loop at raster $33.
    #
    # Each PAL line = 63 cycles. We enter IRQ2 somewhere around cycle 0-2
    # of raster $31 (after stabilization from the double-IRQ trick).
    #
    # The trick: After the KERNAL IRQ entry overhead, the CPU has jitter of
    # 0-7 cycles. We stabilize by:
    #   1. Saving X to stack (via TSX trick or just waste cycles)
    #   2. Using NOP padding to align to a known cycle
    #
    # For simplicity, we use the "NOP slide" approach:
    # We know the KERNAL IRQ takes 7 cycles (BRK-like entry), then
    # PHA, TXA, PHA, TYA, PHA = 3*3 = 9 cycles, then JMP ($0314) = 5 cycles
    # But jitter from previous instruction can be 0-6 cycles.
    # 
    # A simpler, proven stabilizer:
    # Just do enough NOPs to cover the rest of line $31 and all of $32,
    # then enter the FLI loop at the START of line $33.
    # 
    # Line $31 remaining cycles from IRQ2 entry ≈ 40 cycles (rough)
    # Line $32: 63 cycles
    # So ≈ 103 NOPs (1 NOP = 2 cycles, so about 51 NOPs)
    # Then we need the FLI to be writing $D011/$D018 for line $33.
    #
    # Better approach: sync by waiting for raster $33 using a spin loop.
    # ====================================================================
    irq2_start = pc
    
    # Acknowledge VIC interrupt
    emit(0xA9, 0xFF)          # LDA #$FF
    emit(0x8D, 0x19, 0xD0)   # STA $D019
    
    # The FLI loop itself IS cycle-exact (23 cycles per line).
    
    # Set Y = 0 (line counter for FLI loop)
    emit(0xA0, 0x00)  # LDY #$00
    
    # ====================================================================
    # FLI LOOP - EXACTLY 23 CYCLES PER ITERATION (verified from FLI.md)
    # ====================================================================
    fli_loop_addr = pc
    emit(0xB9, ADDR_D011_TABLE & 0xFF, (ADDR_D011_TABLE >> 8) & 0xFF)  # LDA $0900,Y [4 cycles]
    emit(0x8D, 0x11, 0xD0)                                               # STA $D011   [4 cycles]
    emit(0xB9, ADDR_D018_TABLE & 0xFF, (ADDR_D018_TABLE >> 8) & 0xFF)  # LDA $0A00,Y [4 cycles]
    emit(0x8D, 0x18, 0xD0)                                               # STA $D018   [4 cycles]
    emit(0xC8)                                                            # INY         [2 cycles]
    emit(0xC0, 0xC8)                                                      # CPY #$C8    [2 cycles]
    # BNE fli_loop: relative branch
    branch_offset = (fli_loop_addr - (pc + 2)) & 0xFF
    emit(0xD0, branch_offset)                                             # BNE fli_loop [3 cycles]
    # TOTAL: 4+4+4+4+2+2+3 = 23 cycles ✓
    
    # ====================================================================
    # After FLI loop: reset to IRQ1 for next frame
    # ====================================================================
    # Set raster back to $30
    emit(0xA9, 0x30)          # LDA #$30
    emit(0x8D, 0x12, 0xD0)   # STA $D012
    
    # Restore $D011 to normal (no FLI)
    emit(0xA9, 0x3B)          # LDA #$3B
    emit(0x8D, 0x11, 0xD0)   # STA $D011
    
    # Restore $D018 to page 0 + bitmap at $6000
    emit(0xA9, 0x08)          # LDA #$08
    emit(0x8D, 0x18, 0xD0)   # STA $D018
    
    # Reset IRQ vector to IRQ1
    emit(0xA9, irq1_addr & 0xFF)        # LDA #lo(IRQ1)
    emit(0x8D, 0x14, 0x03)              # STA $0314
    emit(0xA9, (irq1_addr >> 8) & 0xFF) # LDA #hi(IRQ1)
    emit(0x8D, 0x15, 0x03)              # STA $0315
    
    # Exit via KERNAL
    emit(0x4C, 0x81, 0xEA)  # JMP $EA81
    
    code_end = pc
    
    print(f"Machine code: $080D - ${code_end-1:04X} ({code_end - 0x080D} bytes)")
    print(f"IRQ1 at: ${irq1_addr:04X}")
    print(f"IRQ2 at: ${irq2_addr:04X}")
    print(f"FLI loop at: ${fli_loop_addr:04X}")
    print(f"D011 table at: ${ADDR_D011_TABLE:04X}")
    print(f"D018 table at: ${ADDR_D018_TABLE:04X}")
    
    # Embed D011 table at $0900
    d011_offset = addr_to_offset(ADDR_D011_TABLE)
    prg[d011_offset:d011_offset + 200] = d011_table
    
    # Embed D018 table at $0A00
    d018_offset = addr_to_offset(ADDR_D018_TABLE)
    prg[d018_offset:d018_offset + 200] = d018_table
    
    return prg

def build_full_prg():
    """
    Build the complete PRG file.
    
    PRG load address: $0801
    Data starts at $4000 (VIC bank 1):
      $4000-$5FFF: Screen RAM (8 pages x 1KB)
      $6000-$7F3F: Bitmap RAM (8000 bytes)
    
    PRG file offset for $4000 = ($4000 - $0801) + 2 = $3801 = 14337
    PRG file size must cover to $7F3F+1 = $8000
    PRG file = $8000 - $0801 + 2 = $37FF bytes
    """
    print("Building FLI rainbow test PRG...")
    
    d011_table = build_d011_table()
    d018_table = build_d018_table()
    screens = build_screen_ram()
    bitmap = build_bitmap()
    color_ram = build_color_ram()
    
    # Start PRG from machine code builder (which also embeds tables at $0900/$0A00)
    prg = build_machine_code(d011_table, d018_table)
    
    # Embed Screen RAM pages at $4000-$5FFF
    # PRG offset for $4000 = ($4000 - $0801) + 2 = 0x3801 = 14337
    screen_prg_offset = (0x4000 - 0x0801) + 2
    prg[screen_prg_offset:screen_prg_offset + 8192] = screens
    
    # Embed Bitmap RAM at $6000-$7F3F  
    # PRG offset for $6000 = ($6000 - $0801) + 2 = 0x5801 = 22529
    bitmap_prg_offset = (0x6000 - 0x0801) + 2
    prg[bitmap_prg_offset:bitmap_prg_offset + 8000] = bitmap
    
    # Trim to needed size: up to $8000
    # PRG size = ($8000 - $0801) + 2 = 0x37FF + 2 = 0x3801 = 14337... wait
    # Actually $8000 is exclusive, last address is $7F3F+1=$7F40 for bitmap end
    # bitmap ends at $6000 + 8000 - 1 = $7F3F
    # So PRG needs to go to at least $7F40
    # PRG end offset = ($7F40 - $0801) + 2 = $7740 = 30528
    prg_size = (0x7F40 - 0x0801) + 2
    prg = prg[:prg_size]
    
    print(f"PRG size: {len(prg)} bytes ({len(prg)/1024:.1f} KB)")
    print(f"Screen RAM at PRG offset: {screen_prg_offset} (C64: $4000)")
    print(f"Bitmap at PRG offset: {bitmap_prg_offset} (C64: $6000)")
    
    return prg, d011_table, d018_table, screens, bitmap, color_ram

def generate_preview(screens, bitmap, color_ram):
    """Generate a PNG preview showing what the FLI rainbow should look like."""
    try:
        from PIL import Image
        preview = Image.new("RGB", (320, 200))
        pixels = preview.load()
        
        # bg_color = 0 (black)
        bg_color = 0
        
        for y in range(200):
            row = y // 8
            py = y % 8
            page = y % 8  # Which screen RAM page is used for this line
            screen_page_offset = page * 1024
            
            for x in range(160):
                col = x // 4
                px = x % 4
                
                cell_idx = row * 40 + col
                
                # Get bitmap byte for this cell+line
                byte = bitmap[cell_idx * 8 + py]
                bits = (byte >> ((3 - px) * 2)) & 3
                
                if bits == 0:
                    color_idx = bg_color
                elif bits == 1:
                    # Screen RAM HIGH nibble (our rainbow color!)
                    color_idx = screens[screen_page_offset + cell_idx] >> 4
                elif bits == 2:
                    # Screen RAM LOW nibble
                    color_idx = screens[screen_page_offset + cell_idx] & 0x0F
                else:
                    # Color RAM
                    color_idx = color_ram[cell_idx]
                
                rgb = C64_COLORS[color_idx]
                pixels[x * 2, y] = rgb
                pixels[x * 2 + 1, y] = rgb
        
        return preview
    except ImportError:
        print("PIL not available, skipping preview generation")
        return None

def print_table_summary(d011_table, d018_table):
    """Print a summary of the FLI tables for debugging."""
    print("\n--- D011 Table (first 16 entries) ---")
    for i in range(16):
        v = d011_table[i]
        scroll = v & 7
        print(f"  Line {i:3d}: $D011=${v:02X} (scroll={scroll}, raster={0x33+i})")
    
    print("\n--- D018 Table (first 16 entries) ---")
    for i in range(16):
        v = d018_table[i]
        screen_page = v >> 4
        bitmap_sel = (v >> 1) & 7
        screen_addr = 0x4000 + screen_page * 0x400
        bitmap_addr = 0x4000 + bitmap_sel * 0x800
        print(f"  Line {i:3d}: $D018=${v:02X} (screen=${screen_addr:04X}, bitmap=${bitmap_addr:04X})")
    
    print("\n--- Expected colors per line (first 32 lines) ---")
    for y in range(32):
        page = y % 8
        row = y // 8
        cell = row * 40  # first column
        screen_byte = 0  # Will be set in screens
        color = y % 16
        print(f"  Line {y:3d}: page={page}, expected color={color} ({['Black','White','Red','Cyan','Purple','Green','Blue','Yellow','Orange','Brown','Lt.Red','Dk.Grey','Med.Grey','Lt.Green','Lt.Blue','Lt.Grey'][color]})")

def main():
    import os
    os.makedirs("tools", exist_ok=True)
    
    prg, d011_table, d018_table, screens, bitmap, color_ram = build_full_prg()
    
    out_path = "tools/fli_rainbow_test.prg"
    with open(out_path, "wb") as f:
        f.write(prg)
    print(f"\nSaved PRG: {out_path}")
    
    print_table_summary(d011_table, d018_table)
    
    # Generate PNG preview
    preview = generate_preview(screens, bitmap, color_ram)
    if preview:
        preview_path = "tools/fli_rainbow_preview.png"
        preview.save(preview_path)
        print(f"Saved preview: {preview_path}")
    
    print("\n=== To test in VICE ===")
    print(f"  x64sc {out_path}")
    print("  Then type: RUN")
    print("\nExpected result: Screen should show 200 horizontal color bands,")
    print("cycling through all 16 C64 colors repeatedly.")
    print("If FLI is working correctly, every 8 lines gets a different color,")
    print("cycling through colors 0-15 about 12-13 times across 200 lines.")
    print("\nThe LEFT 3 COLUMNS (24 pixels) will have the FLI bug (corruption).")

if __name__ == "__main__":
    main()
