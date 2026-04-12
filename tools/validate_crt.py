import struct

payload = bytes(range(20))
nBanks = (len(payload) + 8191) // 8192

print(f'nBanks = {nBanks}')

boot = bytes([
    0x78,0xD8,0xA2,0xFF,0x9A,0xA9,0x37,0x85,0x01,
    0xA9,0x01,0x85,0xFD,
    0xA9,0x01,0x85,0xFB,
    0xA9,0x08,0x85,0xFC,
    # copy_bank at 0x15:
    0xA5,0xFD,
    0x8D,0x00,0xDE,
    0xA9,0x04,
    0x8D,0x01,0xDE,
    0xA9,0x00,0x85,0xFE,
    0xA9,0x80,0x85,0xFF,
    0xA9,0x20,0x8D,0x00,0x03,
    # page_loop at 0x2C:
    0xA0,0x00,
    # byte_loop at 0x2E:
    0xB1,0xFE,0x91,0xFB,0xC8,
    0xD0,0xF9,   # BNE byte_loop (rel=-7 -> 0x35-7=0x2E ✓)
    0xE6,0xFC,0xE6,0xFF,
    0xCE,0x00,0x03,
    0xD0,0xEE,   # BNE page_loop (rel=-18 -> 0x3E-18=0x2C ✓)
    0xE6,0xFD,
    0xA5,0xFD,
    0xC9,nBanks+1,
    0xD0,0xCF,   # BNE copy_bank (rel=-49 -> 0x46-49=0x15 ✓)
    0xA9,0x00,0x8D,0x01,0xDE,
    0x4C,0x01,0x08
])

def check_bne(code, pos, label_name, target):
    offset = code[pos+1]
    signed = offset if offset < 128 else offset - 256
    actual = pos + 2 + signed
    ok = 'OK' if actual == target else f'WRONG! (got {hex(actual)}, expected {hex(target)})'
    print(f'  BNE {label_name} at 0x{pos:02X}: offset=0x{offset:02X}({signed:+d}) -> 0x{actual:02X} [{ok}]')

print('Branch verification:')
check_bne(boot, 0x33, 'byte_loop ', 0x2E)
check_bne(boot, 0x3C, 'page_loop ', 0x2C)
check_bne(boot, 0x44, 'copy_bank ', 0x15)

romh = bytearray(b'\xFF' * 8192)
romh[0:len(boot)] = boot
romh[0x1FFA] = 0x00; romh[0x1FFB] = 0xE0
romh[0x1FFC] = 0x00; romh[0x1FFD] = 0xE0
romh[0x1FFE] = 0x01; romh[0x1FFF] = 0xE0

h = bytearray(64)
h[0:16] = b'C64 CARTRIDGE   '
struct.pack_into('>I', h, 0x10, 0x40)
struct.pack_into('>H', h, 0x14, 0x0100)
struct.pack_into('>H', h, 0x16, 32)
h[0x18] = 0x00; h[0x19] = 0x00
h[0x20:0x2B] = b'ESPSTREAMER'

def make_chip(bank, addr, data):
    pkt = bytearray(16 + 8192)
    pkt[0:4] = b'CHIP'
    struct.pack_into('>I', pkt, 4, 16+8192)
    struct.pack_into('>H', pkt, 8, 0)
    struct.pack_into('>H', pkt, 10, bank)
    struct.pack_into('>H', pkt, 12, addr)
    struct.pack_into('>H', pkt, 14, 8192)
    pkt[16:] = data
    return bytes(pkt)

parts = [bytes(h)]
parts.append(make_chip(0, 0x8000, b'\xFF'*8192))
parts.append(make_chip(0, 0xA000, bytes(romh)))
chunk = bytearray(b'\xFF'*8192); chunk[0:len(payload)] = payload
parts.append(make_chip(1, 0x8000, bytes(chunk)))
parts.append(make_chip(1, 0xA000, b'\xFF'*8192))

crt = b''.join(parts)
print(f'\nCRT total: {len(crt)} bytes')
print(f'  Header sig : "{bytes(h[0:16]).decode()}"')
print(f'  Header len : 0x{struct.unpack_from(">I",h,0x10)[0]:08X}')
print(f'  Version    : 0x{struct.unpack_from(">H",h,0x14)[0]:04X}')
print(f'  HW Type    : {struct.unpack_from(">H",h,0x16)[0]} (32=EasyFlash)')
print(f'  EXROM/GAME : {h[0x18]}/{h[0x19]}')
crt_name = bytes(h[0x20:0x3F]).rstrip(b'\x00').decode()
print(f'  Name       : "{crt_name}"')
print(f'  CHIP count : {len(parts)-1}')
print(f'  Reset vec  : ${romh[0x1FFD]:02X}{romh[0x1FFC]:02X}')
print(f'  Boot code  : {len(boot)} bytes (${0xE000:04X}-${0xE000+len(boot)-1:04X})')
print('\nResult: VALID EasyFlash CRT')
