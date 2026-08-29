# v0.22 hypothesis test: does loading nvngx_dlss.dll BEFORE dlssnr Init_Ext cause the crash?
# Mode A: load dlss.dll first -> dlssnr Init_Ext (expect crash/refused)
# Mode B: no dlss.dll -> dlssnr Init_Ext (expect ok like harness)
import ctypes, ctypes.wintypes as wt, os, sys, struct, uuid

SL = r"D:\Modding\renodx\extracted\streamline"
DRIVER_NVNGX = r"C:\Windows\System32\DriverStore\FileRepository\nv_dispi.inf_amd64_a3944b54ff18b284\nvngx.dll"
kAppId = 0x1000000
kSuccess = 0x1

def patch_dlssnr(m):
    base = ctypes.cast(m, ctypes.c_void_p).value
    def wp(off, data):
        slot = base + off
        old = ctypes.c_uint32()
        ctypes.windll.kernel32.VirtualProtect(ctypes.c_void_p(slot), len(data), 0x40, ctypes.byref(old))
        buf = (ctypes.c_ubyte * len(data)).from_address(slot)
        for i, b in enumerate(data):
            buf[i] = b
        ctypes.windll.kernel32.VirtualProtect(ctypes.c_void_p(slot), len(data), old.value, ctypes.byref(old))
    # strstr bypass 0x15e97 jne->jmp
    wp(0x15e97, bytes([0xE9]))
    # state machine 0x7ab60 xor eax,eax;ret
    wp(0x7ab60, bytes([0x31, 0xC0, 0xC3]))
    # component query 0x8810 mov eax,1;ret
    wp(0x8810, bytes([0xB8, 0x01, 0x00, 0x00, 0x00, 0xC3]))
    # first gate 0x144bd 6xNOP
    wp(0x144bd, bytes([0x90]*6))
    # v0.22: IAT stubs (full 7-patch like game PrepareDlssnrForStreamline)
    k32 = ctypes.WinDLL("kernel32.dll")
    GMHEXW = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    def stub_exw(flags, name, out):
        out[0] = m
        return 1
    GMHA = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)
    def stub_ga(name):
        return core_handle
    global _stub_exw, _stub_ga, core_handle
    _stub_exw = GMHEXW(stub_exw)
    _stub_ga = GMHA(stub_ga)
    wp(0xac118, struct.pack("<Q", ctypes.cast(_stub_exw, ctypes.c_void_p).value))
    wp(0xac080, struct.pack("<Q", ctypes.cast(_stub_ga, ctypes.c_void_p).value))
    print("patched dlssnr @0x%x (incl IAT stubs)" % base)

LOG_CB = ctypes.CFUNCTYPE(None, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64)
logfns = []
def hook_log(off):
    # write mov rax,imm64; jmp rax at dlssnr+off
    def mk():
        cb = LOG_CB(lambda a,b,c,d: None)
        logfns.append(cb)
        return ctypes.cast(cb, ctypes.c_void_p).value
    return mk

# NGXFeatureCommonInfo
class FCI(ctypes.Structure):
    _fields_ = [("instanceId", ctypes.c_uint32), ("creationNodeMask", ctypes.c_uint32),
                ("visibilityNodeMask", ctypes.c_uint32), ("reserved", ctypes.c_uint32),
                ("userData", ctypes.c_void_p)]

def run(mode):
    print("\n===== Mode %s (%s nvngx_dlss.dll) =====" % (mode, "WITH" if mode=="A" else "WITHOUT"))
    # independent device (like game v0.21)
    d3d12 = ctypes.WinDLL("d3d12.dll")
    dev = ctypes.c_void_p()
    iid = uuid.UUID("189819f1-1db6-4b57-be54-1821339b85f7").bytes_le
    ibuf = ctypes.create_string_buffer(iid, 16)
    hr = d3d12.D3D12CreateDevice(None, 0xc000, ctypes.cast(ibuf, ctypes.c_void_p), ctypes.byref(dev))
    print("D3D12CreateDevice -> hr=0x%x dev=0x%x" % (hr & 0xffffffff, dev.value or 0))
    if not dev.value: return

    # driver nvngx core
    k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    k32.LoadLibraryW.restype = ctypes.c_void_p
    k32.LoadLibraryW.argtypes = [ctypes.c_wchar_p]
    k32.GetProcAddress.restype = ctypes.c_void_p
    k32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    core = k32.LoadLibraryW(ctypes.c_wchar_p(DRIVER_NVNGX))
    print("driver nvngx.dll -> 0x%x err=%d" % (core or 0, ctypes.get_last_error() or 0))
    if not core: return
    initStd = ctypes.cast(k32.GetProcAddress(core, b"NVSDK_NGX_D3D12_Init"), ctypes.c_void_p).value
    allocP = ctypes.cast(k32.GetProcAddress(core, b"NVSDK_NGX_D3D12_AllocateParameters"), ctypes.c_void_p).value
    print("core Init=0x%x AllocParams=0x%x" % (initStd, allocP))

    # optional dlss.dll (mode A)
    dlss = None
    if mode == "A":
        dlss = k32.LoadLibraryW(ctypes.c_wchar_p(SL + r"\nvngx_dlss.dll"))
        print("nvngx_dlss.dll -> 0x%x" % (dlss or 0))

    # dlssnr + patch
    nr = k32.LoadLibraryW(ctypes.c_wchar_p(SL + r"\nvngx_dlssnr.dll"))
    print("nvngx_dlssnr.dll -> 0x%x" % (nr or 0))
    if not nr: return
    global core_handle
    core_handle = core
    patch_dlssnr(nr)

    # core Init (5-arg)
    dataPath = ctypes.create_unicode_buffer("C:\\")
    fci = FCI()
    PFN_INIT = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_uint64, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
    r = PFN_INIT(initStd)(kAppId, dataPath, dev, 0x13, ctypes.byref(fci))
    print("core Init(0x13) -> 0x%x (%s)" % (r, "ok" if r==kSuccess else "refused"))

    # AllocateParameters
    params = ctypes.c_void_p()
    PFN_ALLOC = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
    ar = PFN_ALLOC(allocP)(ctypes.byref(params))
    print("AllocateParameters -> 0x%x params=0x%x" % (ar, params.value or 0))

    # dlssnr Init_Ext
    nrInitExt = ctypes.cast(k32.GetProcAddress(nr, b"NVSDK_NGX_D3D12_Init_Ext"), ctypes.c_void_p).value
    PFN_IE = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_uint64, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
    try:
        r2 = PFN_IE(nrInitExt)(kAppId, dataPath, dev, 0x13, ctypes.byref(fci))
        print("dlssnr Init_Ext(0x13) -> 0x%x (%s)" % (r2, "OK!!!" if r2==kSuccess else "refused"))
    except Exception as e:
        print("dlssnr Init_Ext EXCEPTION: %s" % e)
    return r2

if __name__ == "__main__":
    run("B")
    print("\nMode B completed")
