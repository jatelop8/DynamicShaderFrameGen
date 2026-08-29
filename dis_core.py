import capstone, struct

dll = r"C:/Windows/System32/D3D12Core.dll"
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

# function head 0x7BEE0 to crash 0x7BF2E
print("=== fn 0x7BEE0 -> 0x7BF2E ===")
off = rva_to_off(0x7BEE0)
for ins in md.disasm(data[off: rva_to_off(0x7BF2E)+16], 0x7ffb8f550000 + 0x7BEE0):
    mark = "  <<<< CRASH" if ins.address == 0x7ffb8f55bf2e else ""
    print(f"{ins.address - 0x7ffb8f550000:#08x}: {ins.mnemonic} {ins.op_str}{mark}")

# exports near 0x7BEE0
print("\n=== exports in D3D12Core ===")
exp_rva, _ = struct.unpack_from("<II", data, pe_off + 24 + 0x70)
eo = rva_to_off(exp_rva)
nfuncs, nnames = struct.unpack_from("<II", data, eo + 20)
funcs_rva, names_rva, ords_rva = struct.unpack_from("<III", data, eo + 28)
base_ord = struct.unpack_from("<I", data, eo + 16)[0]
print(f"nfuncs={nfuncs} nnames={nnames} base={base_ord}")
hits = []
for i in range(nnames):
    no = rva_to_off(names_rva + i*4)
    name_rva = struct.unpack_from("<I", data, no)[0]
    no2 = rva_to_off(name_rva)
    end = data.index(b"\x00", no2)
    nm = data[no2:end].decode("ascii", "replace")
    ord_ofs = rva_to_off(ords_rva + i*2)
    ordv = struct.unpack_from("<H", data, ord_ofs)[0]
    fn_rva = struct.unpack_from("<I", data, rva_to_off(funcs_rva + (ordv-base_ord)*4))[0]
    if 0x7B000 <= fn_rva <= 0x7C800:
        hits.append((fn_rva, nm))
for fn_rva, nm in sorted(hits):
    print(f"  RVA {fn_rva:#x} {nm}")
