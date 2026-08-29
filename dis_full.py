import struct
dll = r"E:/EJ/mod/mods/SkyrimUpscalerAIOBuild/UpscalerBasePlugin/PDPerfPlugin.dll"
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
# read strings around 0x9C060-0x9C0D0 (ascii and utf-16)
off = rva_to_off(0x9C060)
chunk = data[off:off+0x100]
print("ascii strings:")
i = 0
while i < len(chunk):
    if 32 <= chunk[i] < 127:
        j = i
        while j < len(chunk) and 32 <= chunk[j] < 127:
            j += 1
        s = chunk[i:j].decode('ascii')
        if len(s) >= 3:
            print(f"  @0x9C060+{i:#x}: {s!r}")
        i = j
    else:
        i += 1
print("wide strings:")
for base in (0x9C060, 0x9C090, 0x9C0C0):
    off2 = rva_to_off(base)
    raw = data[off2:off2+0x80]
    try:
        end = raw.index(b"\x00\x00")
        s = raw[:end].decode("utf-16-le", "replace")
        if len(s) >= 2 and s.isprintable():
            print(f"  @{base:#x}: {s!r}")
    except (ValueError, UnicodeDecodeError):
        pass
