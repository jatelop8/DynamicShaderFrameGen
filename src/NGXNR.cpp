#include "NGXNR.h"

#include <SKSE/SKSE.h>

#include <d3d12.h>
#include <Windows.h>

namespace FrameGen
{
	// ------------------------------------------------------------------
	// NGX function signatures (stable public NGX SDK API, resolved at runtime)
	// ------------------------------------------------------------------
	using PFN_NGX_D3D12_Init = std::uint32_t(__cdecl*)(unsigned long long a_appId,
		const wchar_t* a_dataPath, ID3D12Device* a_device,
		const void* a_featureInfo, std::uint32_t a_sdkVersion);
	using PFN_NGX_D3D12_GetParameters = std::uint32_t(__cdecl*)(NGXInstanceParameters** a_params);
	using PFN_NGX_D3D12_CreateFeature = std::uint32_t(__cdecl*)(const NGXFeatureCreateParameter* a_create,
		const NGXInstanceParameters* a_params, void** a_handle);
	using PFN_NGX_D3D12_UpdateFeature = std::uint32_t(__cdecl*)(void* a_handle,
		const NGXInstanceParameters* a_params, ID3D12GraphicsCommandList* a_cmdList,
		const unsigned long long* a_renderRes, void* a_elapsed);
	using PFN_NGX_D3D12_Shutdown = std::uint32_t(__cdecl*)();

	namespace
	{
		// NGX SDK version as packed by NVSDK_NGX_Version (major<<16 | minor<<8 | patch)
		// matches NGX rel_310_8 (3.10.8) seen in nvngx_dlssnr.dll build path
		constexpr std::uint32_t kNGXSDKVersion = 0x00031008;
		constexpr unsigned long long kAppId = 0x4E525832;  // 'NRX2'

		// Common NGX parameter names (stable across NGX SDK versions)
		constexpr const char* kParamPerfQuality = "PerfQualityValue";
		constexpr const char* kParamWidth = "DLSSNR.Width";
		constexpr const char* kParamHeight = "DLSSNR.Height";
		constexpr const char* kParamHintPreset = "DLSSNR.Hint.Render.Preset";

		// wide -> utf8 helper (avoid CommonLib stl dependency in this TU)
		std::string w2a(const std::wstring& a_w)
		{
			if (a_w.empty())
				return {};
			const int len = WideCharToMultiByte(CP_UTF8, 0, a_w.c_str(), static_cast<int>(a_w.size()), nullptr, 0, nullptr, nullptr);
			std::string s(static_cast<std::size_t>(len), '\0');
			WideCharToMultiByte(CP_UTF8, 0, a_w.c_str(), static_cast<int>(a_w.size()), &s[0], len, nullptr, nullptr);
			return s;
		}
	}  // namespace

