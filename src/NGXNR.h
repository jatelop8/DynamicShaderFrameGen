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
#include <string>
#include <unordered_map>

// HMODULE forward declaration (Windows.h must be included AFTER CommonLib in .cpp)
typedef struct HINSTANCE__* HMODULE;

struct ID3D12Device;
struct ID3D12Resource;
struct ID3D11Resource;
struct ID3D12GraphicsCommandList;

namespace FrameGen
{
	// NGX return codes
	inline constexpr unsigned int kNGXSuccess = 0x1;

	// NGXInstanceParameters vtable — v0.8.10 改用 dlssg-to-fsr3 实战验证布局
	// （Nukem9，劫持整个 NGX 层，槽位经多引擎验证）：
	//   Set: 0=void* 1=float 2=void* 3=uint32 4=uint32 5=void* 6=ID3D12Resource* 7=void*
	//   Get: 0=void** 1=float* 2=void* 3=uint32* 4=uint32* 5=void* 6=float* 7=void*
	// 我们自实现该接口（存 map），NGX CreateFeature/EvaluateFeature 内部通过
	// Get 读参数——不依赖 AllocateParameters（nvngx_dlssnr.dll 不导出）。
	struct NGXInstanceParameters
	{
		virtual void SetVoidPointer(const char* name, void* value) = 0;			 // 0
		virtual void Set2(const char* name, float value) = 0;					 // 1
		virtual void Set3(const char* name, void* value) = 0;					 // 2
		virtual void Set4(const char* name, std::uint32_t value) = 0;			 // 3
		virtual void Set5(const char* name, std::uint32_t value) = 0;			 // 4
		virtual void Set6(const char* name, void* value) = 0;					 // 5
		virtual void Set7(const char* name, ID3D12Resource* value) = 0;			 // 6
		virtual void Set8(const char* name, void* value) = 0;					 // 7
		virtual std::uint32_t GetVoidPointer(const char* name, void** value) = 0; // 8
		virtual std::uint32_t Get2(const char* name, float* value) = 0;			 // 9
		virtual std::uint32_t Get3(const char* name, void* value) = 0;			 // 10
		virtual std::uint32_t Get4(const char* name, std::uint32_t* value) = 0;	 // 11
		virtual std::uint32_t Get5(const char* name, std::uint32_t* value) = 0;	 // 12
		virtual std::uint32_t Get6(const char* name, void* value) = 0;			 // 13
		virtual std::uint32_t Get7(const char* name, float* value) = 0;			 // 14
		virtual std::uint32_t Get8(const char* name, void* value) = 0;			 // 15
	};

	// v0.8.10：自实现参数对象（dlssg-to-fsr3 同款思路——Set 存 map，Get 读 map）。
	// 传给真实 NGX CreateFeature/EvaluateFeature，NGX 内部用 Get 读 Width/Height/
	// DLSSNR.* 等；不依赖 AllocateParameters（snippet DLL 不导出）。
	class OwnNGXParams : public NGXInstanceParameters
	{
	public:
		void SetVoidPointer(const char* name, void* value) override { voids_[name] = value; }
		void Set2(const char* name, float value) override { floats_[name] = value; }
		void Set3(const char* name, void* value) override { voids_[name] = value; }
		void Set4(const char* name, std::uint32_t value) override { uints_[name] = value; }
		void Set5(const char* name, std::uint32_t value) override { uints_[name] = value; }
		void Set6(const char* name, void* value) override { voids_[name] = value; }
		void Set7(const char* name, ID3D12Resource* value) override { resources_[name] = value; }
		void Set8(const char* name, void* value) override { voids_[name] = value; }

		std::uint32_t GetVoidPointer(const char* name, void** value) override
		{
			auto it = voids_.find(name);
			if (it != voids_.end()) { *value = it->second; return kNGXSuccess; }
			auto it2 = resources_.find(name);
			if (it2 != resources_.end()) { *value = it2->second; return kNGXSuccess; }
			return 0xBAD00004;
		}
		std::uint32_t Get2(const char* name, float* value) override
		{
			auto it = floats_.find(name);
			if (it != floats_.end()) { *value = it->second; return kNGXSuccess; }
			return 0xBAD00004;
		}
		std::uint32_t Get3(const char* name, void* value) override
		{
			auto it = voids_.find(name);
			if (it != voids_.end()) { *static_cast<void**>(value) = it->second; return kNGXSuccess; }
			return 0xBAD00004;
		}
		std::uint32_t Get4(const char* name, std::uint32_t* value) override
		{
			auto it = uints_.find(name);
			if (it != uints_.end()) { *value = it->second; return kNGXSuccess; }
			return 0xBAD00004;
		}
		std::uint32_t Get5(const char* name, std::uint32_t* value) override { return Get4(name, value); }
		std::uint32_t Get6(const char* name, void* value) override { return Get3(name, value); }
		std::uint32_t Get7(const char* name, float* value) override { return Get2(name, value); }
		std::uint32_t Get8(const char* name, void* value) override { return Get3(name, value); }

	private:
		std::unordered_map<std::string, float> floats_;
		std::unordered_map<std::string, std::uint32_t> uints_;
		std::unordered_map<std::string, void*> voids_;
		std::unordered_map<std::string, ID3D12Resource*> resources_;
	};

	struct NGXHandle
	{
		unsigned int id = 0;
	};

	class NGXNR
	{
	public:
		bool initialized = false;   // NGX D3D12 session initialised (informational; Init_Ext may legitimately refuse on Skyrim - no NGX core)
		bool featureCreated = false;
		bool supported = false;     // CreateFeature 成功 = 硬件/驱动支持（v0.8.10 用试错替代 Caps 查询）

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
		int initVersion = 0;   // negotiated SDK version (0x13..0x16), 0 = refused (non-fatal)
		bool ready = false;           // v0.8.10：DLL 加载成功即 ready——Init 失败也试 CreateFeature

		// v0.8.11：NGX core 会话状态（由 nvngx_dlss.dll 建立——SkyrimUpscaler 实锤链路）
		bool coreInitOk = false;      // dlss.dll 会话建立成功（Init_Ext 或热身 CreateFeature）
		unsigned int coreInitResult = 0;  // 最近一次 core 初始化返回码
		// v0.8.12：dlss.dll 热身 CreateFeature 结果（区分"缺 core" vs "其他原因"）
		unsigned int warmupResult = 0;    // 0=未执行 1=成功 其他=返回码

	private:
		ID3D12Device* device = nullptr;
		HMODULE coreModule = nullptr; // v0.8.11：nvngx_dlss.dll（NGX core 宿主，自举 core 会话）
		HMODULE ngxModule = nullptr;  // nvngx_dlssnr.dll（执行 CreateFeature/Evaluate 的 NR snippet）
		OwnNGXParams params;          // v0.8.10：自实现参数对象（值成员，无需 AllocateParameters）
		NGXHandle* handle = nullptr;
		unsigned int outWidth = 0;
		unsigned int outHeight = 0;
		bool needCreate = true;
	};
}  // namespace FrameGen
