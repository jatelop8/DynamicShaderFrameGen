# v0.24: can dlssnr CreateFeature work WITHOUT Init_Ext (direct call, own export 0x15750)?
# Community addon path detours CreateFeature/EvaluateFeature - if CreateFeature works
# standalone on a driver-core session, we skip Init_Ext entirely (its crash is moot).
import ctypes, uuid, struct, sys
sys.path.insert(0, r"D:\Modding\DynamicShaderFrameGen")
import harness_nr_verify as H  # no side effects now (guarded)

SL = H.SL
k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
k32.LoadLibraryW.restype = ctypes.c_void_p
k32.LoadLibraryW.argtypes = [ctypes.c_wchar_p]
k32.GetProcAddress.restype = ctypes.c_void_p
k32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

d3d12 = ctypes.WinDLL("d3d12.dll")
dev = ctypes.c_void_p()
iid = uuid.UUID("189819f1-1db6-4b57-be54-1821339b85f7").bytes_le
ibuf = ctypes.create_string_buffer(iid, 16)
hr = d3d12.D3D12CreateDevice(None, 0xc000, ctypes.cast(ibuf, ctypes.c_void_p), ctypes.byref(dev))
print("device 0x%x hr=0x%x" % (dev.value or 0, hr & 0xffffffff))
if not dev.value:
    sys.exit(1)

core = k32.LoadLibraryW(H.DRIVER_NVNGX)
nr = k32.LoadLibraryW(SL + r"\nvngx_dlssnr.dll")
print("core 0x%x dlssnr 0x%x" % (core, nr))
H.core_handle = core
H.patch_dlssnr(nr)

initStd = k32.GetProcAddress(core, b"NVSDK_NGX_D3D12_Init")
allocP = k32.GetProcAddress(core, b"NVSDK_NGX_D3D12_AllocateParameters")
dataPath = ctypes.create_unicode_buffer("C:\\")
fci = H.FCI()
PFN_INIT = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_uint64, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
r = PFN_INIT(initStd)(H.kAppId, dataPath, dev, 0x13, ctypes.byref(fci))
print("core Init -> 0x%x" % r)
params = ctypes.c_void_p()
PFN_ALLOC = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
ar = PFN_ALLOC(allocP)(ctypes.byref(params))
print("AllocateParameters -> 0x%x params=0x%x" % (ar, params.value or 0))

# D3D12 cmdlist via vtable (ID3D12Device: CreateCommandAllocator slot 10, CreateCommandList slot 11)
class VT(ctypes.Structure):
    _fields_ = [("f", ctypes.c_void_p)] * 60
vt = ctypes.cast(dev, ctypes.POINTER(ctypes.POINTER(VT)))
CreateCommandAllocator = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
CreateCommandList = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
# ID3D12Device vtable: IUnknown(0-2) ID3D12Object(3-5) ID3D12DeviceChild(6-8) ID3D12Device(9+)
# 9=GetNodeCount 10=CreateCommandQueue 11=CreateCommandAllocator 12=CreateCommandList
IID_CA = uuid.UUID("6102dee4-af59-4b09-b999-b448d73f09b7").bytes_le
IID_CL = uuid.UUID("5b2d072e-bc35-4a0e-9e75-0d8f1f9c8e9e").bytes_le
alloc = ctypes.c_void_p(); cl = ctypes.c_void_p()
h1 = CreateCommandAllocator(vt[0][11], dev, 0, ctypes.cast(ctypes.create_string_buffer(IID_CA,16), ctypes.c_void_p), ctypes.byref(alloc))
h2 = CreateCommandList(vt[0][12], dev, 0, 0, alloc, None, ctypes.cast(ctypes.create_string_buffer(IID_CL,16), ctypes.c_void_p), ctypes.byref(cl))
print("cmdalloc hr=0x%x cmdlist hr=0x%x cl=0x%x" % (h1 & 0xffffffff, h2 & 0xffffffff, cl.value or 0))
if not cl.value:
    sys.exit(1)

# set feature params (DLSSNR.* keys, like the plugin would)
# params is NVSDK_NGX_Parameter from driver core: vtable Set(name,uint) slot3, Set(name,float) slot4
def setUI(p, n, v):
    vt2 = ctypes.cast(ctypes.c_void_p(p), ctypes.POINTER(ctypes.POINTER(VT)))
    fn = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint)(vt2[0][3])
    return fn(p, n, v)
def setF(p, n, v):
    vt2 = ctypes.cast(ctypes.c_void_p(p), ctypes.POINTER(ctypes.POINTER(VT)))
    fn = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_float)(vt2[0][4])
    return fn(p, n, v)
P = params.value
for n, v in [(b"DLSSNR.Width", 3840), (b"DLSSNR.Height", 2160), (b"DLSSNR.ScalingRatio", 1.0),
             (b"DLSSNR.Enabled", 1), (b"DLSSNR.Reset", 1), (b"Width", 3840), (b"Height", 2160),
             (b"OutWidth", 3840), (b"OutHeight", 2160), (b"DLSS.Feature.Create.Flags", 107),
             (b"CreationNodeMask", 1), (b"VisibilityNodeMask", 1)]:
    if isinstance(v, int):
        rr = setUI(P, n, v)
    else:
        rr = setF(P, n, v)
    print("Set %s -> 0x%x" % (n.decode(), rr))

# direct dlssnr CreateFeature, feature id candidates: 18 (Reserved18/DLSS-NR), 0, 6, 1
cf = k32.GetProcAddress(nr, b"NVSDK_NGX_D3D12_CreateFeature")
PFN_CF = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
for fid in (18, 0, 6, 1, 1004):
    hnd = ctypes.c_void_p()
    try:
        cr = PFN_CF(cf)(cl, fid, P, ctypes.byref(hnd))
        print("dlssnr CreateFeature(%d) direct -> 0x%x handle=0x%x" % (fid, cr, hnd.value or 0))
        if cr == 1 and hnd.value:
            print(">>> CREATE FEATURE SUCCESS WITHOUT Init_Ext! fid=%d" % fid)
            break
    except Exception as e:
        print("CreateFeature(%d) EXCEPTION: %s" % (fid, e))
        break
print("Done.")
