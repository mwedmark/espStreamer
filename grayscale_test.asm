;==============================================================
; C64 PAL Blending Grayscale Test Pattern (16 Shades)
; Target: ca65 / cc65 toolchain (Standard c64.cfg compatible)
; Mode: VIC-II Multicolor Bitmap Mode for scanline PAL blending
;==============================================================

.export _main
.export START

.segment "CODE"

_main:
START:
    SEI                   ; Disable interrupts
    CLD                   ; Clear decimal mode

    ; --- Step 1: Mute SID Audio to prevent start-up hum ---
    LDX #$18
    LDA #$00
SID_MUTE_LOOP:
    STA $D400,x
    DEX
    BPL SID_MUTE_LOOP

    ; --- Step 2: Disable CIA Interrupts ---
    LDA #$7F
    STA $DC0D
    STA $DD0D
    LDA $DC0D             ; Clear any pending interrupts
    LDA $DD0D

    ; --- Step 3: Setup VIC-II Border & Background Colors ---
    LDA #$00
    STA $D020             ; Border color = Black
    STA $D021             ; Background color = Black

    ; --- Step 4: Configure VIC-II registers for Multicolor Bitmap ---
    LDA #$3B              ; Bit 5 = 1 (Bitmap Mode on), Bit 3 = 1 (25 rows)
    STA $D011
    LDA #$D8              ; Bit 3 = 1 (Multicolor on), Bit 5 = 0
    STA $D016
    LDA #$18              ; Screen RAM at $0400, Bitmap RAM at $2000
    STA $D018

    ; --- Step 5: Initialize 8KB Bitmap memory ($2000-$3F3F) ---
    ; Even scanlines (0, 2, 4, 6 of each block) filled with $55 (%01010101) -> Color %01 (Screen RAM high nibble)
    ; Odd scanlines (1, 3, 5, 7 of each block) filled with $AA (%10101010) -> Color %10 (Screen RAM low nibble)
    LDA #$00
    STA $FB
    LDA #$20
    STA $FC

    LDX #31               ; 31 pages of 256 bytes = 7936 bytes
    LDY #$00
BITMAP_PAGE_LOOP:
    LDA #$55
    STA ($FB),y
    INY
    LDA #$AA
    STA ($FB),y
    INY
    BNE BITMAP_PAGE_LOOP
    INC $FC
    DEX
    BNE BITMAP_PAGE_LOOP

    ; Fill the remaining 64 bytes of the last page to hit exactly 8000 bytes
    LDY #$00
BITMAP_REMAIN_LOOP:
    LDA #$55
    STA ($FB),y
    INY
    LDA #$AA
    STA ($FB),y
    INY
    CPY #64               ; 64 bytes
    BNE BITMAP_REMAIN_LOOP

    ; --- Step 6: Clear Color RAM ($D800-$DBE7) ---
    ; In Multicolor Bitmap Mode, pixel bits %01 and %10 only read from Screen RAM,
    ; but clearing Color RAM ensures clean state without stray artifacts.
    LDX #$00
CLEAR_COLOR_RAM:
    LDA #$00
    STA $D800,x
    STA $D900,x
    STA $DA00,x
    STA $DB00,x
    INX
    BNE CLEAR_COLOR_RAM

    ; --- Step 7: Initialize Screen RAM Pointer ($0400) ---
    LDA #$00
    STA $FB
    LDA #$04
    STA $FC

    ; --- Step 8: Draw 25 Rows in Screen RAM ---
    LDY #$00              ; Y = Row Counter (0 to 24)
LINE_LOOP:
    CPY #$19              ; Check if Y >= 25 lines
    BCS END_PATTERN       ; If done, exit loop

    ; Save Row Counter in Zero Page
    STY $FD

    ; Draw the row: Column index goes into Y register
    LDY #$00              ; Y = Column Counter (0 to 39)
COLUMN_LOOP:
    CPY #$28              ; Check if Y >= 40 columns
    BCS END_COLUMN_LOOP

    CPY #$04              ; Columns 0-3 are Black padding
    BCC WRITE_BLACK
    CPY #$24              ; Columns 36-39 are Black padding
    BCS WRITE_BLACK

    ; We are in the 16 bands (columns 4 to 35)
    TYA
    SEC
    SBC #$04
    LSR                   ; Divide column offset by 2 to get band index (0-15)
    TAX                   ; X = band index (0 to 15)

    ; Load Even color (displays on scanlines 0, 2, 4, 6)
    LDA EVEN_PALETTE,x
    ASL
    ASL
    ASL
    ASL                   ; Shift color code into high nibble
    STA $FE               ; Store in Zero Page temp
    
    ; Load Odd color (displays on scanlines 1, 3, 5, 7)
    LDA ODD_PALETTE,x
    AND #$0F              ; Ensure low nibble only
    ORA $FE               ; Combine: (EVEN << 4) | ODD
    JMP DO_WRITE

WRITE_BLACK:
    LDA #$00              ; Black padding (both Even and Odd lines are color $00)

DO_WRITE:
    STA ($FB),y           ; Write dual-color byte to Screen RAM ($0400 + Y*40 + column)

    INY                   ; Increment Column Counter
    JMP COLUMN_LOOP

END_COLUMN_LOOP:
    ; Restore Row Counter
    LDY $FD

    ; Advance Screen RAM Pointer ($FB/$FC) by 40 bytes
    CLC
    LDA $FB
    ADC #40
    STA $FB
    LDA $FC
    ADC #$00
    STA $FC

    INY                   ; Increment Row Counter
    JMP LINE_LOOP

END_PATTERN:
    CLI                   ; Re-enable interrupts
    RTS                   ; Return to BASIC (user can press RUN/STOP + RESTORE to reset text screen)

; ==============================================================
; PALETTE DATA SEGMENT
; ==============================================================
.segment "RODATA"

; 16-shade palette for EVEN lines (Pepto Y sorted, complementary PAL phases)
EVEN_PALETTE:
    .byte $00, $00, $0B, $09, $0B, $04, $0C, $02, $06, $0D, $0C, $0A, $0F, $0E, $0F, $01

; 16-shade palette for ODD lines (Pepto Y sorted, complementary PAL phases)
ODD_PALETTE:
    .byte $00, $0B, $0B, $08, $0C, $05, $0C, $03, $07, $04, $0F, $03, $0F, $07, $01, $01

.segment "STARTUP"
.segment "INIT"
.segment "ONCE"
