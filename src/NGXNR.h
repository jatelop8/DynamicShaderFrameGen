#pragma once
// v0.8.1: DLSS Neural Radiance (DLSS-NR) via direct NGX calls.
//
// Interface verified against NIGos/dlss5-dx11-bridge (MIT) — the NGX entry
// points are undocumented; that project recovered the real signatures from
// disassembly and proved them on multiple engines (BG3 / Fallout 4 / Unity).
// Three corrections vs v0.8:
//   1. NVSDK_NGX_D3D12_CreateFeature(cmdList, feature_id, params, &handle)
//      — feature_id is a plain int, hardcoded 1 (SuperSampling). DLSS-NR is
//      NOT a separate feature: it is SuperSampling + DLSSNR.* params.
//   2. Per-frame call is NVSDK_NGX_D3D12_EvaluateFeature, not UpdateFeature.
//   3. Init must NEGOTIATE the SDK version (0x13..0x16) across
//      NVSDK_NGX_D3D12_Init_Ext / _Init_ProjectID; a hardcoded constant
//      faults the whole D3D12 session on other drivers.
//   4. GPU capability gate: GetCapabilityParameters ->
//      "SuperSamplingDenoising.Available" (0 on RTX 40 = no sm_120 kernel).
//
// Architecture: NGX is independent of Streamline (which is single-instance
// per process bound to one device — ours is D3D11 for DLSS upscaling). We
// init NGX on our own D3D12 device via shared textures, zero conflict.
//
// Runtime files (NOT redistributed): nvngx_dlss.dll + nvngx_dlssnr.dll
// dropped into the mod's Streamline folder by the user.

#include <cstdint>

// HMODULE forward declaration (Windows.h must be included AFTER CommonLib in .cpp)
typedef struct HINSTANCE__* HMODULE;

struct ID3D12Device;
struct ID3D12Resource;
struct ID3D11Resource;
struct ID3D12GraphicsCommandList;

namespace FrameGen
{
	// NGXInstanceParameters vtable (from dlssg-to-fsr3 + dlss5-dx11-bridge,
	// same layout, slot order verified by both projects):
	//   Set: 0=u64 1=float 2=double 3=uint 4=int 5=ID3D11Resource* 6=ID3D12Resource* 7=void*
	//   Get: 0=u64 1=float 2=double 3=uint 4=int 5=ID3D11Resource* 6=float 7=void*  (+Unknown)
	struct NGXInstanceParameters
	{
		virtual void Set(const char* name, unsigned long long value) = 0;	 // 0
		virtual void Set(const char* name, float value) = 0;				 // 1
		virtual void Set(const char* name, double value) = 0;				 // 2
		virtual void Set(const char* name, unsigned int value) = 0;		 // 3
		virtual void Set(const char* name, int value) = 0;					 // 4
		virtual void Set(const char* name, ID3D11Resource* value) = 0;		 // 5
		virtual void Set(const char* name, ID3D12Resource* value) = 0;		 // 6
		virtual void Set(const char* name, void* value) = 0;				 // 7
		virtual unsigned int Get0(const char* name, unsigned long long* value) const = 0;	 // 8
		virtual unsigned int Get1(const char* name, float* value) const = 0;				 // 9
		virtual unsigned int Get2(const char* name, void* value) const = 0;				 // 10
		virtual unsigned int Get3(const char* name, unsigned int* value) const = 0;		 // 11
		virtual unsigned int Get4(const char* name, int* value) const = 0;					 // 12
		virtual unsigned int Get5(const char* name, ID3D11Resource** value) const = 0;		 // 13
		virtual unsigned int Get6(const char* name, float* value) const = 0;				 // 14
		virtual unsigned int Get7(const char* name, void** value) const = 0;				 // 15
		virtual void Unknown() = 0;
	};

	struct NGXHandle
	{
		unsigned int id = 0;
	};

	// NGX return codes
	inline constexpr unsigned int kNGXSuccess = 0x1;

	class NGXNR
	{
	public:
		bool initialized = false;   // NGX D3D12 session initialised
		bool featureCreated = false;
		bool supported = false;     // SuperSamplingDenoising.Available == 1 (RTX 50 only)

		// settings (mirrored by INI/GUI)
		bool enable = true;
		float intensity = 0.5f;
		float style = 0.5f;
		float localToneStrength = 0.0f;
		float skinStructureStrength = 0.0f;

		void Init(ID3D12Device* a_device, const wchar_t* a_pluginDir);
		void Shutdown();
		// Per-frame: bind resources + params, run NVSDK_NGX_D3D12_EvaluateFeature.
		// a_cmdList must be an OPEN direct command list (recorded, executed later).
		// Returns true when the feature ran successfully.
		bool Evaluate(ID3D12Resource* a_color, ID3D12Resource* a_depth, ID3D12Resource* a_mvec,
			ID3D12Resource* a_output, unsigned int a_width, unsigned int a_height,
			ID3D12GraphicsCommandList* a_cmdList);

		// state for GUI/log
		bool nvngxPresent = false;
		bool nvngxNrPresent = false;
		bool lastEvaluateOk = false;
		unsigned int lastCreateResult = 0;
		unsigned int lastEvaluateResult = 0;
		int initVersion = 0;   // negotiated SDK version (0x13..0x16)

	private:
		ID3D12Device* device = nullptr;
		HMODULE ngxModule = nullptr;
		NGXInstanceParameters* params = nullptr;
		NGXHandle* handle = nullptr;
		unsigned int outWidth = 0;
		unsigned int outHeight = 0;
		bool needCreate = true;
	};
}  // namespace FrameGen
