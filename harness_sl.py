# Streamline path harness: slInit + slGetFeatureFunction(kFeatureDLSS_NR?) + slEvaluateFeature
# Uses the PATCHED sl.interposer/sl.dlss_nr from RenoDX streamline.zip
import ctypes, ctypes.wintypes as wt, uuid, os, sys

SL_DIR = r"D:\Modding\renodx\extracted\streamline"
SLI = os.path.join(SL_DIR, "sl.interposer.dll")
print("sl.interposer:", SLI, os.path.exists(SLI))
sl = ctypes.WinDLL(SLI)
print("sl.interposer loaded:", bool(sl._handle))

def gpa(name):
    try:
        return ctypes.cast(sl[name], ctypes.c_void_p).value
    except Exception:
        return 0

slInit = gpa("slInit")
slGetFeatureFunction = gpa("slGetFeatureFunction")
slShutdown = gpa("slShutdown")
print("slInit=0x%x slGetFeatureFunction=0x%x slShutdown=0x%x" % (slInit, slGetFeatureFunction, slShutdown))

# --- D3D12 device ---
d3d12 = ctypes.WinDLL("d3d12.dll")
D3D12CreateDevice = d3d12.D3D12CreateDevice
D3D12CreateDevice.restype = ctypes.c_long
D3D12CreateDevice.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
IID_ID3D12Device = uuid.UUID("189819f1-1db6-4b57-be54-1821339b85f7").bytes_le
dbuf = ctypes.create_string_buffer(IID_ID3D12Device, 16)
dev = ctypes.c_void_p()
D3D12CreateDevice(None, 0xc000, ctypes.cast(dbuf, ctypes.c_void_p), ctypes.byref(dev))
print("device=0x%x" % (dev.value or 0))

# --- Preferences layout (sl_core_types.h) ---
# +0x00 bool showConsole; +0x08 u32 logLevel; +0x10 ptr pathsToPlugins; +0x18 u32 numPathsToPlugins
# +0x20 ptr pathToLogsAndData; +0x28 allocCb; +0x30 releaseCb; +0x38 logCb
# +0x40 u64 flags; +0x48 ptr featuresToLoad; +0x50 u32 numFeaturesToLoad
# +0x58 u32 applicationId; +0x60 u32 engine; +0x68 ptr engineVersion; +0x70 ptr projectId; +0x78 u32 renderAPI
kSDKVersion = (2 << 48) | (12 << 32) | (0 << 16) | 0xFEDC
FEATURE_CANDIDATES = [1002, 1003, 1004, 0, 1000, 1001, 1100, 2000, 1500, 1200]

def build_prefs(feat):
    buf = ctypes.create_string_buffer(0x80)
    ctypes.memset(buf, 0, 0x80)
    # logLevel = 0 (eDefault)
    # flags = eDisableCLStateTracking|eAllowOTA|eLoadDownloadedPlugins = 1|8|64 = 73? use eAll-ish: set 0 for simplicity
    # featuresToLoad pointer -> need persistent storage
    feat_arr = (ctypes.c_uint64 * 1)(feat)
    # featuresToLoad at +0x48, numFeaturesToLoad at +0x50
    ftl = ctypes.addressof(feat_arr)
    ctypes.c_uint64.from_buffer(buf, 0x48).value = ftl
    ctypes.c_uint32.from_buffer(buf, 0x50).value = 1
    ctypes.c_uint32.from_buffer(buf, 0x58).value = 0x1337  # applicationId
    # engine = 0 (eCustom), renderAPI = 0 (eD3D12) already 0
    return buf, feat_arr

SL_INIT = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint64)

for feat in FEATURE_CANDIDATES:
    prefs, arr = build_prefs(feat)
    r = SL_INIT(slInit)(ctypes.addressof(prefs), kSDKVersion)
    print("slInit(featuresToLoad=%d) -> %d (0x%x)" % (feat, r, r))
    if r == 0:  # sl::Result eOk = 0? check
        print("  slInit OK with feature %d" % feat)
        break
    sl_shutdown_f = ctypes.CFUNCTYPE(ctypes.c_int64)(slShutdown) if slShutdown else None
    if sl_shutdown_f:
        sl_shutdown_f()
