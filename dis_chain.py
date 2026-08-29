import capstone, struct, re

dll = r"E:/EJ/mod/mods/SkyrimUpscalerAIOBuild/UpscalerBasePlugin/PDPerfPlugin.dll"
base = 0x7ffb8f410000
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

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

def dis(rva, size, label, headcut=0):
    print(f"\n===== {label} @{rva:#x} =====")
    off = rva_to_off(rva) + headcut
    rva += headcut
    for ins in md.disasm(data[off: off+size], base + rva):
        m = re.search(r"rip \+ (0x[0-9a-f]+)", ins.op_str)
        extra = ""
        if m:
            tgt = ins.address - base + ins.size + int(m.group(1), 16)
            extra = f"  ; -> {tgt:#x}"
        print(f"{ins.address - base:#08x}: {ins.mnemonic} {ins.op_str}{extra}")
        if ins.address - base > rva + size - 0x10:
            break

# 0x1A880 first 0x40 (prologue, was cut before)
dis(0x1A880, 0x40, "0x1A880 prologue")
