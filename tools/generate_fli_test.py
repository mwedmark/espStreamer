#!/usr/bin/env python3
"""
generate_fli_test.py
Generates a retro-synthwave C64 FLI test image containing a big "FLI IMAGE" chrome logo.
Outputs both a standard C64 .prg file (runnable in VICE) and a PNG preview.
"""

import os
import struct
from PIL import Image, ImageDraw, ImageFont

# Define C64 colors (Pepto Palette)
c64_colors = [
    (0, 0, 0),        # 0: Black
    (255, 255, 255),  # 1: White
    (104, 55, 43),    # 2: Red
    (112, 164, 178),  # 3: Cyan
    (111, 61, 134),   # 4: Purple
    (88, 141, 67),    # 5: Green
    (53, 40, 121),    # 6: Blue
    (184, 199, 111),  # 7: Yellow
    (111, 79, 37),    # 8: Orange
    (67, 57, 0),      # 9: Brown
    (154, 103, 89),   # 10: Light Red
    (68, 68, 68),     # 11: Dark Grey
    (108, 108, 108),  # 12: Medium Grey
    (154, 210, 132),  # 13: Light Green
    (108, 94, 181),   # 14: Light Blue
    (149, 149, 149),  # 15: Light Grey
]

def get_closest_c64_color(r, g, b):
    # Weighted Manhattan distance matching VIC-II perception
    best_dist = 999999
    best_idx = 0
    for idx, (cr, cg, cb) in enumerate(c64_colors):
        dist = abs(r - cr) * 2 + abs(g - cg) * 4 + abs(b - cb)
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return best_idx

