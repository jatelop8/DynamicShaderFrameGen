import capstone, struct

dll = r"E:/EJ/mod/mods/SkyrimUpscalerAIOBuild/UpscalerBasePlugin/PDPerfPlugin.dll"
base = 0x7ffb07700000
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
print("===== 0x1AFF0 create (0x1b153-0x1b350) =====")
code = data[rva_to_off(0x1b153): rva_to_off(0x1b350)]
for ins in md.disasm(code, base + 0x1b153):
    print(f"{ins.address - base:#08x}: {ins.mnemonic} {ins.op_str}")
