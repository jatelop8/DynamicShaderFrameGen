# v0.18 harness v2: corrected Preferences layout (BaseStructure 32B prefix)
# +0x00 next(8) +0x08 structType(16 GUID) +0x18 structVersion(8)
# +0x20 showConsole(1) +0x28 logLevel(4) +0x30 pathsToPlugins(8) +0x38 numPathsToPlugins(4)
# +0x40 pathToLogsAndData(8) +0x48 allocateCb(8) +0x50 releaseCb(8) +0x58 logCb(8)
# +0x60 flags(8) +0x68 featuresToLoad(8) +0x70 numFeaturesToLoad(4) +0x78 applicationId(4)
# +0x80 engine(4) +0x88 engineVersion(8) +0x90 projectId(8) +0x98 renderAPI(4)
import ctypes, os, struct

SL_DIR = r"D:\Modding\renodx\extracted\streamline"
sl = ctypes.WinDLL(os.path.join(SL_DIR, "sl.interposer.dll"))
def gpa(name):
    try: return ctypes.cast(sl[name], ctypes.c_void_p).value
    except Exception: return 0
slInit = gpa("slInit"); slShutdown = gpa("slShutdown")
slIsFeatureLoaded = gpa("slIsFeatureLoaded"); slSetD3DDevice = gpa("slSetD3DDevice")
slGetFeatureRequirements = gpa("slGetFeatureRequirements")
print("slInit=0x%x slSetD3DDevice=0x%x slIsFeatureLoaded=0x%x" % (slInit, slSetD3DDevice, slIsFeatureLoaded))

LOG_LINES = []
LOG_CB = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p)
@LOG_CB
def log_cb(ltype, msg):
    try: s = msg.decode("utf-8", "replace") if msg else ""
    except Exception: s = repr(msg)
    LOG_LINES.append(s)
    print("[SL] %s" % s)

kSDKVersion = (2 << 48) | (12 << 32) | (0 << 16) | 0xFEDC
GUID = bytes.fromhex("65 09 a1 1c 8e bf 2b 43 8d a1 67 16 d8 79 fb 14")  # 1ca10965-bf8e-432b-8da1-6716d879fb14

def build_prefs(feats, flags, log_level):
    n = len(feats)
    feat_arr = (ctypes.c_uint64 * n)(*feats)
    buf = ctypes.create_string_buffer(0xA0)
    ctypes.memset(buf, 0, 0xA0)
    eng_ver = ctypes.create_string_buffer(b"1.0.0")
    proj_id = ctypes.create_string_buffer(b"f8776929-c969-43bd-ac2b-294b4de58aac")
    ctypes.memmove(ctypes.addressof(buf) + 0x08, GUID, 16)          # structType
    ctypes.c_uint64.from_buffer(buf, 0x18).value = 1                 # structVersion (kStructVersion1)
    ctypes.c_uint32.from_buffer(buf, 0x28).value = log_level         # logLevel
    ctypes.c_uint64.from_buffer(buf, 0x58).value = ctypes.cast(log_cb, ctypes.c_void_p).value  # logCb
    ctypes.c_uint64.from_buffer(buf, 0x60).value = flags             # flags
    ctypes.c_uint64.from_buffer(buf, 0x68).value = ctypes.addressof(feat_arr)
    ctypes.c_uint32.from_buffer(buf, 0x70).value = n
    ctypes.c_uint32.from_buffer(buf, 0x78).value = 0x1337            # applicationId
    ctypes.c_uint32.from_buffer(buf, 0x80).value = 0                 # engine eCustom
    ctypes.c_uint64.from_buffer(buf, 0x88).value = ctypes.addressof(eng_ver)   # engineVersion
    ctypes.c_uint64.from_buffer(buf, 0x90).value = ctypes.addressof(proj_id)   # projectId
    ctypes.c_uint32.from_buffer(buf, 0x98).value = 0                 # renderAPI eD3D12
    return buf, feat_arr, eng_ver, proj_id

# D3D12 device for slSetD3DDevice (matches game flow: slInit -> slSetD3DDevice)
dev = ctypes.c_void_p()
try:
    d3d12 = ctypes.WinDLL("d3d12.dll")
    import uuid as _uuid
    IID_ID3D12Device = _uuid.UUID("189819f1-1db6-4b57-be54-1821339b85f7").bytes_le
    dbuf = ctypes.create_string_buffer(IID_ID3D12Device, 16)
    D3D12CreateDevice = d3d12.D3D12CreateDevice
    D3D12CreateDevice.restype = ctypes.c_long
    D3D12CreateDevice.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    hr = D3D12CreateDevice(None, 0xc000, ctypes.cast(dbuf, ctypes.c_void_p), ctypes.byref(dev))
    print("D3D12CreateDevice -> hr=0x%x dev=0x%x" % (hr & 0xffffffff, dev.value or 0))
except Exception as e:
    print("no d3d12 device:", e)

def run(tag, feats, flags, do_set_device):
    LOG_LINES.clear()
    prefs, arr, _ev, _pj = build_prefs(feats, flags, 2)
    SL_INIT = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint64)
    r = SL_INIT(slInit)(ctypes.addressof(prefs), kSDKVersion)
    print("\n=== %s: slInit(feats=%s flags=0x%x) -> 0x%x (%d)" % (tag, feats, flags, r, r))
    if r != 0:
        print("  slInit failed, skip")
        return
    if do_set_device and slSetD3DDevice and dev.value:
        SD = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p)
        sr = SD(slSetD3DDevice)(dev)
        print("slSetD3DDevice -> 0x%x (%d)" % (sr, sr))
    if slIsFeatureLoaded:
        loaded = ctypes.c_bool(False)
        SL_LOADED = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_uint64, ctypes.POINTER(ctypes.c_bool))
        lr = SL_LOADED(slIsFeatureLoaded)(1004, ctypes.byref(loaded))
        print("slIsFeatureLoaded(1004) -> rc=0x%x loaded=%s" % (lr, loaded.value))
    k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    h = k32.GetModuleHandleW(ctypes.c_wchar_p("sl.dlss_nr.dll"))
    print("GetModuleHandleW(sl.dlss_nr.dll) -> 0x%x (%s)" % (h or 0, "LOADED" if h else "NOT loaded"))
    print("--- interposer log ---")
    for s in LOG_LINES:
        print("  ", s[:220])
    # shutdown
    if slShutdown:
        try: ctypes.CFUNCTYPE(ctypes.c_int64)(slShutdown)()
        except Exception: pass

run("A-init only", [1004], 0x0, False)
run("B-setdevice", [1004], 0x0, True)
run("C-flags 0x40", [1004], 0x40, True)
run("D-full flags", [1004], 0x1|0x8|0x40, True)
run("E-multi feat", [0,1000,3,1004], 0x1|0x8|0x40, True)
print("\nDone.")
