// NGX entry-point signatures and negotiation logic derived from
//   dlss5-dx11-bridge (c) 2026 NIGos — MIT License
//   https://github.com/NIGos/dlss5-dx11-bridge
//   (recovered from disassembly; proven on BG3 / Fallout 4 / Unity)
// v0.8.8: Get()/settings live in FrameGen. CommonLib rule: Windows.h must come
// AFTER CommonLib - FrameGen.h first, then SKSE (which manages Windows.h).
#include "FrameGen.h"
#include "NGXNR.h"

#include <SKSE/SKSE.h>

#include <d3d12.h>

namespace FrameGen
{
	// ------------------------------------------------------------------
	// NGX function signatures — recovered from disassembly by the
	// dlss5-dx11-bridge project (MIT) and proven on multiple engines.
	// ------------------------------------------------------------------
	using PFN_NGXInitExt = unsigned int(__cdecl*)(unsigned long long a_appId,
		const wchar_t* a_dataPath, ID3D12Device* a_device, int a_version, const void* a_featureInfo);
	// v0.8.7: plain NVSDK_NGX_D3D12_Init (non-Ex). Disassembly of
	// nvngx_dlssnr.dll D3D12_Init (rva 0x15cf0) shows arg3 (r8) used as an
	// OUT handle (mov [r8],0 on success) while arg1/arg2 are not consumed —
	// signature: (u64 appId, wchar_t* path, void** outHandle, int ver, void* info)
	using PFN_NGXInit = unsigned int(__cdecl*)(unsigned long long a_appId,
		const wchar_t* a_dataPath, void** a_outHandle, int a_sdkVersion, const void* a_featureInfo);
	using PFN_NGXInitProjectID = unsigned int(__cdecl*)(const char* a_project, int a_engineType,
		const char* a_version, const wchar_t* a_dataPath, ID3D12Device* a_device,
		int a_sdkVersion, const void* a_featureInfo);
	using PFN_NGXAllocParams = unsigned int(__cdecl*)(NGXInstanceParameters** a_params);
	using PFN_NGXCreateFeature = unsigned int(__cdecl*)(ID3D12GraphicsCommandList* a_cmdList,
		int a_featureId, NGXInstanceParameters* a_params, NGXHandle** a_handle);
	using PFN_NGXEvaluateFeature = unsigned int(__cdecl*)(ID3D12GraphicsCommandList* a_cmdList,
		const NGXHandle* a_handle, const NGXInstanceParameters* a_params, void* a_callback);
	using PFN_NGXReleaseFeature = unsigned int(__cdecl*)(NGXHandle* a_handle);
	using PFN_NGXGetCaps = unsigned int(__cdecl*)(NGXInstanceParameters** a_caps);

	namespace
	{
		constexpr unsigned long long kAppId = 0x1000000ULL;
		constexpr const char* kProjectId = "a0f57b54-1daf-4934-90ae-c4035c19df04";  // bridge's tested GUID
		constexpr int kFeatureSuperSampling = 1;  // DLSS-NR is a sub-mode of SuperSampling
		constexpr unsigned int kNGXExceptionMarker = 0x7FFFFFFF;

		std::string w2a(const std::wstring& a_w)
		{
			if (a_w.empty())
				return {};
			const int len = WideCharToMultiByte(CP_UTF8, 0, a_w.c_str(), static_cast<int>(a_w.size()), nullptr, 0, nullptr, nullptr);
			std::string s(static_cast<std::size_t>(len), '\0');
			WideCharToMultiByte(CP_UTF8, 0, a_w.c_str(), static_cast<int>(a_w.size()), &s[0], len, nullptr, nullptr);
			return s;
		}

		// guarded calls: a wrong signature must land in the log, never crash the game
		template <class Fn, class... Args>
		unsigned int Guarded(Fn a_fn, DWORD* a_code, Args&&... a_args)
		{
			*a_code = 0;
			__try {
				return a_fn(std::forward<Args>(a_args)...);
			} __except (EXCEPTION_EXECUTE_HANDLER) {
				*a_code = GetExceptionCode();
				return kNGXExceptionMarker;
			}
		}
	}  // namespace

