* = $0801
!to "wic64_viewer.prg", cbm
!byte $0c, $08, $0a, $00, $9e, $20, $32, $30, $36, $34, $00, $00, $00 ; 10 SYS 2064

* = $0810
jmp main

!src "tools/wic64-library/wic64.h"
!src "tools/wic64-library/wic64.asm"

; --- Memory Map ---
; $0200-$0203 : 4-byte frame header
; $0204-$0207 : 4-byte chunk header (delta)
; $0208-$020b : 4-byte page header (delta)

; Variables
double_buf_flag = $03
bitmap_dest_hi  = $0a
screen_dest_hi  = $0b
pages_count     = $08
delta_bitmap_cnt = $09
delta_screen_cnt = $0c
delta_color_cnt  = $0d

read_len_lo = $fc
read_len_hi = $fd
read_dst_lo = $fe
read_dst_hi = $ff

main:
    sei
    cld
    lda #$35
    sta $01 ; I/O visible

    ; Set CIA2 data direction: bits 0-1 as output for VIC bank select
    lda $dd02
    ora #$03
    sta $dd02

    ; Set VIC to bank 0 ($0000-$3FFF)
    lda $dd00
    ora #$03
    sta $dd00

    lda #$00
    sta double_buf_flag

    jsr wic64_initialize

    ; Connect to TCP server (provide a dummy buffer in case it returns a response)
    +wic64_execute tcp_open_request, dummy_buffer

main_loop:
    ; Read 4 bytes frame header
    lda #4
    sta read_len_lo
    lda #0
    sta read_len_hi
    lda #$00
    sta read_dst_lo
    lda #$02
    sta read_dst_hi
    jsr reliable_tcp_read

    ; Double buffer flag check
    lda double_buf_flag
    bne write_bank0

write_bank1:
    lda #$60
    sta bitmap_dest_hi
    lda #$44
    sta screen_dest_hi
    jmp do_reads

write_bank0:
    lda #$20
    sta bitmap_dest_hi
    lda #$04
    sta screen_dest_hi

do_reads:
    ; Check if delta frame (flags & 0x80)
    lda $0202
    and #$80
    beq full_reads

delta_reads:
    lda $0203
    sta delta_bitmap_cnt

    ; Read the next 4 bytes of extended delta header (Screen count, Color count, Pad, Pad)
    lda #4
    sta read_len_lo
    lda #0
    sta read_len_hi
    lda #$04
    sta read_dst_lo
    lda #$02
    sta read_dst_hi
    jsr reliable_tcp_read
    
    lda $0204
    sta delta_screen_cnt
    lda $0205
    sta delta_color_cnt

    lda delta_bitmap_cnt
    beq skip_bitmap_deltas
    sta pages_count
    lda bitmap_dest_hi
    jsr apply_delta_pages
skip_bitmap_deltas:

    ; Screen deltas
    lda delta_screen_cnt
    beq skip_screen_deltas
    sta pages_count
    lda screen_dest_hi
    jsr apply_delta_pages
skip_screen_deltas:

    ; Color deltas
    lda delta_color_cnt
    beq skip_color_deltas
    sta pages_count
    lda #$d8
    jsr apply_delta_pages
skip_color_deltas:

    jmp apply_settings

full_reads:
    ; Read 8000 bytes bitmap
    lda #<8000
    sta read_len_lo
    lda #>8000
    sta read_len_hi
    lda #$00
    sta read_dst_lo
    lda bitmap_dest_hi
    sta read_dst_hi
    jsr reliable_tcp_read

    ; Check if we need to read screen
    lda $0202
    and #$01
    beq full_skip_screen
    
    lda #<1000
    sta read_len_lo
    lda #>1000
    sta read_len_hi
    lda #$00
    sta read_dst_lo
    lda screen_dest_hi
    sta read_dst_hi
    jsr reliable_tcp_read
full_skip_screen:

    ; Check if we need to read color
    lda $0202
    and #$02
    beq full_skip_color

    lda #<1000
    sta read_len_lo
    lda #>1000
    sta read_len_hi
    lda #$00
    sta read_dst_lo
    lda #$d8
    sta read_dst_hi
    jsr reliable_tcp_read
full_skip_color:

apply_settings:
    ; Set background color
    lda $0201
    sta $d021
    sta $d020

    ; Check mode
    lda $0200
    cmp #$00
    beq apply_multi

apply_hires:
    lda #$3b
    sta $d011
    lda #$08
    sta $d016
    lda #$18
    sta $d018
    jmp flip_buffer

apply_multi:
    lda #$3b
    sta $d011
    lda #$18
    sta $d016
    lda #$18
    sta $d018

flip_buffer:
    ; Toggle VIC bank select
    lda $dd00
    eor #$01
    sta $dd00

    ; Toggle double buffer flag
    lda double_buf_flag
    eor #$01
    sta double_buf_flag

    jmp main_loop

; subroutine: apply_delta_pages
; input: A = destination base high page, pages_count = number of pages
apply_delta_pages:
    sta apply_base_page_hi

delta_loop:
    ; Read 4-byte page header
    lda #4
    sta read_len_lo
    lda #0
    sta read_len_hi
    lda #$08
    sta read_dst_lo
    lda #$02
    sta read_dst_hi
    jsr reliable_tcp_read

    ; Calculate destination
    lda apply_base_page_hi
    clc
    adc $0208 ; page offset
    sta read_dst_hi
    lda #0
    sta read_dst_lo

    ; Read 256 bytes page data
    lda #0
    sta read_len_lo
    lda #1
    sta read_len_hi
    jsr reliable_tcp_read

    dec pages_count
    bne delta_loop
    rts

apply_base_page_hi: !byte 0


; --- Reliable TCP Read Subroutine ---
reliable_tcp_read:
    lda read_dst_lo
    sta wic64_response
    lda read_dst_hi
    sta wic64_response+1

reliable_loop:
    ; Update tcp_read_dyn_request with remaining length
    lda read_len_lo
    sta tcp_read_dyn_len
    lda read_len_hi
    sta tcp_read_dyn_len+1

    +wic64_set_request tcp_read_dyn_request
    jsr wic64_execute

    ; Wait for data
    lda wic64_response_size
    ora wic64_response_size+1
    beq reliable_loop

    ; Subtract wic64_response_size from read_len
    sec
    lda read_len_lo
    sbc wic64_response_size
    sta read_len_lo
    lda read_len_hi
    sbc wic64_response_size+1
    sta read_len_hi

    ; Advance destination pointer
    clc
    lda wic64_response
    adc wic64_response_size
    sta wic64_response
    lda wic64_response+1
    adc wic64_response_size+1
    sta wic64_response+1

    ; Check if done
    lda read_len_lo
    ora read_len_hi
    bne reliable_loop

    ; Send ACK to server to indicate this chunk has been fully received
    +wic64_execute tcp_ack_request, dummy_buffer

    rts


; --- WiC64 Requests ---

tcp_open_request:
    !byte "R", WIC64_TCP_OPEN
    !byte <(tcp_ip_end - tcp_ip), >(tcp_ip_end - tcp_ip)
tcp_ip:
    !text "192.168.000.000:00000" ; Patched by python server
tcp_ip_end:

tcp_ack_request:
    !byte "R", WIC64_TCP_WRITE, 1, 0
tcp_ack_val:
    !byte $06

tcp_read_dyn_request:
    !byte "R", WIC64_TCP_READ, 2, 0
tcp_read_dyn_len:
    !byte 0, 0

dummy_buffer:
    !fill 16, 0
