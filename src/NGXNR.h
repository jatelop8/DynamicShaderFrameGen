#pragma once
// v0.8: DLSS Neural Radiance (DLSS-NR) via direct NGX calls (renodx-style).
//
// WHY NOT STREAMLINE:
//   - Streamline is a process-global single instance bound to ONE device
//     (slInit + slSetD3DDevice, confirmed in official ProgrammingGuide).
//   - Our existing SL instance is D3D11 (DLSS upscaling, FSR3 mode).
//   - sl.dlss_nr.dll manifest declares rhi = ["d3d12","vk"] (verified by
//     extracting the embedded manifest: id 1004, priority 100) -> SL will
//     never load it on a D3D11 instance.
//   - NGX (NVSDK_NGX_D3D12_Init) is an independent framework - it does NOT
//     go through Streamline, so it coexists with our D3D11 SL instance with
//     zero conflict. renodx-dlss5 uses exactly this approach (it hooks
//     slEvaluateFeature only for NGX/Streamline deduplication).
//
// REQUIREMENTS (runtime files, NOT redistributed):
//   - nvngx_dlss.dll        (NGX core runtime, exports NVSDK_NGX_*)
//   - nvngx_dlssnr.dll      (DLSS-NR feature, 158 MB, sm_120 only = RTX 50xx)
//   User drops these into the mod's Streamline folder. If missing or the GPU
//   has no matching cubin (e.g. RTX 4080 / sm89), feature creation fails and
//   the menu item is greyed out - never a crash.
//
// INTERFACE (reverse-engineered from nvngx_dlssnr.dll strings, verified):
//   feature id 1004 "sl.dlss_nr" (Streamline id; NGX feature enum probed)
//   params: DLSSNR.Color / .MVec / .Depth / .Output (ID3D12Resource*)
//           DLSSNR.Intensity / .Style / .LocalToneStrength /
//           .SkinStructureStrength / .LocalStructureStrength / .Reset / ...
//   NGX parameter object = NGXInstanceParameters (vtable, Set/Get by name)

#include <cstdint>

// HMODULE forward declaration (Windows.h must be included AFTER CommonLib in .cpp)
typedef struct HINSTANCE__* HMODULE;

struct ID3D12Device;
struct ID3D12Resource;
struct ID3D12GraphicsCommandList;

namespace FrameGen
{
	// NGXInstanceParameters vtable (from sl.common.dll / nvngx_dlss.dll),
	// same layout as dlssg-to-fsr3's reverse-engineered header.
	struct NGXInstanceParameters
	{
		virtual void SetVoidPointer(const char* name, void* value) = 0;			   // vtable 0
		virtual void Set2(const char* name, float value) = 0;					   // 8
		virtual void Set3(const char* name, void* unknown) = 0;					   // 10
		virtual void Set4(const char* name, std::uint32_t value) = 0;			   // 18
		virtual void Set5(const char* name, std::uint32_t value) = 0;			   // 20
		virtual void Set6(const char* name, void* unknown) = 0;					   // 28
		virtual void Set7(const char* name, ID3D12Resource* value) = 0;			   // 30
		virtual void Set8(const char* name, void* value) = 0;					   // 38
		virtual std::uint32_t GetVoidPointer(const char* name, void** value) = 0;  // 40
		virtual std::uint32_t Get2(const char* name, float* value) = 0;			   // 48
		virtual std::uint32_t Get3(const char* name, void* value) = 0;			   // 50
		virtual std::uint32_t Get4(const char* name, std::uint32_t* value) = 0;	   // 58
		virtual std::uint32_t Get5(const char* name, std::uint32_t* value) = 0;	   // 60
		virtual std::uint32_t Get6(const char* name, void* unknown) = 0;		   // 68
		virtual std::uint32_t Get7(const char* name, float* value) = 0;			   // 70
		virtual std::uint32_t Get8(const char* name, void* unknown) = 0;		   // 78
		virtual void Unknown() = 0;
	};

	// NGX return codes (NGX_SUCCESS == 0x1, verified in dlssg-to-fsr3)
	inline constexpr std::uint32_t kNGXSuccess = 0x1;
	inline constexpr std::uint32_t kNGXFeatureNotFound = 0xBAD00004;
	inline constexpr std::uint32_t kNGXInvalidParameter = 0xBAD00005;

	// Feature create parameter passed to NVSDK_NGX_D3D12_CreateFeature
	struct NGXFeatureCreateParameter
	{
		std::uint32_t feature;	 // NVSDK_NGX_Feature id (probed)
		std::uint32_t sdkVersion;
		std::uint32_t apiVersion;
	};

	// DLSS-NR via NGX. All NVSDK_NGX_* resolved at runtime from nvngx_dlss.dll.
	class NGXNR
	{
	public:
		bool initialized = false;   // NGX D3D12 initialized
		bool featureCreated = false;
		bool supported = false;	   // feature id probe succeeded (GPU capable)
		std::uint32_t featureId = 0;  // probed NVSDK_NGX_Feature id

		// settings (mirrored by INI/GUI)
		bool enable = true;
		float intensity = 0.5f;
		float style = 0.5f;
		float localToneStrength = 0.0f;
		float skinStructureStrength = 0.0f;

		// Runtime resources (D3D12 side of our shared textures)
		void Init(ID3D12Device* a_device, const wchar_t* a_pluginDir);
		void Shutdown();
		// Probe NVSDK_NGX_Feature id for DLSS-NR by trial (distinguishes
		// "invalid feature" from "architecture not supported")
		std::uint32_t ProbeFeatureId(NGXInstanceParameters* a_params, std::uint32_t a_maxTries = 24);
		// Evaluate one frame. Returns true when the feature ran.
		bool Evaluate(ID3D12Resource* a_color, ID3D12Resource* a_depth, ID3D12Resource* a_mvec,
			ID3D12Resource* a_output, std::uint32_t a_width, std::uint32_t a_height,
			ID3D12GraphicsCommandList* a_cmdList);

		// state for GUI
		bool nvngxPresent = false;	   // nvngx_dlss.dll found
		bool nvngxNrPresent = false;   // nvngx_dlssnr.dll found
		bool lastEvaluateOk = false;
		std::uint32_t lastCreateResult = 0;
		std::uint32_t lastEvaluateResult = 0;

	private:
		ID3D12Device* device = nullptr;
		HMODULE ngxModule = nullptr;
		NGXInstanceParameters* params = nullptr;
		void* handle = nullptr;	 // NVSDK_NGX_Handle*
		std::uint32_t outWidth = 0;
		std::uint32_t outHeight = 0;
	};
}  // namespace FrameGen