	// ------------------------------------------------------------------
	// Init: load the DLSS-NR plugin, negotiate NGX SDK version, query caps
	// ------------------------------------------------------------------
	void NGXNR::Init(ID3D12Device* a_device, const wchar_t* a_pluginDir)
	{
		SKSE::log::info("[NGXNR] Init called: device={} initialized={} dir={}", (void*)a_device, initialized,
			a_pluginDir ? w2a(a_pluginDir) : "(null)");
		if (initialized || !a_device)
			return;
		device = a_device;

		// v0.8.7: load nvngx_dlssnr.dll first (the DLSS-NR plugin carries the
		// D3D12 backend; its D3D12_Init is a real implementation while the
		// *_Init_Ext exports are stubs returning 0xbad00001). Fall back to
		// nvngx_dlss.dll. Log the resolved path - LoadLibrary may reuse an
		// already-loaded module (e.g. one loaded by SkyrimUpscaler).
		std::wstring dllPath = std::wstring(a_pluginDir) + L"\\nvngx_dlssnr.dll";
		ngxModule = LoadLibraryW(dllPath.c_str());
		if (!ngxModule) {
			dllPath = std::wstring(a_pluginDir) + L"\\nvngx_dlss.dll";
			ngxModule = LoadLibraryW(dllPath.c_str());
		}
		if (!ngxModule) {
			SKSE::log::warn("[NGXNR] no nvngx_dlssnr.dll / nvngx_dlss.dll under {} - DLSS-NR disabled (no crash)", w2a(a_pluginDir));
			nvngxPresent = false;
			return;
		}
		nvngxPresent = true;
		wchar_t resolved[MAX_PATH] = {};
		GetModuleFileNameW(ngxModule, resolved, MAX_PATH);
		SKSE::log::info("[NGXNR] loaded {} (resolved: {})", w2a(dllPath), w2a(resolved));

		auto initExt = reinterpret_cast<PFN_NGXInitExt>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_Init_Ext"));
		auto init = reinterpret_cast<PFN_NGXInit>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_Init"));
		auto initProject = reinterpret_cast<PFN_NGXInitProjectID>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_Init_ProjectID"));
		auto allocParams = reinterpret_cast<PFN_NGXAllocParams>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_AllocateParameters"));
		auto getCaps = reinterpret_cast<PFN_NGXGetCaps>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_GetCapabilityParameters"));
		SKSE::log::info("[NGXNR] entry: Init_Ext={} Init={} Init_ProjectID={} Alloc={} Caps={}",
			(void*)initExt, (void*)init, (void*)initProject, (void*)allocParams, (void*)getCaps);
		if (!initExt && !init && !initProject) {
			SKSE::log::warn("[NGXNR] no NGX D3D12 Init entry points - DLSS-NR disabled");
			return;
		}

		// data path = directory of the game exe (NGX writes its logs there)
		wchar_t dataPath[MAX_PATH] = {};
		GetModuleFileNameW(nullptr, dataPath, MAX_PATH);
		if (wchar_t* s = wcsrchr(dataPath, L'\\'))
			*(s + 1) = L'\0';

		DWORD code = 0;
		bool inited = false;
		// v0.8.7: try ALL THREE init flavours per version. *_Init_Ext are
		// stubs on the 2.13 plugins (0xbad00001), plain Init is the real
		// implementation with an out-handle arg, Init_ProjectID sometimes
		// accepted on drivers that fault on the other two (bridge comment).
		for (int ver = 0x13; ver <= 0x16 && !inited; ++ver) {
			if (initExt) {
				unsigned int r = Guarded([&] { return initExt(kAppId, dataPath, a_device, ver, nullptr); }, &code);
				SKSE::log::info("[NGXNR] Init_Ext(0x{:02X}) -> {} (rc={:#x})", ver,
					code ? "faulted" : (r == kNGXSuccess ? "ok" : "refused"), code ? code : r);
				if (code == 0 && r == kNGXSuccess) { inited = true; initVersion = ver; break; }
			}
			if (init) {
				void* outHandle = nullptr;
				unsigned int r = Guarded([&] { return init(kAppId, dataPath, &outHandle, ver, nullptr); }, &code);
				SKSE::log::info("[NGXNR] Init(0x{:02X}) -> {} (rc={:#x} outHandle={})", ver,
					code ? "faulted" : (r == kNGXSuccess ? "ok" : "refused"), code ? code : r, outHandle);
				if (code == 0 && r == kNGXSuccess) { inited = true; initVersion = ver; break; }
			}
			if (initProject) {
				unsigned int r = Guarded([&] { return initProject(kProjectId, 0, "1.0", dataPath, a_device, ver, nullptr); }, &code);
				SKSE::log::info("[NGXNR] Init_ProjectID(0x{:02X}) -> {} (rc={:#x})", ver,
					code ? "faulted" : (r == kNGXSuccess ? "ok" : "refused"), code ? code : r);
				if (code == 0 && r == kNGXSuccess) { inited = true; initVersion = ver; break; }
			}
		}
		if (!inited) {
			SKSE::log::warn("[NGXNR] no NGX D3D12 init flavour accepted by this driver - DLSS-NR disabled");
			return;
		}
		SKSE::log::info("[NGXNR] NGX D3D12 session initialised (version 0x{:02X})", initVersion);
		initialized = true;

		// nvngx_dlssnr.dll presence (informational; without it the feature
		// will fail at creation and the menu stays greyed out)
		std::wstring nrDll = std::wstring(a_pluginDir) + L"\\nvngx_dlssnr.dll";
		nvngxNrPresent = GetFileAttributesW(nrDll.c_str()) != INVALID_FILE_ATTRIBUTES;
		SKSE::log::info("[NGXNR] nvngx_dlssnr.dll {}",
			nvngxNrPresent ? "present" : "NOT present (expected -> feature unavailable)");

		// GPU capability gate: SuperSamplingDenoising.Available is 0 on
		// hardware without the FP8 Blackwell kernel (RTX 40) — nothing else
		// matters then. This is the clean graceful-degradation check.
		if (getCaps) {
			NGXInstanceParameters* caps = nullptr;
			unsigned int r = Guarded([&] { return getCaps(&caps); }, &code);
			if (code == 0 && r == kNGXSuccess && caps) {
				int avail = 0;
				unsigned int rc = caps->Get4("SuperSamplingDenoising.Available", &avail);
				SKSE::log::info("[NGXNR] SuperSamplingDenoising.Available = {} (query {:#x})",
					rc == kNGXSuccess ? avail : -1, rc);
				supported = (rc == kNGXSuccess && avail != 0);
			} else {
				SKSE::log::warn("[NGXNR] capability query failed/faulted - DLSS-NR treated as unsupported");
			}
		}
		if (!supported) {
			SKSE::log::warn("[NGXNR] DLSS-NR not available on this GPU (RTX 40 lacks sm_120 FP8 kernel) - menu greyed, no crash");
			return;
		}

		// parameters object for feature creation + per-frame evaluation
		if (allocParams) {
			NGXInstanceParameters* p = nullptr;
			unsigned int r = Guarded([&] { return allocParams(&p); }, &code);
			if (code == 0 && r == kNGXSuccess && p)
				params = p;
		}
		if (!params) {
			SKSE::log::warn("[NGXNR] AllocateParameters failed - DLSS-NR disabled");
			supported = false;
			return;
		}
		needCreate = true;
		SKSE::log::info("[NGXNR] DLSS-NR ready (feature created on first evaluate frame)");
	}

