# v0.9 NGX direct-link harness - verify Init/Allocate/Set/CreateFeature WITHOUT the game
# Loads driver nvngx.dll (core) + patched nvngx_dlssnr.dll, creates a D3D12 device,
# and runs the exact RenoDX-verified sequence, printing every return code.
import ctypes, ctypes.wintypes as wt, sys, os, uuid

D3D12Core = os.environ.get("D3D12CORE", r"C:\Windows\System32\D3D12Core.dll")
DRIVER_NVNGX = r"C:\Windows\System32\DriverStore\FileRepository\nv_dispi.inf_amd64_a3944b54ff18b284\nvngx.dll"
DLSSNR = r"D:\Modding\renodx\extracted\streamline\nvngx_dlssnr.dll"
# fallbacks
if not os.path.exists(DRIVER_NVNGX):
    import glob
    cands = glob.glob(r"C:\Windows\System32\DriverStore\FileRepository\nv_dispi.inf_amd64_*\nvngx.dll")
    if cands:
        DRIVER_NVNGX = cands[0]
print("driver nvngx:", DRIVER_NVNGX, os.path.exists(DRIVER_NVNGX))
print("dlssnr:", DLSSNR, os.path.exists(DLSSNR))

d3d12 = ctypes.WinDLL("d3d12.dll")
D3D12CreateDevice = d3d12.D3D12CreateDevice
D3D12CreateDevice.restype = ctypes.c_long
D3D12CreateDevice.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]

IID_ID3D12Device = uuid.UUID("189819f1-1db6-4b57-be54-1821339b85f7")
def iid_bytes(iid):
    b = iid.bytes_le
    return b

# --- create D3D12 device ---
dev = ctypes.c_void_p()
hr = D3D12CreateDevice(None, 0xc000, iid_bytes(IID_ID3D12Device), ctypes.byref(dev))  # D3D_FEATURE_LEVEL_11_0 = 0xc000
print("D3D12CreateDevice hr=%#x dev=0x%x" % (hr & 0xffffffff, dev.value))
if hr != 0:
    sys.exit(1)
DEV = dev.value

# --- load core + dlssnr ---
core = ctypes.WinDLL(DRIVER_NVNGX)
nr = ctypes.WinDLL(DLSSNR)
print("core loaded:", bool(core._handle), " dlssnr loaded:", bool(nr._handle))

def proc(mod, name):
    p = ctypes.cast(mod[name], ctypes.c_void_p).value
    return p

# --- Init: NVSDK_NGX_D3D12_Init(appId, path, device, version) ---
fnInit = proc(nr, "NVSDK_NGX_D3D12_Init")
print("Init addr: 0x%x" % fnInit)
if not fnInit:
    sys.exit(1)
INIT = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_uint64, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint)
path = ctypes.c_wchar_p("")
for ver in (0x15, 0x0, 0x100, 0x2000000, 0x31080000, 0x1400000):
    r = INIT(fnInit)(0x1337, path, DEV, ver)
    print("Init ver=%#x -> %#x" % (ver, r))
    if r == 1:
        print("  Init SUCCESS with ver=%#x" % ver)
        break
else:
    print("Init FAILED all versions")
    sys.exit(1)

# --- AllocateParameters (driver core) ---
fnAlloc = proc(core, "NVSDK_NGX_D3D12_AllocateParameters")
print("Alloc addr: 0x%x" % fnAlloc)
if not fnAlloc:
    sys.exit(1)
ALLOC = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
params = ctypes.c_void_p()
ar = ALLOC(fnAlloc)(ctypes.byref(params))
print("AllocateParameters -> %#x params=0x%x" % (ar, params.value))
if ar != 1 or not params.value:
    sys.exit(1)
P = params.value

# --- vtable Set probes: find slot for Set(name,uint) by testing Get roundtrip ---
def vtslot(obj, n):
    return ctypes.cast(ctypes.c_void_p(ctypes.cast(obj, ctypes.c_void_p).value), ctypes.POINTER(ctypes.c_void_p))[n]

