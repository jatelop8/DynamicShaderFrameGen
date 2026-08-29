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
	using PFN_NGXAllocParams = unsigned int(__cdecl*)(NGXInstanceParameters** a_params);
	using PFN_NGXCreateFeature = unsigned int(__cdecl*)(ID3D12GraphicsCommandList* a_cmdList,
		int a_featureId, NGXInstanceParameters* a_params, NGXHandle** a_handle);
	using PFN_NGXEvaluateFeature = unsigned int(__cdecl*)(ID3D12GraphicsCommandList* a_cmdList,
		const NGXHandle* a_handle, const NGXInstanceParameters* a_params, void* a_callback);
	using PFN_NGXReleaseFeature = unsigned int(__cdecl*)(NGXHandle* a_handle);
	using PFN_NGXGetCaps = unsigned int(__cdecl*)(NGXInstanceParameters** a_caps);
	// v0.8.11: NVSDK_NGX_D3D11_Init on nvngx_dlss.dll — disassembly (rva 0x2b420)
	// shows a 3-arg real impl: checks arg3 (r8) != null, writes qword 0 to *r8,
	// returns 1 (kNGXSuccess). SkyrimUpscaler log proves this call establishes
	// the NGX core session (Init -> GetCapabilityParameters -> CREATE_DLSS_EXT all
	// succeed afterwards on the same nvngx_dlss.dll).
	using PFN_NGXInit11 = unsigned int(__cdecl*)(unsigned long long a_appId,
		const wchar_t* a_dataPath, void* a_param);

	// v0.8.12：NVSDK_NGX_FeatureCommonInfo（Init_Ext/CreateFeature 的第 5 参）。
	// dlss5-dx11-bridge 传 nullptr 在 BG3 成功（BG3 有 SL core）；Skyrim 无 core，
	// Init_Ext 全部 0xbad00002——试非空 FeatureCommonInfo 排除参数缺失因素。
	struct NGXFeatureCommonInfo
	{
		std::uint32_t instanceId = 0;
		std::uint32_t creationNodeMask = 1;
		std::uint32_t visibilityNodeMask = 1;
		std::uint32_t reserved[1] = {};
		void* userData = nullptr;
	};

	namespace
	{
		constexpr unsigned long long kAppId = 0x1000000ULL;
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

		// ------------------------------------------------------------------
		// v0.8.11 重大修正（v0.8.10 方向反了）：
		//   v0.8.10 只加载 nvngx_dlssnr.dll（NR snippet）→ CreateFeature 每帧
		//   0xbad00002 = "找不到已初始化 NGX core 实例"——snippet 需要 core 会话，
		//   而进程里从未加载过 core 宿主。
		//   SkyrimUpscaler.log 实锤链路（同款 nvngx_dlss.dll，md5 f9add387）：
		//     NVSDK_NGX_D3D11_Init = 1 Success
		//     NVSDK_NGX_D3D11_GetCapabilityParameters = 1 Success
		//     NGX_D3D11_CREATE_DLSS_EXT = 1 Success
		//   → nvngx_dlss.dll 自举 NGX core（Init 3 参真实现 + CreateFeature 自举），
		//     dlssnr 只是外围 snippet。正确顺序：先 dlss.dll 建 core，再 dlssnr 跑 NR。
		// ------------------------------------------------------------------

		// --- 1) 加载 NGX core 宿主 nvngx_dlss.dll ---
		std::wstring corePath = std::wstring(a_pluginDir) + L"\\nvngx_dlss.dll";
		coreModule = LoadLibraryW(corePath.c_str());
		if (!coreModule) {
			SKSE::log::warn("[NGXNR] nvngx_dlss.dll NOT found under {} - no NGX core host (CreateFeature will fail 0xbad00002)", w2a(a_pluginDir));
		} else {
			SKSE::log::info("[NGXNR] NGX core host nvngx_dlss.dll loaded");
		}

		// --- 2) 加载 NR snippet nvngx_dlssnr.dll（CreateFeature/Evaluate 的执行者）---
		std::wstring nrPath = std::wstring(a_pluginDir) + L"\\nvngx_dlssnr.dll";
		ngxModule = LoadLibraryW(nrPath.c_str());
		if (!ngxModule) {
			SKSE::log::warn("[NGXNR] nvngx_dlssnr.dll NOT found under {} - DLSS-NR disabled (no crash)", w2a(a_pluginDir));
			nvngxPresent = false;
			return;
		}
		nvngxPresent = true;
		wchar_t resolved[MAX_PATH] = {};
		GetModuleFileNameW(ngxModule, resolved, MAX_PATH);
		SKSE::log::info("[NGXNR] loaded {} (resolved: {})", w2a(nrPath), w2a(resolved));

		// --- 3) 建立 NGX core 会话（用 nvngx_dlss.dll）---
		auto initExt12 = coreModule ? reinterpret_cast<PFN_NGXInitExt>(GetProcAddress(coreModule, "NVSDK_NGX_D3D12_Init_Ext")) : nullptr;
		auto init11 = coreModule ? reinterpret_cast<PFN_NGXInit11>(GetProcAddress(coreModule, "NVSDK_NGX_D3D11_Init")) : nullptr;
		// snippet 侧导出（仅记录；Init 是 stub 0xbad00001，Init_Ext 需 core——v0.8.10 已证）
		auto nrInitExt = reinterpret_cast<PFN_NGXInitExt>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_Init_Ext"));
		auto nrInit = reinterpret_cast<PFN_NGXInit>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_Init"));
		SKSE::log::info("[NGXNR] entry: core[dlss]: Init_Ext={} D3D11_Init={} | nr[dlssnr]: Init_Ext={} Init={}",
			(void*)initExt12, (void*)init11, (void*)nrInitExt, (void*)nrInit);

		// data path = directory of the game exe (NGX writes its logs there)
		wchar_t dataPath[MAX_PATH] = {};
		GetModuleFileNameW(nullptr, dataPath, MAX_PATH);
		if (wchar_t* s = wcsrchr(dataPath, L'\\'))
			*(s + 1) = L'\0';

		DWORD code = 0;
		NGXFeatureCommonInfo fci{};  // v0.8.12：非空 FeatureCommonInfo（排除参数缺失）
		// 3a) 首选：dlss.dll 的 D3D12_Init_Ext（真实实现，带 D3D12 device）版本协商
		if (coreModule && initExt12) {
			for (int ver = 0x13; ver <= 0x16 && !coreInitOk; ++ver) {
				unsigned int r = Guarded([&] { return initExt12(kAppId, dataPath, a_device, ver, &fci); }, &code);
				SKSE::log::info("[NGXNR] core D3D12_Init_Ext(0x{:02X}) -> {} (rc={:#x})", ver,
					code ? "faulted" : (r == kNGXSuccess ? "ok" : "refused"), code ? code : r);
				if (code == 0 && r == kNGXSuccess) {
					initialized = true;
					initVersion = ver;
					coreInitOk = true;
					coreInitResult = r;
				}
			}
		}
		// 3b) 备选：dlss.dll 的 D3D11_Init（3 参。反汇编 0x2B440 = stub 0xBAD00001——
		// v0.8.12 修正：先前把 0x2B420（GetScratchBufferSize）误认为 D3D11_Init）
		if (!coreInitOk && init11) {
			void* dummy = nullptr;
			unsigned int r = Guarded([&] { return init11(kAppId, dataPath, &dummy); }, &code);
			SKSE::log::info("[NGXNR] core D3D11_Init -> {} (rc={:#x})", code ? "faulted" : (r == kNGXSuccess ? "ok" : "refused"), code ? code : r);
			if (code == 0 && r == kNGXSuccess) {
				coreInitOk = true;
				coreInitResult = r;
				SKSE::log::info("[NGXNR] NGX core session established via D3D11_Init (SkyrimUpscaler pattern)");
			}
		}
		// 3c) 记录：snippet 侧 Init_Ext（预期 0xbad00002；v0.8.12 传非空 FeatureCommonInfo）
		if (nrInitExt && !initialized) {
			unsigned int r = Guarded([&] { return nrInitExt(kAppId, dataPath, a_device, 0x13, &fci); }, &code);
			SKSE::log::info("[NGXNR] nr Init_Ext(0x13) -> {} (rc={:#x})", code ? "faulted" : (r == kNGXSuccess ? "ok" : "refused"), code ? code : r);
		}
		if (!coreInitOk)
			SKSE::log::warn("[NGXNR] no NGX core session (rc={:#x}) - will try dlss.dll warmup CreateFeature on first evaluate frame", coreInitResult);
		else
			SKSE::log::info("[NGXNR] NGX core session ready (rc={:#x})", coreInitResult);

		// nvngx_dlssnr.dll presence (informational)
		nvngxNrPresent = GetFileAttributesW(nrPath.c_str()) != INVALID_FILE_ATTRIBUTES;
		SKSE::log::info("[NGXNR] nvngx_dlssnr.dll {}", nvngxNrPresent ? "present" : "NOT present (expected -> feature unavailable)");

		// v0.8.10：无 GetCapabilityParameters（snippet 不导出）——supported 由
		// CreateFeature 试错决定（Evaluate 首帧）。core 宿主 + snippet 都加载成功即 ready。
		ready = coreModule != nullptr;
		needCreate = true;
		SKSE::log::info("[NGXNR] DLSS-NR armed (feature created on first evaluate frame; core={})", coreInitOk ? "ok" : "MISSING");
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
			// --- v0.8.12：core 未建立 → 先用 dlss.dll 的 CreateFeature 热身 ---
			// Init 全是 stub（D3D11/D3D12_Init @0x2b440 = 0xBAD00001）、Init_Ext 全
			// 0xbad00002——CreateFeature 才是自举入口（SkyrimUpscaler 同款：Init 占位
			// + CreateFeature 成功）。dlssnr 的 CreateFeature 需要 dlss.dll 建立的
			// NGX core 单例；先让 dlss.dll 建一次（随后立即释放），dlssnr 就能找到。
			// v0.8.14：热身只试一次（warmupTried）；先调 GetScratchBufferSize 诊断——
			// CreateFeature 内部第一步就是它（不碰 cmdList），同样返回 0xbad00005
			// 即实锤 "core 未初始化"，而非 vtable/参数问题。
			if (!coreInitOk && coreModule && !warmupTried) {
				warmupTried = true;
				auto warmupCreate = reinterpret_cast<PFN_NGXCreateFeature>(GetProcAddress(coreModule, "NVSDK_NGX_D3D12_CreateFeature"));
				auto warmupRelease = reinterpret_cast<PFN_NGXReleaseFeature>(GetProcAddress(coreModule, "NVSDK_NGX_D3D12_ReleaseFeature"));
				auto scratchSize = reinterpret_cast<unsigned int(__cdecl*)(int, NGXInstanceParameters*, unsigned long long*)>(
					GetProcAddress(coreModule, "NVSDK_NGX_D3D12_GetScratchBufferSize"));
				OwnNGXParams wp;
				wp.Set4("DLSS.Mode", 0);
				wp.Set4("DLSS.Input.Width", a_width);
				wp.Set4("DLSS.Input.Height", a_height);
				wp.Set4("DLSS.Output.Width", a_width);
				wp.Set4("DLSS.Output.Height", a_height);
				wp.Set4("DLSS.Enable.Output.Subrects", 1);
				wp.Set4("DLSS.PerfQualityValue", 1);
				wp.Set4("DLSS.DepthInverted", 0);
				wp.Set4("DLSS.Hint.Render.Preset", 0);
				wp.Set4("CreationNodeMask", 1u);
				wp.Set4("VisibilityNodeMask", 1u);

				// 诊断：GetScratchBufferSize —— CreateFeature 的前置，不碰 cmdList
				if (scratchSize) {
					unsigned long long sbSize = 0;
					DWORD scode = 0;
					unsigned int sr = Guarded([&] { return scratchSize(1, &wp, &sbSize); }, &scode);
					scratchSizeResult = scode ? kNGXExceptionMarker : sr;
					SKSE::log::info("[NGXNR] GetScratchBufferSize(1) -> {} (rc={:#x} size={})",
						scode ? "faulted" : (sr == kNGXSuccess ? "ok" : "failed"), scode ? scode : sr, sbSize);
				}

				if (warmupCreate) {
					NGXHandle* wh = nullptr;
					DWORD wcode = 0;
					unsigned int wr = Guarded([&] { return warmupCreate(a_cmdList, 1, &wp, &wh); }, &wcode);
					warmupResult = wcode ? kNGXExceptionMarker : wr;
					if (wcode == 0 && wr == kNGXSuccess && wh) {
						coreInitOk = true;
						coreInitResult = wr;
						SKSE::log::info("[NGXNR] dlss.dll warmup CreateFeature OK - NGX core established (handle={})", (void*)wh);
						if (warmupRelease) {
							DWORD rcode = 0;
							Guarded([&] { return warmupRelease(wh); }, &rcode);
						}
					} else {
						SKSE::log::warn("[NGXNR] dlss.dll warmup CreateFeature failed {:#x} (fault={:#x}) - core NOT established", wr, wcode);
					}
				}
			}

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
			params.Set4("DLSS.Mode", 0);
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
				// v0.8.14：节流（首次 + 每 180 帧），避免每帧刷屏
				static unsigned int lastLogged = 0;
				static unsigned int frameCount = 0;
				if (++frameCount % 180 == 1 || r != lastLogged) {
					lastLogged = r;
					SKSE::log::warn("[NGXNR] CreateFeature failed {:#x} - DLSS-NR disabled ({}x{} core={})", r, a_width, a_height,
						coreInitOk ? "ok" : "MISSING");
				}
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
		if (coreModule) {
			// v0.8.11：core 宿主（nvngx_dlss.dll）——NGX Shutdown 用 snippet 侧已调，
			// 这里只卸载模块。进程退出期，泄漏可接受；显式卸载避免重复 Shutdown。
			FreeLibrary(coreModule);
			coreModule = nullptr;
		}
		initialized = false;
		featureCreated = false;
		supported = false;
		ready = false;
		coreInitOk = false;
		handle = nullptr;
		device = nullptr;
	}
}  // namespace FrameGen
