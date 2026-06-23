import os

def disassemble(prg_path):
    if not os.path.exists(prg_path):
        print(f"Error: {prg_path} does not exist")
        return

    with open(prg_path, "rb") as f:
        data = f.read()

    # The first two bytes are the load address
    load_addr = data[0] + (data[1] << 8)
    print(f"Load Address: ${load_addr:04X}")

    code = data[2:]
    print(f"Code Length: {len(code)} bytes")

    # 6502 Opcode table for simple disassembly
    opcodes = {
        0x78: ("SEI", 1),
        0xD8: ("CLD", 1),
        0xA9: ("LDA #", 2),
        0x85: ("STA <", 2),
        0x8D: ("STA", 3),
        0xA2: ("LDX #", 2),
        0x8A: ("TXA", 1),
        0x29: ("AND #", 2),
        0x09: ("ORA #", 2),
        0x9D: ("STA ,X", 3),
        0x0A: ("ASL A", 1),
        0xE8: ("INX", 1),
        0xE0: ("CPX #", 2),
        0xD0: ("BNE", 2),
        0xBD: ("LDA ,X", 3),
        0xAD: ("LDA", 3),
        0x2C: ("BIT", 3),
        0x0E: ("ASL", 3),
        0x46: ("LSR", 3),
        0x58: ("CLI", 1),
        0x4C: ("JMP", 3),
        0x48: ("PHA", 1),
        0x98: ("TYA", 1),
        0xEE: ("INC", 3),
        0xBA: ("TSX", 1),
        0xEA: ("NOP", 1),
        0x68: ("PLA", 1),
        0xA8: ("TAY", 1),
        0xAA: ("TAX", 1),
        0x40: ("RTI", 1),
        0x9A: ("TXS", 1),
        0xA0: ("LDY #", 2),
        0x88: ("DEY", 1),
        0xCD: ("CMP", 3),
        0xF0: ("BEQ", 2),
        0xCA: ("DEX", 1),
        0xB9: ("LDA ,Y", 3),
        0xC8: ("INY", 1),
        0xC0: ("CPY #", 2),
    }

    pc = load_addr
    idx = 0
    # Disassemble only the assembly viewer portion (first 256 bytes)
    while idx < 250 and idx < len(code):
        opcode = code[idx]
        addr = pc + idx
        if opcode in opcodes:
            name, size = opcodes[opcode]
            if size == 1:
                print(f"${addr:04X}: {opcode:02X}        {name}")
            elif size == 2:
                val = code[idx+1]
                if name == "BNE" or name == "BEQ":
                    # relative branch target
                    target = addr + 2 + (val - 256 if val >= 128 else val)
                    print(f"${addr:04X}: {opcode:02X} {val:02X}     {name} ${target:04X}")
                else:
                    print(f"${addr:04X}: {opcode:02X} {val:02X}     {name}${val:02X}")
            elif size == 3:
                val_lo = code[idx+1]
                val_hi = code[idx+2]
                val = val_lo + (val_hi << 8)
                if name.endswith(",X"):
                    name_base = name.replace(" ,X", "")
                    print(f"${addr:04X}: {opcode:02X} {val_lo:02X} {val_hi:02X}  {name_base} ${val:04X},X")
                else:
                    print(f"${addr:04X}: {opcode:02X} {val_lo:02X} {val_hi:02X}  {name} ${val:04X}")
            idx += size
        else:
            print(f"${addr:04X}: {opcode:02X}        ??? (ILLEGAL)")
            idx += 1

if __name__ == "__main__":
    disassemble("tools/test_fli_generated.prg")