# try slots 0..24: call as Set(name,uint) with a marker, then Get(name,&val) to verify
SETU = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint)
SETF = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_float)
GETU = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint))
marker = b"HARNESS.PROBE"
val = ctypes.c_uint(0)
for slot in range(0, 24):
    fn = vtslot(P, slot)
    if not fn:
        continue
    r = SETU(fn)(P, marker, 0xDEAD)
    if r == 1:  # plausible Set success
        out = ctypes.c_uint(0)
        # find Get slot: try same slot and nearby
        for gs in range(8, 24):
            gfn = vtslot(P, gs)
            if not gfn:
                continue
            out.value = 0
            gr = GETU(gfn)(P, marker, ctypes.byref(out))
            if gr == 1 and out.value == 0xDEAD:
                print("  SetUI slot=%d GetUI slot=%d roundtrip OK" % (slot, gs))
                SETUI_SLOT, GETUI_SLOT = slot, gs
                break
        else:
            continue
        break
else:
    print("  !! no SetUI slot found - vtable layout differs")
    sys.exit(1)

def setUI(name, v):
    fn = vtslot(P, SETUI_SLOT)
    return SETU(fn)(P, name.encode(), v)
def setF(name, v):
    fn = vtslot(P, 4)
    return SETF(fn)(P, name.encode(), ctypes.c_float(v))

print("== set params ==")
print("  W        -> %#x" % setUI("DLSSNR.Width", 1920))
print("  H        -> %#x" % setUI("DLSSNR.Height", 1080))
print("  Scaling  -> %#x" % setF("DLSSNR.ScalingRatio", 1.0))
print("  Enabled  -> %#x" % setUI("DLSSNR.Enabled", 1))
print("  Reset    -> %#x" % setUI("DLSSNR.Reset", 1))

# --- CreateFeature: needs a command list ---
# ID3D12Device vtable: 13=CreateCommandQueue 14=CreateCommandAllocator 17=CreateGraphicsCommandList
DEVVT = ctypes.cast(DEV, ctypes.POINTER(ctypes.c_void_p))
CreateCommandAllocator = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
CreateGraphicsCommandList = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
IID_ID3D12CommandAllocator = uuid.UUID("6102dee4-af59-4b09-b999-b44d73f09b24")
IID_ID3D12GraphicsCommandList = uuid.UUID("5b160d0f-ac1b-4185-8ba8-b3ae42a5a455")

alloc = ctypes.c_void_p()
hr = CreateCommandAllocator(DEVVT[14])(DEV, 0, iid_bytes(IID_ID3D12CommandAllocator), ctypes.byref(alloc))
print("CreateCommandAllocator hr=%#x alloc=0x%x" % (hr & 0xffffffff, alloc.value))
if hr != 0:
    sys.exit(1)

cl = ctypes.c_void_p()
hr = CreateGraphicsCommandList(DEVVT[17])(DEV, 0, 0, alloc.value, 0, iid_bytes(IID_ID3D12GraphicsCommandList), ctypes.byref(cl))
print("CreateGraphicsCommandList hr=%#x cl=0x%x" % (hr & 0xffffffff, cl.value))
if hr != 0:
    sys.exit(1)

fnCreate = proc(nr, "NVSDK_NGX_D3D12_CreateFeature")
print("CreateFeature addr: 0x%x" % fnCreate)
CREATE = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
handle = ctypes.c_void_p()
cr = CREATE(fnCreate)(cl.value, 18, P, ctypes.byref(handle))
print("CreateFeature(18) -> %#x handle=0x%x" % (cr, handle.value))

if cr == 1 and handle.value:
    print("== feature created! trying EvaluateFeature ==")
    fnEval = proc(nr, "NVSDK_NGX_D3D12_EvaluateFeature")
    EVAL = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    er = EVAL(fnEval)(cl.value, handle.value, P, None)
    print("EvaluateFeature -> %#x" % er)
    print("HARNESS RESULT: EVALUATE_RC=%#x" % er)
else:
    print("HARNESS RESULT: CREATE_RC=%#x handle=0x%x" % (cr, handle.value))
