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
	// Init: load the DLSS-NR snippet, negotiate NGX SDK version (informational)
	// ------------------------------------------------------------------
	// v0.8.10 重大修正：
	//  - 导出表解析 bug 修正后（NameOrdinals 是 0-based index，不需减 base）：
	//    Init_Ext @ 0x15df0 是**真实实现**（内部检查失败 -> 0xbad00002 =
	//    "找不到已初始化实例"——snippet 需要 NGX core 会话，Skyrim 无 core），
	//    Init @ 0x13f50 是 stub（0xbad00001）。
	//  - nvngx_dlssnr.dll 不导出 AllocateParameters/GetCapabilityParameters
	//    （snippet 由 NGX core 提供这些）-> 自实现 OwnNGXParams 替代。
	//  - **Init 失败不阻塞**：SkyrimUpscaler 的 D3D11 也如此（Init stub 返回 1
	//    占位，CreateFeature 才是真初始化）——D3D12 同理：直接 CreateFeature
	//    试错，成功 = 支持（4080 + Ada 补丁 cubin sm_89 应成功）。
	void NGXNR::Init(ID3D12Device* a_device, const wchar_t* a_pluginDir)
	{
		SKSE::log::info("[NGXNR] Init called: device={} initialized={} dir={}", (void*)a_device, initialized,
			a_pluginDir ? w2a(a_pluginDir) : "(null)");
		if (ready || !a_device)
			return;
		device = a_device;

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
		SKSE::log::info("[NGXNR] entry: Init_Ext={} Init={} Init_ProjectID={}",
			(void*)initExt, (void*)init, (void*)initProject);

		// data path = directory of the game exe (NGX writes its logs there)
		wchar_t dataPath[MAX_PATH] = {};
		GetModuleFileNameW(nullptr, dataPath, MAX_PATH);
		if (wchar_t* s = wcsrchr(dataPath, L'\\'))
			*(s + 1) = L'\0';

		DWORD code = 0;
		for (int ver = 0x13; ver <= 0x16; ++ver) {
			if (initExt) {
				unsigned int r = Guarded([&] { return initExt(kAppId, dataPath, a_device, ver, nullptr); }, &code);
				SKSE::log::info("[NGXNR] Init_Ext(0x{:02X}) -> {} (rc={:#x})", ver,
					code ? "faulted" : (r == kNGXSuccess ? "ok" : "refused"), code ? code : r);
				if (code == 0 && r == kNGXSuccess) { initialized = true; initVersion = ver; break; }
			}
			if (init) {
				void* outHandle = nullptr;
				unsigned int r = Guarded([&] { return init(kAppId, dataPath, &outHandle, ver, nullptr); }, &code);
				SKSE::log::info("[NGXNR] Init(0x{:02X}) -> {} (rc={:#x} outHandle={})", ver,
					code ? "faulted" : (r == kNGXSuccess ? "ok" : "refused"), code ? code : r, outHandle);
				if (code == 0 && r == kNGXSuccess) { initialized = true; initVersion = ver; break; }
			}
			if (initProject) {
				unsigned int r = Guarded([&] { return initProject(kProjectId, 0, "1.0", dataPath, a_device, ver, nullptr); }, &code);
				SKSE::log::info("[NGXNR] Init_ProjectID(0x{:02X}) -> {} (rc={:#x})", ver,
					code ? "faulted" : (r == kNGXSuccess ? "ok" : "refused"), code ? code : r);
				if (code == 0 && r == kNGXSuccess) { initialized = true; initVersion = ver; break; }
			}
		}
		if (!initialized)
			SKSE::log::warn("[NGXNR] all NGX D3D12 init flavours refused (expected without NGX core) - trying CreateFeature directly");

		// nvngx_dlssnr.dll presence (informational)
		std::wstring nrDll = std::wstring(a_pluginDir) + L"\\nvngx_dlssnr.dll";
		nvngxNrPresent = GetFileAttributesW(nrDll.c_str()) != INVALID_FILE_ATTRIBUTES;
		SKSE::log::info("[NGXNR] nvngx_dlssnr.dll {}",
			nvngxNrPresent ? "present" : "NOT present (expected -> feature unavailable)");

		// v0.8.10：无 GetCapabilityParameters（snippet 不导出）——supported 由
		// CreateFeature 试错决定（Evaluate 首帧）。DLL 加载成功即 ready。
		ready = true;
		needCreate = true;
		SKSE::log::info("[NGXNR] DLSS-NR armed (feature created on first evaluate frame)");
	}

	// ------------------------------------------------------------------
	// Evaluate: (re)create feature on demand, bind resources, evaluate
	// ------------------------------------------------------------------
	bool NGXNR::Evaluate(ID3D12Resource* a_color, ID3D12Resource* a_depth, ID3D12Resource* a_mvec,
		ID3D12Resource* a_output, unsigned int a_width, unsigned int a_height,
		ID3D12GraphicsCommandList* a_cmdList)
	{
		lastEvaluateOk = false;
		if (!ready || !a_color || !a_output || !a_cmdList)
			return false;

		auto createFeature = reinterpret_cast<PFN_NGXCreateFeature>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_CreateFeature"));
		auto evalFeature = reinterpret_cast<PFN_NGXEvaluateFeature>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_EvaluateFeature"));
		if (!createFeature || !evalFeature)
			return false;

		// --- (re)create on first frame / size change ---
		// v0.8.8：DLSS-NR 参数键全部用 DLSSNR.* 前缀（nvngx_dlssnr.dll 字符串表
		// + renodx addon 反编译双源实锤）。v0.8.10：OwnNGXParams 方法名（Set4=uint32、
		// Set2=float、Set7=ID3D12Resource*——dlssg-to-fsr3 vtable 布局）。
		if (needCreate || a_width != outWidth || a_height != outHeight) {
			params.Set4("DLSSNR.Width", a_width);
			params.Set4("DLSSNR.Height", a_height);
			params.Set4("DLSSNR.InputWidth", a_width);
			params.Set4("DLSSNR.InputHeight", a_height);
			params.Set4("DLSSNR.OutputWidth", a_width);
			params.Set4("DLSSNR.OutputHeight", a_height);
			params.Set2("DLSSNR.ScalingRatio", 1.0f);		  // DLAA 模式（4K→4K 滤镜）
			params.Set4("DLSSNR.Enabled", 1);
			params.Set4("DLSSNR.DepthInverted", 0);			  // Skyrim depth: 近=0 远=1
			params.Set4("DLSSNR.Hint.Render.Preset", 0);	  // 0=Auto (renodx: Preset #1/#2/#3)
			params.Set4("DLSSNR.Reset", 1);					  // 创建时重置内部状态
			params.Set4("PerfQualityValue", 2);				  // balanced-ish
			params.Set4("DLSS.Feature.Create.Flags", 107);
			params.Set4("DLSS.Enable.Output.Subrects", 1);
			params.Set4("CreationNodeMask", 1u);
			params.Set4("VisibilityNodeMask", 1u);
			params.Set4("RTXValue", 0);

			DWORD code = 0;
			NGXHandle* h = nullptr;
			unsigned int r = Guarded([&] { return createFeature(a_cmdList, kFeatureSuperSampling, &params, &h); }, &code);
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
			supported = true;   // v0.8.10：CreateFeature 成功 = 硬件/驱动支持（替代 Caps 查询）
			needCreate = false;
			SKSE::log::info("[NGXNR] feature created {}x{} handle={}", a_width, a_height, (void*)h);
		}

		// --- per-frame resources + params (DLSSNR.* keys) ---
		params.Set7("DLSSNR.Color", a_color);
		params.Set7("DLSSNR.Depth", a_depth);
		params.Set7("DLSSNR.MVec", a_mvec);
		params.Set7("DLSSNR.Output", a_output);
		params.Set4("DLSSNR.Enabled", 1);
		// v0.8.9：MV 缩放（Skyrim 引擎 mvec 语义 = 我们 DLSS 超分的 mvecScale 1.0）
		params.Set2("DLSSNR.MVecScaleX", 1.0f);
		params.Set2("DLSSNR.MVecScaleY", 1.0f);
		// v0.8.7：NR 参数读 settings（GUI 滑块/INI 写入处）
		auto& s = Get().settings;
		params.Set2("DLSSNR.Intensity", s.nrIntensity);
		params.Set2("DLSSNR.Style", s.nrStyle);
		params.Set2("DLSSNR.LocalToneStrength", s.nrLocalTone);
		params.Set2("DLSSNR.SkinStructureStrength", s.nrSkinStructure);
		params.Set4("DLSSNR.Reset", 0);
		params.Set2("Sharpness", 0.0f);
		params.Set2("Jitter.Offset.X", 0.0f);
		params.Set2("Jitter.Offset.Y", 0.0f);

		DWORD code = 0;
		unsigned int r = Guarded([&] { return evalFeature(a_cmdList, handle, &params, nullptr); }, &code);
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
		ready = false;
		handle = nullptr;
		device = nullptr;
	}
}  // namespace FrameGen
