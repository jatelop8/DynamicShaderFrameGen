import capstone, struct

dll = r"C:/Windows/System32/DriverStore/FileRepository/nv_dispi.inf_amd64_a3944b54ff18b284/nvngx.dll"
data = open(dll, "rb").read()
pe_off = struct.unpack_from("<I", data, 0x3C)[0]
nsec = struct.unpack_from("<H", data, pe_off + 6)[0]
opt_size = struct.unpack_from("<H", data, pe_off + 20)[0]
sec_off = pe_off + 24 + opt_size
sections = []
for i in range(nsec):
    e = sec_off + i * 40
    vsize, va, rsize, roff = struct.unpack_from("<IIII", data, e + 8)
    sections.append((va, vsize, roff, rsize))
def rva_to_off(rva):
    for va, vsize, roff, rsize in sections:
        if va <= rva < va + max(vsize, rsize):
            return rva - va + roff
    return None

crash = 0x7ffb82fdbf2e
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
# try RVA candidates: 0xBF2E + n*0x10000 within .text
for n in range(0, 0x60):
    rva = 0xBF2E + n*0x10000
    if not (0x1000 <= rva < 0x58E00):
        continue
    off = rva_to_off(rva)
    if off is None:
        continue
    # disassemble a few instructions ending at crash
    code = data[off-0x30: off+0x20]
    for ins in md.disasm(code, crash - 0x30):
        if ins.address == crash:
            print(f"base {crash - rva:#x} RVA {rva:#x}: {ins.mnemonic} {ins.op_str}")
            break