	// ------------------------------------------------------------------
	// Init: load nvngx_dlss.dll, resolve exports, init NGX on D3D12 device
	// ------------------------------------------------------------------
	void NGXNR::Init(ID3D12Device* a_device, const wchar_t* a_pluginDir)
	{
		if (initialized || !a_device)
			return;
		device = a_device;

		// 1. locate + load nvngx_dlss.dll (NGX core)
		std::wstring ngxDll = std::wstring(a_pluginDir) + L"\\nvngx_dlss.dll";
		ngxModule = LoadLibraryW(ngxDll.c_str());
		if (!ngxModule) {
			SKSE::log::warn("[NGXNR] nvngx_dlss.dll not found at {} - DLSS-NR disabled (no crash)",
				w2a(ngxDll));
			nvngxPresent = false;
			return;
		}
		nvngxPresent = true;

		auto pInit = reinterpret_cast<PFN_NGX_D3D12_Init>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_Init"));
		auto pGetParams = reinterpret_cast<PFN_NGX_D3D12_GetParameters>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_GetParameters"));
		if (!pInit || !pGetParams) {
			SKSE::log::warn("[NGXNR] nvngx_dlss.dll missing required exports - DLSS-NR disabled");
			return;
		}

		// 2. NVSDK_NGX_D3D12_Init
		const std::uint32_t rc = pInit(kAppId, nullptr, a_device, nullptr, kNGXSDKVersion);
		if (rc != kNGXSuccess) {
			SKSE::log::warn("[NGXNR] NVSDK_NGX_D3D12_Init failed rc={:#x} - DLSS-NR disabled", rc);
			return;
		}
		SKSE::log::info("[NGXNR] NGX D3D12 initialized (appId={:#x}, sdk={:#x})", kAppId, kNGXSDKVersion);

		// 3. parameters object
		if (pGetParams(&params) != kNGXSuccess || !params) {
			SKSE::log::warn("[NGXNR] NVSDK_NGX_D3D12_GetParameters failed - DLSS-NR disabled");
			return;
		}
		initialized = true;

		// 4. check nvngx_dlssnr.dll presence (informational)
		std::wstring nrDll = std::wstring(a_pluginDir) + L"\\nvngx_dlssnr.dll";
		nvngxNrPresent = GetFileAttributesW(nrDll.c_str()) != INVALID_FILE_ATTRIBUTES;
		SKSE::log::info("[NGXNR] nvngx_dlssnr.dll {}",
			nvngxNrPresent ? "present - DLSS-NR feature available" : "NOT present - feature will fail (expected)");

		// 5. probe feature id (works on any GPU: distinguishes enum vs hardware)
		featureId = ProbeFeatureId(params);
		if (featureId == 0) {
			SKSE::log::warn("[NGXNR] DLSS-NR feature probe failed - not supported on this GPU (RTX 4080 has no sm_120 cubin)");
			return;
		}
		supported = true;
		SKSE::log::info("[NGXNR] DLSS-NR feature id {} probed OK - feature ready", featureId);
	}

	// ------------------------------------------------------------------
	// Probe NVSDK_NGX_Feature id for DLSS-NR.
	// Logic: try ids 1..maxTries; a successful CreateFeature returns
	// kNGXSuccess; "feature not found" (0xBAD00004) means wrong id, keep
	// going; any OTHER return means the id was accepted but hardware/
	// parameters failed -> remember as candidate (still proves the id).
	// ------------------------------------------------------------------
	std::uint32_t NGXNR::ProbeFeatureId(NGXInstanceParameters* a_params, std::uint32_t a_maxTries)
	{
		if (!a_params)
			return 0;

		auto pCreate = reinterpret_cast<PFN_NGX_D3D12_CreateFeature>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_CreateFeature"));
		if (!pCreate)
			return 0;

		std::uint32_t candidate = 0;
		std::uint32_t candidateRc = 0;
		for (std::uint32_t id = 1; id <= a_maxTries; ++id) {
			// minimal create parameters: width/height + perf quality
			a_params->Set4(kParamWidth, 3840);
			a_params->Set4(kParamHeight, 2160);
			a_params->Set5(kParamPerfQuality, 1);	 // ePerfQualityHigh? value unimportant for probe
			a_params->Set5(kParamHintPreset, 0);

			NGXFeatureCreateParameter create{};
			create.feature = id;
			create.sdkVersion = kNGXSDKVersion;
			create.apiVersion = 0;

			void* h = nullptr;
			const std::uint32_t rc = pCreate(&create, a_params, &h);
			if (rc == kNGXSuccess) {
				SKSE::log::info("[NGXNR] probe: feature id {} -> SUCCESS", id);
				if (h)
					handle = h;	 // keep the created feature (50-series path)
				return id;
			}
			if (rc == kNGXFeatureNotFound) {
				continue;  // wrong id
			}
			// other error: id plausibly correct but hardware/params rejected
			if (!candidate) {
				candidate = id;
				candidateRc = rc;
			}
			SKSE::log::info("[NGXNR] probe: feature id {} -> rc={:#x} ({})", id, rc,
				rc == kNGXFeatureNotFound ? "not found" : "accepted-but-failed");
			// keep probing a few more to catch late-listed ids
		}
		if (candidate) {
			SKSE::log::info("[NGXNR] probe candidate: feature id {} rc={:#x} (hardware/param rejected)", candidate, candidateRc);
			return candidate;
		}
		return 0;
	}

