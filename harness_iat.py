# ReShade-style verification: patch patched-dlssnr IAT (GetModuleHandleExW/GetModuleHandleA -> stubs)
# so the "Not called from NGX runtime" check passes, then Init_Ext -> CreateFeature(18) -> Evaluate.
import ctypes, ctypes.wintypes as wt, uuid, os, glob, struct

DRIVER = r"C:\Windows\System32\DriverStore\FileRepository\nv_dispi.inf_amd64_a3944b54ff18b284\nvngx.dll"
if not os.path.exists(DRIVER):
    DRIVER = glob.glob(r"C:\Windows\System32\DriverStore\FileRepository\nv_dispi.inf_amd64_*\nvngx.dll")[0]
DLSSNR = r"D:\Modding\renodx\extracted\streamline\nvngx_dlssnr.dll"

core = ctypes.WinDLL(DRIVER)
nr = ctypes.WinDLL(DLSSNR)
nr_base = ctypes.cast(nr._handle, ctypes.c_void_p).value
core_base = ctypes.cast(core._handle, ctypes.c_void_p).value
print("dlssnr base=0x%x core base=0x%x" % (nr_base, core_base))

# ---- D3D12 device ----
d3d12 = ctypes.WinDLL("d3d12.dll")
D3D12CreateDevice = d3d12.D3D12CreateDevice
D3D12CreateDevice.restype = ctypes.c_long
D3D12CreateDevice.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
IID_ID3D12Device = uuid.UUID("189819f1-1db6-4b57-be54-1821339b85f7").bytes_le
dbuf = ctypes.create_string_buffer(IID_ID3D12Device, 16)
dev = ctypes.c_void_p()
D3D12CreateDevice(None, 0xc000, ctypes.cast(dbuf, ctypes.c_void_p), ctypes.byref(dev))
print("device=0x%x" % (dev.value or 0))

# ---- IAT slots of dlssnr (runtime addresses) ----
IAT_GetModuleHandleExW = nr_base + 0xac118
IAT_GetModuleHandleA  = nr_base + 0xac080
print("IAT[0xac118](GetModuleHandleExW) = 0x%x" % ctypes.c_uint64.from_address(IAT_GetModuleHandleExW).value)
print("IAT[0xac080](GetModuleHandleA)  = 0x%x" % ctypes.c_uint64.from_address(IAT_GetModuleHandleA).value)

# ---- stub callbacks ----
k32 = ctypes.WinDLL("kernel32.dll")
# stub GetModuleHandleExW(dwFlags, lpModuleName, phModule): always claim dlssnr module
GetModuleHandleExW_T = ctypes.CFUNCTYPE(wt.BOOL, wt.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
def stub_GetModuleHandleExW(flags, name, out):
    out[0] = nr_base
    return True
stub_exw = GetModuleHandleExW_T(stub_GetModuleHandleExW)
# stub GetModuleHandleA(lpModuleName): return core handle (nvngx.dll)
GetModuleHandleA_T = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)
def stub_GetModuleHandleA(name):
    return core_base
stub_ga = GetModuleHandleA_T(stub_GetModuleHandleA)

# ---- patch IAT (make writable first) ----
def patch_iat(slot, stub_ptr):
    old = ctypes.c_uint64.from_address(slot).value
    k32.VirtualProtect(ctypes.c_void_p(slot), 8, 0x40, ctypes.byref(ctypes.c_uint32()))
    ctypes.c_uint64.from_address(slot).value = stub_ptr
    print("IAT patched 0x%x: 0x%x -> 0x%x" % (slot, old, stub_ptr))

patch_iat(IAT_GetModuleHandleExW, ctypes.cast(stub_exw, ctypes.c_void_p).value)
patch_iat(IAT_GetModuleHandleA, ctypes.cast(stub_ga, ctypes.c_void_p).value)

# ---- Init_Ext (patched dlssnr, 5 params) ----
INIT_EXT = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_uint64, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p)
fnInitExt = ctypes.cast(nr["NVSDK_NGX_D3D12_Init_Ext"], ctypes.c_void_p).value
for ver in (0x15, 0x1000000, 0x1400000, 0x31080000, 0x0, 0x2000000, 0x3000000, 0x1):
    r = INIT_EXT(fnInitExt)(0x1337, "", dev.value, ver, None)
    print("Init_Ext ver=%#x -> %#x" % (ver, r))
    if r == 1:
        print("  >>> INIT_EXT SUCCESS with IAT patch! ver=%#x" % ver)
        break