def generate_chrome_image():
    print("Generating chrome image...")
    # Create 320x200 image
    img = Image.new("RGB", (320, 200), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Draw Deep Space Gradient Background
    for y in range(200):
        # Dark purple -> Dark blue
        factor = y / 200.0
        r = int(13 + (8 - 13) * factor)
        g = int(8 + (23 - 8) * factor)
        b = int(38 + (54 - 38) * factor)
        draw.line([(0, y), (320, y)], fill=(r, g, b))

    # 2. Draw Retro Synthwave Sun
    # Sun center (160, 95), radius 35
    sun_mask = Image.new("L", (320, 200), 0)
    sun_draw = ImageDraw.Draw(sun_mask)
    sun_draw.ellipse([(125, 60), (195, 130)], fill=255)

    # Cut horizontal stripes out of the bottom half of the sun
    for sy in range(100, 130, 4):
        sun_draw.rectangle([(120, sy), (200, sy + 2)], fill=0)

    # Sun gradient (Yellow at top, hot pink/magenta at bottom)
    sun_grad = Image.new("RGB", (320, 200))
    sg_draw = ImageDraw.Draw(sun_grad)
    for y in range(200):
        factor = max(0.0, min(1.0, (y - 60) / 70.0))
        sr = 255
        sg = int(230 * (1.0 - factor))
        sb = int(150 * factor)
        sg_draw.line([(0, y), (320, y)], fill=(sr, sg, sb))

    img.paste(sun_grad, mask=sun_mask)

    # 3. Draw Neon Pink Perspective Grid
    horizon_y = 120
    y_pos = horizon_y
    step = 2.0
    while y_pos < 200:
        draw.line([(0, int(y_pos)), (320, int(y_pos))], fill=(255, 0, 128), width=1)
        step *= 1.35
        y_pos += step

    # Grid perspective lines radiating from center of horizon
    for x_start in range(-160, 480, 24):
        draw.line([(x_start, 200), (160, horizon_y)], fill=(0, 255, 255), width=1)

    # 4. Draw Chrome Text "FLI IMAGE"
    # Find the best bold font
    font = None
    font_size = 44
    for fn in ["Impact.ttf", "arialbd.ttf", "Arial.ttf", "courbd.ttf"]:
        fp = os.path.join("C:\\Windows\\Fonts", fn)
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                print(f"Loaded font: {fn}")
                break
            except:
                pass

    if not font:
        font = ImageFont.load_default()
        print("Using fallback default font")

    text_val = "FLI IMAGE"
    
    # Get text bounds
    try:
        bbox = draw.textbbox((0, 0), text_val, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except AttributeError:
        text_w, text_h = draw.textsize(text_val, font=font)

    tx = (320 - text_w) // 2
    ty = (200 - text_h) // 2 - 10

    # Draw thick hot pink neon outline
    outline_color = (255, 0, 128)
    outline_mask = Image.new("L", (320, 200), 0)
    ol_draw = ImageDraw.Draw(outline_mask)
    for dx in [-2, -1, 0, 1, 2]:
        for dy in [-2, -1, 0, 1, 2]:
            if abs(dx) + abs(dy) > 0:
                ol_draw.text((tx + dx, ty + dy), text_val, fill=255, font=font)

    outline_img = Image.new("RGB", (320, 200), outline_color)
    img.paste(outline_img, mask=outline_mask)

    # Create the metallic chrome gradient (reflecting sky/ground horizon)
    chrome_grad = Image.new("RGB", (320, 200))
    cg_draw = ImageDraw.Draw(chrome_grad)
    text_center_y = ty + text_h // 2 + 5

    for y in range(200):
        if y < text_center_y:
            # Sky reflection: Dark Blue -> Cyan -> White
            factor = max(0.0, min(1.0, (y - ty) / max(1.0, text_center_y - ty)))
            cr = int(230 * factor)
            cg = int(255 * factor)
            cb = int(100 + 155 * factor)
        else:
            # Ground reflection: White -> Gold/Orange -> Dark Brown -> Black
            factor = max(0.0, min(1.0, (y - text_center_y) / max(1.0, ty + text_h - text_center_y)))
            if factor < 0.35:
                # White to Gold/Yellow
                f = factor / 0.35
                cr = 255
                cg = int(255 - 95 * f)
                cb = int(255 - 255 * f)
            else:
                # Gold/Yellow to Dark Brown
                f = (factor - 0.35) / 0.65
                cr = int(255 - 215 * f)
                cg = int(160 - 130 * f)
                cb = 0
        cg_draw.line([(0, y), (320, y)], fill=(cr, cg, cb))

    # Paste chrome gradient using the text mask
    text_mask = Image.new("L", (320, 200), 0)
    text_draw = ImageDraw.Draw(text_mask)
    text_draw.text((tx, ty), text_val, fill=255, font=font)
    img.paste(chrome_grad, mask=text_mask)

    return img

def encode_fli(img_320):
    # Downsample to C64 multicolor double-width pixels (160x200)
    img_160 = img_320.resize((160, 200), Image.Resampling.NEAREST)
    pixels = img_160.load()

    # Pre-map all pixels to standard C64 color indices
    c64_indices = []
    for y in range(200):
        row_indices = []
        for x in range(160):
            r, g, b = pixels[x, y][:3]
            row_indices.append(get_closest_c64_color(r, g, b))
        c64_indices.append(row_indices)

    # Initialize buffers
    bitmap_ram = bytearray(8000)
    screens = bytearray(8192)
    color_ram = bytearray(1000)
    bg_color = 0  # Black background

    # C64 FLI constraints packing loop
    for cy in range(25):
        for cx in range(40):
            cellIdx = cy * 40 + cx

            # 1. Color RAM Selection: Most common color in 4x8 block (excluding bg)
            counts = [0] * 16
            for py in range(8):
                for px in range(4):
                    col = c64_indices[cy * 8 + py][cx * 4 + px]
                    counts[col] += 1
            counts[bg_color] = -1
            cC = bg_color
            max_count = -1
            for i in range(16):
                if counts[i] > max_count:
                    max_count = counts[i]
                    cC = i
            if max_count <= 0:
                cC = bg_color

            color_ram[cellIdx] = cC

            # 2. Screen RAM Selection per scanline
            for py in range(8):
                l_counts = [0] * 16
                for px in range(4):
                    col = c64_indices[cy * 8 + py][cx * 4 + px]
                    l_counts[col] += 1
                l_counts[bg_color] = -1
                l_counts[cC] = -1

                # Find the two most common colors (c1 & c2) for this scanline segment
                c1 = bg_color
                c2 = bg_color
                m1 = 0
                m2 = 0
                for i in range(16):
                    if l_counts[i] > m1:
                        m2 = m1
                        c2 = c1
                        m1 = l_counts[i]
                        c1 = i
                    elif l_counts[i] > m2:
                        m2 = l_counts[i]
                        c2 = i

                if m1 == 0:
                    c1 = cC
                if m2 == 0:
                    c2 = c1

                screens[py * 1024 + cellIdx] = (c1 << 4) | (c2 & 0x0F)

                # 3. Map the 4 pixels to the 2-bit color slots:
                #    00 = bg_color, 01 = c1, 10 = c2, 11 = cC
                slots = [bg_color, c1, c2, cC]
                byte_val = 0
                for px in range(4):
                    col = c64_indices[cy * 8 + py][cx * 4 + px]
                    
                    # Find slot with best matching color
                    best_slot = 0
                    best_dist = 999999
                    for slot_idx, slot_col in enumerate(slots):
                        cr, cg, cb = c64_colors[col]
                        sr, sg, sb = c64_colors[slot_col]
                        dist = abs(cr - sr) * 2 + abs(cg - sg) * 4 + abs(cb - sb)
                        if dist < best_dist:
                            best_dist = dist
                            best_slot = slot_idx
                    byte_val |= (best_slot << ((3 - px) * 2))

                bitmap_ram[cellIdx * 8 + py] = 0 if cx < 3 else byte_val

    return bitmap_ram, screens, color_ram, bg_color

def save_fli_prg(bitmap_ram, screens, color_ram, bg_color, out_path):
    print(f"Saving C64 executable PRG to: {out_path}")

    # PRG loads at $0801. Full layout in VIC Bank 1 ($4000-$7FFF):
    #   $0900-$09C7 : D011 table (200 bytes)
    #   $0A00-$0AC7 : D018 table (200 bytes)
    #   $1000-$13E7 : Color RAM data (1000 bytes, copied to $D800 at startup)
    #   $4000-$5FFF : Screen RAM pages 0-7 (8 x 1024 bytes)
    #   $6000-$7F3F : Bitmap RAM (8000 bytes)
    prg = bytearray(30529)  # Spans $0801-$7F40

    # Load address $0801
    prg[0] = 0x01
    prg[1] = 0x08

    # BASIC stub: 10 SYS 2061 ($080D)
    prg[2:14] = [0x0B, 0x08, 0x0A, 0x00, 0x9E, 0x32, 0x30, 0x36, 0x31, 0x00, 0x00, 0x00]



    # Helper to write bytes at a C64 address into the PRG buffer
    def addr_to_offset(c64_addr):
        return (c64_addr - 0x0801) + 2

    pc = 0x080D  # Machine code starts here

    def emit(*bytes_):
        nonlocal pc
        offset = addr_to_offset(pc)
        for i, b in enumerate(bytes_):
            prg[offset + i] = b & 0xFF
        pc += len(bytes_)
        return pc - len(bytes_)

    # ----------------------------------------------------------------
    # BUILD D011 TABLE at $0900:
    # Forces a "bad line" on every scanline.
    # Bad-line condition: (raster & 7) == ($D011 & 7) when display enabled.
    # For screen line Y, raster = $33 + Y.
    # D011 = $38 | (raster & 7)  (BMM=1, DEN=1, RSEL=1, yscroll=raster&7)
    # ----------------------------------------------------------------
    d011_table = bytearray(200)
    for y in range(200):
        raster = 0x33 + y
        d011_table[y] = 0x38 | (raster & 0x07)

    # ----------------------------------------------------------------
    # BUILD D018 TABLE at $0A00:
    # Cycles through 8 screen RAM pages (one per scroll offset).
    # Screen pages at $4000,$4400,$4800,$4C00,$5000,$5400,$5800,$5C00
    # Bitmap at $6000 in bank -> bits[3:1] = 4 -> low nibble = $08
    # D018 = (page << 4) | $08
    # ----------------------------------------------------------------
    d018_table = bytearray(200)
    for y in range(200):
        page = y % 8
        d018_table[y] = (page << 4) | 0x08

    # ----------------------------------------------------------------
    # SETUP CODE at $080D
    # ----------------------------------------------------------------

    emit(0x78)                          # SEI
    emit(0xD8)                          # CLD

    # Set VIC Bank 1 ($4000-$7FFF): $DD00 bits[1:0] = %10
    emit(0xAD, 0x00, 0xDD)             # LDA $DD00
    emit(0x29, 0xFC)                    # AND #$FC
    emit(0x09, 0x02)                    # ORA #$02
    emit(0x8D, 0x00, 0xDD)             # STA $DD00
    emit(0xAD, 0x02, 0xDD)             # LDA $DD02
    emit(0x09, 0x03)                    # ORA #$03
    emit(0x8D, 0x02, 0xDD)             # STA $DD02

    # VIC modes: multicolor bitmap
    emit(0xA9, 0x3B)                    # LDA #$3B  (BMM=1, DEN=1, RSEL=1, yscroll=3)
    emit(0x8D, 0x11, 0xD0)             # STA $D011
    emit(0xA9, 0x18)                    # LDA #$18  (MCM=1, CSEL=1)
    emit(0x8D, 0x16, 0xD0)             # STA $D016
    emit(0xA9, 0x08)                    # LDA #$08  (screen page 0 at $4000, bitmap at $6000)
    emit(0x8D, 0x18, 0xD0)             # STA $D018

    # Border + background color
    emit(0xA9, bg_color)               # LDA #bg_color
    emit(0x8D, 0x20, 0xD0)             # STA $D020
    emit(0x8D, 0x21, 0xD0)             # STA $D021

    # Copy Color RAM from $1000 to $D800 (1000 bytes in 4 chunks of 250)
    emit(0xA2, 0x00)                    # LDX #$00
    # copy_loop (250 iterations, 4 pages):
    copy_loop = pc
    emit(0xBD, 0x00, 0x10)             # LDA $1000,X
    emit(0x9D, 0x00, 0xD8)             # STA $D800,X
    emit(0xBD, 0xFA, 0x10)             # LDA $10FA,X
    emit(0x9D, 0xFA, 0xD8)             # STA $D8FA,X
    emit(0xBD, 0xF4, 0x11)             # LDA $11F4,X
    emit(0x9D, 0xF4, 0xD9)             # STA $D9F4,X
    emit(0xBD, 0xEE, 0x12)             # LDA $12EE,X  (last 250 at $12EE)
    emit(0x9D, 0xEE, 0xDA)             # STA $DAEE,X
    emit(0xE8)                          # INX
    emit(0xE0, 0xFA)                    # CPX #$FA  (250)
    branch_back = (copy_loop - (pc + 2)) & 0xFF
    emit(0xD0, branch_back)             # BNE copy_loop

    # Disable CIA interrupts
    emit(0xA9, 0x7F)                    # LDA #$7F
    emit(0x8D, 0x0D, 0xDC)             # STA $DC0D
    emit(0x8D, 0x0D, 0xDD)             # STA $DD0D
    emit(0xAD, 0x0D, 0xDC)             # LDA $DC0D  (clear pending)
    emit(0xAD, 0x0D, 0xDD)             # LDA $DD0D

    # Acknowledge any pending VIC interrupt
    emit(0xA9, 0xFF)                    # LDA #$FF
    emit(0x8D, 0x19, 0xD0)             # STA $D019

    # Set raster IRQ to line $30 (just before visible area)
    emit(0xA9, 0x30)                    # LDA #$30
    emit(0x8D, 0x12, 0xD0)             # STA $D012
    emit(0xAD, 0x11, 0xD0)             # LDA $D011
    emit(0x29, 0x7F)                    # AND #$7F  (clear raster bit 8)
    emit(0x8D, 0x11, 0xD0)             # STA $D011

    # Enable VIC raster interrupt
    emit(0xA9, 0x01)                    # LDA #$01
    emit(0x8D, 0x1A, 0xD0)             # STA $D01A

    # Set IRQ vector to IRQ1 (address computed below: main_loop + 14)
    main_loop_addr = pc
    irq1_addr = main_loop_addr + 14    # 10 bytes vector set + 1 CLI + 3 JMP

    emit(0xA9, irq1_addr & 0xFF)        # LDA #lo(IRQ1)
    emit(0x8D, 0x14, 0x03)              # STA $0314
    emit(0xA9, (irq1_addr >> 8) & 0xFF) # LDA #hi(IRQ1)
    emit(0x8D, 0x15, 0x03)              # STA $0315

    emit(0x58)                           # CLI

    # main_loop: spin forever, IRQ does all work
    real_main = pc
    emit(0x4C, real_main & 0xFF, (real_main >> 8) & 0xFF)  # JMP main_loop

    assert pc == irq1_addr, f"IRQ1 addr mismatch: ${irq1_addr:04X} vs ${pc:04X}"

    # ----------------------------------------------------------------
    # IRQ1: double-IRQ first stage (jittery entry, just re-arms IRQ2)
    # ----------------------------------------------------------------
    irq1_start = pc

    emit(0xA9, 0xFF)                    # LDA #$FF
    emit(0x8D, 0x19, 0xD0)             # STA $D019  (ack VIC IRQ)
    emit(0xA9, 0x31)                    # LDA #$31   (next raster line)
    emit(0x8D, 0x12, 0xD0)             # STA $D012

    # IRQ2 is 23 bytes after IRQ1 start
    irq2_addr = irq1_start + 23

    emit(0xA9, irq2_addr & 0xFF)        # LDA #lo(IRQ2)
    emit(0x8D, 0x14, 0x03)              # STA $0314
    emit(0xA9, (irq2_addr >> 8) & 0xFF) # LDA #hi(IRQ2)
    emit(0x8D, 0x15, 0x03)              # STA $0315
    emit(0x4C, 0x81, 0xEA)             # JMP $EA81  (KERNAL IRQ exit)

    assert pc == irq2_addr, f"IRQ2 addr mismatch: ${irq2_addr:04X} vs ${pc:04X}"

    # ----------------------------------------------------------------
    # IRQ2: stable second stage - spin-wait for raster $33 then FLI
    # ----------------------------------------------------------------
    emit(0xA9, 0xFF)                    # LDA #$FF
    emit(0x8D, 0x19, 0xD0)             # STA $D019  (ack VIC IRQ)

    # Double spin: wait for $32, then $33
    wait32 = pc
    emit(0xAD, 0x12, 0xD0)             # LDA $D012
    emit(0xC9, 0x32)                    # CMP #$32
    emit(0xD0, (wait32 - (pc + 2)) & 0xFF)  # BNE wait32

    wait33 = pc
    emit(0xAD, 0x12, 0xD0)             # LDA $D012
    emit(0xC9, 0x33)                    # CMP #$33
    emit(0xD0, (wait33 - (pc + 2)) & 0xFF)  # BNE wait33

    emit(0xEA)                          # NOP (2 cycles) to shift write past cycle 14
    emit(0xA0, 0x01)                    # LDY #$01  (Start at line 1)

    # ----------------------------------------------------------------
    # FLI LOOP: exactly 23 cycles per iteration (fits 24-cycle window)
    #   LDA $0900,Y  [4] - D011 value
    #   STA $D011    [4] - write scroll/bad-line
    #   LDA $0A00,Y  [4] - D018 value
    #   STA $D018    [4] - write screen page pointer
    #   INY          [2]
    #   CPY #$C8     [2]
    #   BNE fli_loop [3]
    #   Total = 23 cycles ✓
    # ----------------------------------------------------------------
    fli_loop = pc
    emit(0xB9, 0x00, 0x09)             # LDA $0900,Y  [4]
    emit(0x8D, 0x11, 0xD0)             # STA $D011    [4]
    emit(0xB9, 0x00, 0x0A)             # LDA $0A00,Y  [4]
    emit(0x8D, 0x18, 0xD0)             # STA $D018    [4]
    emit(0xC8)                          # INY          [2]
    emit(0xC0, 0xC8)                    # CPY #$C8     [2]
    emit(0xD0, (fli_loop - (pc + 2)) & 0xFF)  # BNE fli_loop [3]

    # After 200 lines: restore state, re-arm IRQ1
    emit(0xA9, 0x3B)                    # LDA #$3B
    emit(0x8D, 0x11, 0xD0)             # STA $D011
    emit(0xA9, 0x08)                    # LDA #$08
    emit(0x8D, 0x18, 0xD0)             # STA $D018
    emit(0xA9, 0x30)                    # LDA #$30
    emit(0x8D, 0x12, 0xD0)             # STA $D012
    emit(0xA9, irq1_addr & 0xFF)        # LDA #lo(IRQ1)
    emit(0x8D, 0x14, 0x03)              # STA $0314
    emit(0xA9, (irq1_addr >> 8) & 0xFF) # LDA #hi(IRQ1)
    emit(0x8D, 0x15, 0x03)              # STA $0315
    emit(0x4C, 0x81, 0xEA)             # JMP $EA81

    print(f"  Code: $080D-${pc-1:04X} | IRQ1: ${irq1_addr:04X} | IRQ2: ${irq2_addr:04X} | FLI loop: ${fli_loop:04X}")

    # ----------------------------------------------------------------
    # Embed tables and data into PRG
    # ----------------------------------------------------------------
    # D011 table at $0900
    off = addr_to_offset(0x0900)
    prg[off:off+200] = d011_table

    # D018 table at $0A00
    off = addr_to_offset(0x0A00)
    prg[off:off+200] = d018_table

    # Color RAM at $1000 (1000 bytes, copied to $D800 by startup code)
    off = addr_to_offset(0x1000)
    prg[off:off+1000] = color_ram

    # Screen RAM pages at $4000-$5FFF (8 pages x 1024 bytes)
    off = addr_to_offset(0x4000)
    prg[off:off+8192] = screens

    # Bitmap at $6000-$7F3F (8000 bytes)
    off = addr_to_offset(0x6000)
    prg[off:off+8000] = bitmap_ram

    with open(out_path, "wb") as f:
        f.write(prg)

def generate_preview(bitmap_ram, screens, color_ram, bg_color, out_path):
    print(f"Generating C64 simulated preview to: {out_path}")
    preview = Image.new("RGB", (320, 200), (0, 0, 0))
    pixels = preview.load()

    # Emulate the C64 VIC-II FLI decoding on PC
    for y in range(200):
        row = y // 8
        py = y % 8
        screen_page_offset = py * 1024
        for x in range(160):
            cellIdx = row * 40 + (x // 4)
            px = x % 4

            # Read raw byte from bitmap
            byte = bitmap_ram[cellIdx * 8 + py]
            bits = (byte >> ((3 - px) * 2)) & 3

            # Fetch color palette index based on bit combination
            if bits == 0:
                col_idx = bg_color
            elif bits == 1:
                # Screen RAM high nibble
                col_idx = screens[screen_page_offset + cellIdx] >> 4
            elif bits == 2:
                # Screen RAM low nibble
                col_idx = screens[screen_page_offset + cellIdx] & 0x0F
            else:
                # Color RAM
                col_idx = color_ram[cellIdx]

            # Render double-width pixel
            rgb = c64_colors[col_idx]
            pixels[x * 2, y] = rgb
            pixels[x * 2 + 1, y] = rgb

    preview.save(out_path)

def main():
    # Make sure tools/ folder exists
    os.makedirs("tools", exist_ok=True)

    img_320 = generate_chrome_image()
    
    # Save the original high-resolution design preview
    img_320.save("tools/test_fli_original.png")
    print("Saved original design to tools/test_fli_original.png")

    # Encode to FLI components
    bitmap_ram, screens, color_ram, bg_color = encode_fli(img_320)

    # Save to runnable C64 executable
    save_fli_prg(bitmap_ram, screens, color_ram, bg_color, "tools/test_fli.prg")

    # Save C64 rendered simulation preview
    generate_preview(bitmap_ram, screens, color_ram, bg_color, "tools/test_fli_preview.png")

    print("\nEncoding Complete! Files created in tools/ directory:")
    print("  - test_fli.prg          (Load & Run this on C64 or VICE)")
    print("  - test_fli_preview.png  (Simulated C64 screen representation)")
    print("  - test_fli_original.png (High-resolution raw text design reference)")

if __name__ == "__main__":
    main()
