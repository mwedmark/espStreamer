# C64 FLI (Flexible Line Interpretation) Specification for ESPStreamer

This document serves as the technical specification for implementing FLI (Flexible Line Interpretation) graphics mode support in the ESPStreamer application. It covers C64 hardware background, timing constraints, memory layout, stream format, and the required modifications for both C64-side assembly and PC-side Python backends.

---

## 1. C64 FLI Hardware Background

Standard C64 Multicolor Bitmap mode restricts color selection to 4 colors per 8x8 character cell:
1. **Background Color** (`$D021`, global for the whole screen).
2. **Color 1** (bits 7-4 of Screen RAM).
3. **Color 2** (bits 3-0 of Screen RAM).
4. **Color 3** (Color RAM at `$D800`–`$DBFF`).

### The FLI Mechanism
FLI overcomes this by changing the **Screen RAM pointer** (register `$D018`) on **every single scanline** during the active screen display.
* By manipulating the vertical smooth scroll register (`$D011`), the CPU forces the VIC-II chip into a **"Bad Line" state on every scanline** instead of once every 8 scanlines.
* During these forced Bad Lines, the VIC-II executes DMA fetches to grab fresh color data from Screen RAM.
* By cycling the `$D018` pointer across 8 different Screen RAM pages on consecutive lines, each **8x1 pixel block** gets its own independent selection of Color 1 (high nibble) and Color 2 (low nibble).
* The global background color (`$D021`) and the Color RAM (`$D800` cell color) remain static.

### The Left-Border FLI Bug
Because the VIC-II chip is pushed to execute DMA cycles on every scanline, the CPU cannot feed the VIC-II with registers fast enough to avoid timing conflicts at the start of the raster sweep. This creates a hardware limitation known as the **"FLI Bug"**: the first **3 character columns (24 pixels)** on the left edge of the screen are corrupted or blanked out.
* The encoder/frontend must offset images or fill the first 3 columns (`x = 0` to `23`) with black/background color.

---

## 2. Timing Constraints & Cycle-Exact Loop

A single PAL scanline is exactly **63 CPU cycles** long.
During an FLI forced Bad Line, the VIC-II steals **40 cycles** from the CPU for DMA, leaving only **23 cycles** of active CPU time.

### The Critical Timing Window
The CPU is suspended between cycles 15 and 54 of the scanline. When the CPU resumes, the register writes to `$D018` (Screen RAM page) and `$D011` (vertical scroll to trigger the Bad Line) for the *next* scanline must complete **before cycle 15 of that next line**.
* This leaves a strict **24-cycle window** `(63 - 54 + 15)` to update the registers.
* The loop must be cycle-exact and synchronized with the raster beam (usually using a **double-interrupt** stable raster routine to remove interrupt jitter).

### Cycle-Exact 6502 FLI Loop Example (63 cycles)
```assembly
; Y register tracks the line index (0 to 199)
fli_loop:
    lda $0A00,y     ; [4 cycles] Get $D018 value (switches Screen RAM bank)
    sta $D018       ; [4 cycles] Write to VIC-II memory pointer (Must hit before cycle 15)
    lda $0900,y     ; [4 cycles] Get $D011 value (switches scroll offset to force badline)
    sta $D011       ; [4 cycles] Write to VIC-II control register (Must hit before cycle 15)
    
    ; --- CPU is suspended here (cycles 15-54) for VIC-II DMA ---
    
    iny             ; [2 cycles] Increment line counter
    cpy #$c8        ; [2 cycles] Check if we reached 200 lines ($c8)
    bne fli_loop    ; [3 cycles] Loop back
```
**Total cycles consumed:** 4 + 4 + 4 + 4 + 2 + 2 + 3 = **23 cycles** (perfectly fitting within the 24-cycle window!).

---

## 3. C64 Memory Layout (VIC Bank 1)

Because Zero Page (`$0000`–`$00FF`) and Stack (`$0100`–`$01FF`) reside in VIC Bank 0, FLI is typically run in **VIC Bank 1 (`$4000`–`$7FFF`)** to avoid memory conflicts.

The 16KB bank is mapped as follows:

| Address Range | Size | Component | Description |
| :--- | :--- | :--- | :--- |
| `$4000`–`$43E7` | 1,000 bytes | Screen RAM Page 0 | Attribute data for line offset 0 |
| `$4400`–`$47E7` | 1,000 bytes | Screen RAM Page 1 | Attribute data for line offset 1 |
| `$4800`–`$4BE7` | 1,000 bytes | Screen RAM Page 2 | Attribute data for line offset 2 |
| `$4C00`–`$4FE7` | 1,000 bytes | Screen RAM Page 3 | Attribute data for line offset 3 |
| `$5000`–`$53E7` | 1,000 bytes | Screen RAM Page 4 | Attribute data for line offset 4 |
| `$5400`–`$57E7` | 1,000 bytes | Screen RAM Page 5 | Attribute data for line offset 5 |
| `$5800`–`$5BE7` | 1,000 bytes | Screen RAM Page 6 | Attribute data for line offset 6 |
| `$5C00`–`$5FE7` | 1,000 bytes | Screen RAM Page 7 | Attribute data for line offset 7 |
| `$6000`–`$7F3F` | 8,000 bytes | Bitmap RAM | Raw pixel data |

* **Color RAM** is mapped statically to the C64 hardware address `$D800`–`$DBE7`.
* **Table of `$D011` values:** Stored in RAM (e.g. `$0900`–`$09C7`).
* **Table of `$D018` values:** Stored in RAM (e.g. `$0A00`–`$0AC7`).

---

## 4. Streaming Protocol changes

To stream FLI frames live, the binary data payload needs to expand beyond the standard multicolor format size.

### Frame Layout (17,001 bytes)
The stream payload transmitted over WebSockets/Serial must contain:
1. **Bitmap Data** (`0` to `7999`): 8,000 bytes.
2. **Screen RAM Pages** (`8000` to `15999`): 8,000 bytes (8 blocks of 1,000 bytes).
3. **Color RAM Data** (`16000` to `16999`): 1,000 bytes.
4. **Background Color** (`17000`): 1 byte.

### Server-Side Updates (`ws_server.py`)
Update binary frame parsing to handle the larger size when `IS_FLI` is active:
```python
# Extract components for FLI frame (17,001 bytes)
mode = message[0]
bg_color = message[1]
bitmap = message[2:8002]       # 8,000 bytes
screen = message[8002:16002]     # 8,000 bytes (8 screens)
color = message[16002:17002]     # 1,000 bytes
```

### Backend Updates (`backend_kungfu.py` / `backend_vice.py`)
1. **Buffer Allocations:** Expand stream arrays to support the 8,000-byte Screen RAM payload.
2. **Transfer logic:** Update the chunked protocol routines to stream 17,001 bytes per frame instead of 10,002 bytes.
