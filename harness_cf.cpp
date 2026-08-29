// v0.24: can dlssnr CreateFeature (own export 0x15750) work WITHOUT Init_Ext?
// Full: D3D12 device + cmdlist + driver core Init + AllocateParameters + dlssnr 7-patch
// + direct CreateFeature(fid) -> if success, we skip Init_Ext entirely.
#include <windows.h>
#include <d3d12.h>
#include <dxgi1_4.h>
#include <cstdio>
#include <string>

#define kAppId 0x1000000ULL
#define kSuccess 0x1
const wchar_t* SL_DIR = L"D:\\Modding\\renodx\\extracted\\streamline";
const wchar_t* DRIVER_NVNGX = L"C:\\Windows\\System32\\DriverStore\\FileRepository\\nv_dispi.inf_amd64_a3944b54ff18b284\\nvngx.dll";

struct FCI { unsigned int instanceId; unsigned int cnMask; unsigned int vnMask; unsigned int reserved; void* userData; };

static HMODULE g_core = 0;
static BOOL WINAPI FakeGMHEXW(DWORD, LPCWSTR, HMODULE* o) { if (o) *o = g_core; return TRUE; }
static HMODULE WINAPI FakeGMHA(LPCSTR) { return g_core; }

static void PatchMem(uintptr_t base, unsigned off, const void* d, size_t n) {
    DWORD oldp; VirtualProtect((void*)(base + off), n, PAGE_EXECUTE_READWRITE, &oldp);
    memcpy((void*)(base + off), d, n); VirtualProtect((void*)(base + off), n, oldp, &oldp);
}

static void PatchDlssnr(HMODULE m) {
    uintptr_t b = (uintptr_t)m;
    // IAT stubs
    PatchMem(b, 0xac118, &FakeGMHEXW, 8);
    PatchMem(b, 0xac080, &FakeGMHA, 8);
    // code patches
    const BYTE jmp = 0xE9; PatchMem(b, 0x15e97, &jmp, 1);
    const BYTE ret0[] = { 0x31,0xC0,0xC3 }; PatchMem(b, 0x7ab60, ret0, 3);
    const BYTE ret1[] = { 0xB8,0x01,0x00,0x00,0x00,0xC3 }; PatchMem(b, 0x8810, ret1, 6);
    const BYTE nops[6] = { 0x90,0x90,0x90,0x90,0x90,0x90 }; PatchMem(b, 0x144bd, nops, 6);
    printf("dlssnr 7-patch @0x%llx\n", (unsigned long long)b);
}

typedef unsigned int(__cdecl* PFN_Init)(unsigned long long, const wchar_t*, ID3D12Device*, int, const void*);
typedef unsigned int(__cdecl* PFN_Alloc)(void**);
typedef unsigned int(__cdecl* PFN_CF)(ID3D12GraphicsCommandList*, int, void*, void**);

int main() {
    ID3D12Device* dev = nullptr;
    HRESULT hr = D3D12CreateDevice(nullptr, D3D_FEATURE_LEVEL_12_0, IID_PPV_ARGS(&dev));
    printf("device hr=0x%x dev=%p\n", (unsigned)hr, dev);
    if (FAILED(hr)) return 1;

    g_core = LoadLibraryW(DRIVER_NVNGX);
    HMODULE nr = LoadLibraryW(L"D:\\Modding\\renodx\\extracted\\streamline\\nvngx_dlssnr.dll");
    printf("core=%p dlssnr=%p\n", g_core, nr);
    if (!g_core || !nr) return 1;
    PatchDlssnr(nr);

    PFN_Init init = (PFN_Init)GetProcAddress(g_core, "NVSDK_NGX_D3D12_Init");
    PFN_Alloc alloc = (PFN_Alloc)GetProcAddress(g_core, "NVSDK_NGX_D3D12_AllocateParameters");
    wchar_t path[] = L"C:\\";
    FCI fci{};
    // v0.24: try appId/ver combos - session identity may be the crash key
    unsigned long long appIds[] = { kAppId, 0x1337, 0x3000000, 0x4000000, 0x5000000, 0x1000001 };
    int vers[] = { 0x13, 0x14, 0x15, 0x16 };
    int okInit = 0; unsigned long long okApp = 0; int okVer = 0;
    for (auto a : appIds) for (auto v : vers) {
        unsigned r = init(a, path, dev, v, &fci);
        if (r == kSuccess) { okInit = 1; okApp = a; okVer = v; printf("Init OK appId=0x%llx ver=0x%x\n", a, v); break; }
    }
    if (!okInit) { printf("no Init combo succeeded\n"); return 1; }
    void* params = nullptr;
    unsigned ar = alloc(&params);
    printf("AllocateParameters -> 0x%x params=%p\n", ar, params);

    ID3D12CommandAllocator* ca = nullptr;
    ID3D12GraphicsCommandList* cl = nullptr;
    hr = dev->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(&ca));
    printf("cmdalloc hr=0x%x\n", (unsigned)hr);
    hr = dev->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, ca, nullptr, IID_PPV_ARGS(&cl));
    printf("cmdlist hr=0x%x cl=%p\n", (unsigned)hr, cl);
    cl->Close();

    // set params (driver-core NVSDK_NGX_Parameter vtable: slot3 Set(name,uint) slot4 Set(name,float))
    struct PVT { void* v[24]; };
    PVT* pvt = *(PVT**)params;
    auto setU = [&](const char* n, unsigned v) { return ((unsigned(__cdecl*)(void*, const char*, unsigned))pvt->v[3])(params, n, v); };
    auto setF = [&](const char* n, float v) { return ((unsigned(__cdecl*)(void*, const char*, float))pvt->v[4])(params, n, v); };
    setU("DLSSNR.Width", 3840); setU("DLSSNR.Height", 2160); setF("DLSSNR.ScalingRatio", 1.0f);
    setU("DLSSNR.Enabled", 1); setU("DLSSNR.Reset", 1);
    setU("Width", 3840); setU("Height", 2160); setU("OutWidth", 3840); setU("OutHeight", 2160);
    setU("DLSS.Feature.Create.Flags", 107); setU("CreationNodeMask", 1); setU("VisibilityNodeMask", 1);
    printf("params set\n");

    PFN_CF cf = (PFN_CF)GetProcAddress(nr, "NVSDK_NGX_D3D12_CreateFeature");
    printf("dlssnr CreateFeature @%p\n", cf);
    for (int fid : { 18, 0, 6, 1, 1004 }) {
        void* h = nullptr;
        __try {
            unsigned cr = cf(cl, fid, params, &h);
            printf("CreateFeature(%d) -> 0x%x h=%p\n", fid, cr, h);
            if (cr == kSuccess && h) { printf(">>> SUCCESS WITHOUT Init_Ext! fid=%d\n", fid); break; }
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            printf("CreateFeature(%d) FAULT 0x%x\n", fid, (unsigned)GetExceptionCode());
            break;
        }
    }
    printf("Done.\n");
    return 0;
}
