# v0.24 hypothesis: patch sl.dlss_nr updateEmbeddedJSON support check (0x3f30c jne->NOP)
# -> sl.dlss_nr reports supported -> interposer loads it -> SL inits dlssnr with its
# standard NGX session (dlssnr-recognized) -> NR 1004 registers without crash?
# Full game sequence: dlssnr 7-patch + sl.dlss_nr patch + interposer slInit.
import ctypes, os, struct, sys, uuid

SL = r"D:\Modding\renodx\extracted\streamline"

def wp(base, off, data):
    slot = base + off
    old = ctypes.c_uint32()
    ctypes.windll.kernel32.VirtualProtect(ctypes.c_void_p(slot), len(data), 0x40, ctypes.byref(old))
    buf = (ctypes.c_ubyte * len(data)).from_address(slot)
    for i, b in enumerate(data):
        buf[i] = b
    ctypes.windll.kernel32.VirtualProtect(ctypes.c_void_p(slot), len(data), old.value, ctypes.byref(old))

k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
k32.LoadLibraryW.restype = ctypes.c_void_p
k32.LoadLibraryW.argtypes = [ctypes.c_wchar_p]
k32.GetProcAddress.restype = ctypes.c_void_p
k32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

# ---- 1) dlssnr + 7-patch (like PrepareDlssnrForStreamline) ----
nr = k32.LoadLibraryW(SL + r"\nvngx_dlssnr.dll")
nr_base = nr
print("dlssnr @0x%x" % nr_base)
GMHEXW = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
GMHA = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)
_stubs = []
def stub_exw(f, n, out):
    out[0] = nr
    return 1
def stub_ga(n):
    return nr
se = GMHEXW(stub_exw); sg = GMHA(stub_ga)
_stubs += [se, sg]
wp(nr_base, 0xac118, struct.pack("<Q", ctypes.cast(se, ctypes.c_void_p).value))
wp(nr_base, 0xac080, struct.pack("<Q", ctypes.cast(sg, ctypes.c_void_p).value))
wp(nr_base, 0x15e97, b"\xE9")
wp(nr_base, 0x7ab60, b"\x31\xC0\xC3")
wp(nr_base, 0x8810, b"\xB8\x01\x00\x00\x00\xC3")
wp(nr_base, 0x144bd, b"\x90"*6)
print("dlssnr 7-patch applied")

# ---- 2) sl.dlss_nr + patch support check 0x3f30c jne->jmp (force success path 0x3f449) ----
slnr = k32.LoadLibraryW(SL + r"\sl.dlss_nr.dll")
print("sl.dlss_nr @0x%x" % slnr)
if not slnr:
    print("FAILED to load sl.dlss_nr"); sys.exit(1)
wp(slnr, 0x3f30c, b"\xE9\x37\x01\x00\x00\x00")
print("sl.dlss_nr support-check patched (0x3f30c jne->jmp 0x3f449)")

# ---- 3) interposer + slInit(featuresNR) ----
sli = k32.LoadLibraryW(SL + r"\sl.interposer.dll")
print("interposer @0x%x" % sli)
def gpa(mod, name):
    return k32.GetProcAddress(mod, name)
slInit = gpa(sli, b"slInit")
slIsFeatureLoaded = gpa(sli, b"slIsFeatureLoaded")
slShutdown = gpa(sli, b"slShutdown")
print("slInit=0x%x slIsFeatureLoaded=0x%x" % (slInit, slIsFeatureLoaded))

kSDKVersion = (2 << 48) | (12 << 32) | (0 << 16) | 0xFEDC
GUID = bytes.fromhex("65 09 a1 1c 8e bf 2b 43 8d a1 67 16 d8 79 fb 14")
def build_prefs(feats):
    n = len(feats)
    arr = (ctypes.c_uint64 * n)(*feats)
    buf = ctypes.create_string_buffer(0xA0)
    ctypes.memset(buf, 0, 0xA0)
    ctypes.memmove(ctypes.addressof(buf) + 0x08, GUID, 16)
    ctypes.c_uint64.from_buffer(buf, 0x18).value = 1
    ctypes.c_uint32.from_buffer(buf, 0x28).value = 2  # eVerbose
    ctypes.c_uint64.from_buffer(buf, 0x60).value = 0x20|0x80  # eUseFrameBasedResourceTagging|eUseDXGIFactoryProxy
    ctypes.c_uint64.from_buffer(buf, 0x68).value = ctypes.addressof(arr)
    ctypes.c_uint32.from_buffer(buf, 0x70).value = n
    ctypes.c_uint32.from_buffer(buf, 0x78).value = 0
    ctypes.c_uint32.from_buffer(buf, 0x80).value = 0
    ctypes.c_uint32.from_buffer(buf, 0x98).value = 0  # eD3D12
    return buf, arr

LOG_CB = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p)
log_lines = []
@LOG_CB
def log_cb(t, m):
    try: s = m.decode("utf-8","replace") if m else ""
    except: s = repr(m)
    log_lines.append(s)
    print("[SL] %s" % s)

prefs, arr = build_prefs([0, 1000, 3, 1004])
ctypes.c_uint64.from_buffer(prefs, 0x58).value = ctypes.cast(log_cb, ctypes.c_void_p).value  # logCb
SL_INIT = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint64)
r = SL_INIT(slInit)(ctypes.addressof(prefs), kSDKVersion)
print("\nslInit -> 0x%x (%d)" % (r, r))

if slIsFeatureLoaded:
    loaded = ctypes.c_bool(False)
    SL_LOADED = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_uint64, ctypes.POINTER(ctypes.c_bool))
    lr = SL_LOADED(slIsFeatureLoaded)(1004, ctypes.byref(loaded))
    print("slIsFeatureLoaded(1004) -> rc=0x%x loaded=%s" % (lr, loaded.value))
h = k32.GetModuleHandleW(ctypes.c_wchar_p("sl.dlss_nr.dll"))
print("GetModuleHandleW(sl.dlss_nr.dll) -> 0x%x (%s)" % (h or 0, "LOADED" if h else "NOT loaded"))
hnr = k32.GetModuleHandleW(ctypes.c_wchar_p("nvngx_dlssnr.dll"))
print("GetModuleHandleW(nvngx_dlssnr.dll) -> 0x%x" % (hnr or 0))
print("\n--- interesting SL log ---")
for s in log_lines:
    tl = s.lower()
    if any(k in tl for k in ["dlss_nr", "ignoring", "not supported", "error", "crashed", "fail", "invalid", "denylist", "map", "load"]):
        print("  ", s[:200])