	// ------------------------------------------------------------------
	// Evaluate: (re)create feature on demand, bind resources, evaluate
	// ------------------------------------------------------------------
	bool NGXNR::Evaluate(ID3D12Resource* a_color, ID3D12Resource* a_depth, ID3D12Resource* a_mvec,
		ID3D12Resource* a_output, unsigned int a_width, unsigned int a_height,
		ID3D12GraphicsCommandList* a_cmdList)
	{
		lastEvaluateOk = false;
		if (!initialized || !supported || !params || !a_color || !a_output || !a_cmdList)
			return false;

		auto createFeature = reinterpret_cast<PFN_NGXCreateFeature>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_CreateFeature"));
		auto evalFeature = reinterpret_cast<PFN_NGXEvaluateFeature>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_EvaluateFeature"));
		if (!createFeature || !evalFeature)
			return false;

		// --- (re)create on first frame / size change ---
		// v0.8.8：DLSS-NR 参数键全部用 DLSSNR.* 前缀（nvngx_dlssnr.dll 字符串表
		// 实锤：DLSSNR.Color/Depth/MVec/Output/Width/Height/Enabled/ScalingRatio/
		// DepthInverted/Reset...）。无前缀通用 DLSS 键（Color/Depth/Output）NR 不认。
		if (needCreate || a_width != outWidth || a_height != outHeight) {
			params->Set("DLSSNR.Width", a_width);
			params->Set("DLSSNR.Height", a_height);
			params->Set("DLSSNR.ScalingRatio", 1.0f);		  // DLAA 模式（4K→4K 滤镜）
			params->Set("DLSSNR.Enabled", 1);
			params->Set("DLSSNR.DepthInverted", 0);			  // Skyrim depth: 近=0 远=1
			params->Set("DLSSNR.Reset", 1);					  // 创建时重置内部状态
			params->Set("PerfQualityValue", 2);				  // balanced-ish; NR uses for ratio
			params->Set("DLSS.Feature.Create.Flags", 107);
			params->Set("DLSS.Enable.Output.Subrects", 1);
			params->Set("CreationNodeMask", 1u);
			params->Set("VisibilityNodeMask", 1u);
			params->Set("RTXValue", 0);

			DWORD code = 0;
			NGXHandle* h = nullptr;
			unsigned int r = Guarded([&] { return createFeature(a_cmdList, kFeatureSuperSampling, params, &h); }, &code);
			lastCreateResult = code ? kNGXExceptionMarker : r;
			if (code != 0) {
				SKSE::log::warn("[NGXNR] CreateFeature FAULTED (code {:#x}) - DLSS-NR disabled this frame", code);
				return false;
			}
			if (r != kNGXSuccess || !h) {
				SKSE::log::warn("[NGXNR] CreateFeature failed {:#x} - DLSS-NR disabled ({}x{})", r, a_width, a_height);
				return false;
			}
			handle = h;
			outWidth = a_width;
			outHeight = a_height;
			featureCreated = true;
			needCreate = false;
			SKSE::log::info("[NGXNR] feature created {}x{} handle={}", a_width, a_height, (void*)h);
		}

		// --- per-frame resources + params (DLSSNR.* keys, v0.8.8) ---
		params->Set("DLSSNR.Color", a_color);
		params->Set("DLSSNR.Depth", a_depth);
		params->Set("DLSSNR.MVec", a_mvec);
		params->Set("DLSSNR.Output", a_output);
		params->Set("DLSSNR.Enabled", 1);
		// v0.8.7：NR 参数读 settings（GUI 滑块/INI 写入处）——原用本对象成员
		// (intensity/style/...) 从未被赋值，滑块无效。Get() = FrameGen 命名空间自由函数。
		auto& s = Get().settings;
		params->Set("DLSSNR.Intensity", s.nrIntensity);
		params->Set("DLSSNR.Style", s.nrStyle);
		params->Set("DLSSNR.LocalToneStrength", s.nrLocalTone);
		params->Set("DLSSNR.SkinStructureStrength", s.nrSkinStructure);
		params->Set("DLSSNR.Reset", 0);
		params->Set("Sharpness", 0.0f);
		params->Set("Jitter.Offset.X", 0.0f);
		params->Set("Jitter.Offset.Y", 0.0f);

		DWORD code = 0;
		unsigned int r = Guarded([&] { return evalFeature(a_cmdList, handle, params, nullptr); }, &code);
		lastEvaluateResult = code ? kNGXExceptionMarker : r;
		lastEvaluateOk = (code == 0 && r == kNGXSuccess);
		if (!lastEvaluateOk) {
			static unsigned int lastLogged = 0;
			if (lastEvaluateResult != lastLogged) {
				lastLogged = lastEvaluateResult;
				SKSE::log::warn("[NGXNR] EvaluateFeature {} {:#x}",
					code ? "faulted" : "failed", code ? code : r);
			}
		}
		return lastEvaluateOk;
	}

	void NGXNR::Shutdown()
	{
		if (ngxModule) {
			if (handle) {
				if (auto release = reinterpret_cast<PFN_NGXReleaseFeature>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_ReleaseFeature"))) {
					DWORD code = 0;
					Guarded([&] { return release(handle); }, &code);
				}
				handle = nullptr;
			}
			if (auto shutdown = reinterpret_cast<unsigned int(__cdecl*)()>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_Shutdown"))) {
				DWORD code = 0;
				Guarded([&] { return shutdown(); }, &code);
				SKSE::log::info("[NGXNR] NGX D3D12 shutdown");
			}
			FreeLibrary(ngxModule);
			ngxModule = nullptr;
		}
		initialized = false;
		featureCreated = false;
		supported = false;
		handle = nullptr;
		params = nullptr;
		device = nullptr;
	}
}  // namespace FrameGen