	// ------------------------------------------------------------------
	// Evaluate: bind resources + params, run NVSDK_NGX_D3D12_UpdateFeature
	// ------------------------------------------------------------------
	bool NGXNR::Evaluate(ID3D12Resource* a_color, ID3D12Resource* a_depth, ID3D12Resource* a_mvec,
		ID3D12Resource* a_output, std::uint32_t a_width, std::uint32_t a_height,
		ID3D12GraphicsCommandList* a_cmdList)
	{
		lastEvaluateOk = false;
		if (!initialized || !featureId || !handle || !params || !a_color || !a_output)
			return false;

		auto pUpdate = reinterpret_cast<PFN_NGX_D3D12_UpdateFeature>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_UpdateFeature"));
		if (!pUpdate)
			return false;

		// recreate feature on resolution change (NGX requires matching dims)
		if (a_width != outWidth || a_height != outHeight) {
			auto pCreate = reinterpret_cast<PFN_NGX_D3D12_CreateFeature>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_CreateFeature"));
			if (pCreate) {
				if (handle) {
					// release old feature (best-effort; NGX may reuse handle)
					handle = nullptr;
				}
				params->Set4(kParamWidth, a_width);
				params->Set4(kParamHeight, a_height);
				params->Set5(kParamPerfQuality, 1);
				NGXFeatureCreateParameter create{};
				create.feature = featureId;
				create.sdkVersion = kNGXSDKVersion;
				create.apiVersion = 0;
				void* h = nullptr;
				const std::uint32_t rc = pCreate(&create, params, &h);
				lastCreateResult = rc;
				if (rc == kNGXSuccess && h) {
					handle = h;
					outWidth = a_width;
					outHeight = a_height;
					SKSE::log::info("[NGXNR] feature (re)created {}x{} rc={:#x}", a_width, a_height, rc);
				} else {
					SKSE::log::warn("[NGXNR] feature recreate failed {}x{} rc={:#x}", a_width, a_height, rc);
					return false;
				}
			}
		}

		// bind resources (vtable slots: Set7 = resource, Set2 = float, Set4/5 = uint)
		params->Set7("DLSSNR.Color", a_color);
		params->Set7("DLSSNR.MVec", a_mvec);
		params->Set7("DLSSNR.Depth", a_depth);
		params->Set7("DLSSNR.Output", a_output);
		params->Set2("DLSSNR.Intensity", intensity);
		params->Set2("DLSSNR.Style", style);
		params->Set2("DLSSNR.LocalToneStrength", localToneStrength);
		params->Set2("DLSSNR.SkinStructureStrength", skinStructureStrength);
		params->Set4("DLSSNR.Reset", 0);

		const unsigned long long res[2] = { a_width, a_height };
		const std::uint32_t rc = pUpdate(handle, params, a_cmdList, res, nullptr);
		lastEvaluateResult = rc;
		lastEvaluateOk = (rc == kNGXSuccess);
		if (!lastEvaluateOk && (lastEvaluateResult & 0xFFFF0000) != 0xBAD00000) {
			// log only once per unique error to avoid spam
			static std::uint32_t lastLogged = 0;
			if (lastEvaluateResult != lastLogged) {
				lastLogged = lastEvaluateResult;
				SKSE::log::warn("[NGXNR] UpdateFeature rc={:#x}", rc);
			}
		}
		return lastEvaluateOk;
	}

	void NGXNR::Shutdown()
	{
		if (ngxModule) {
			if (auto pShutdown = reinterpret_cast<PFN_NGX_D3D12_Shutdown>(GetProcAddress(ngxModule, "NVSDK_NGX_D3D12_Shutdown"))) {
				const std::uint32_t rc = pShutdown();
				SKSE::log::info("[NGXNR] NGX D3D12 shutdown rc={:#x}", rc);
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
