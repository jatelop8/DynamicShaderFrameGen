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

	// NGXInstanceParameters vtable — v0.8.13 改为 dlss5-dx11-bridge 布局
	// （MIT，BG3/FO4/Unity 实战验证的 NVSDK_NGX_Parameter 完整 17 方法）：
	//   Set: 0=u64 1=float 2=double 3=uint 4=int 5=ID3D11Resource* 6=ID3D12Resource* 7=void*
	//   Get: 8=u64* 9=float* 10=double* 11=uint* 12=int* 13=ID3D11Resource** 14=ID3D12Resource** 15=void**
	//   Reset: 16
	// v0.8.10 用的 dlssg-to-fsr3 布局（Set3=uint32、无 Reset）与 DLSS 超分系
	// （nvngx_dlss.dll/dlssnr.dll 同一 SDK）的预期不符 → CreateFeature 参数校验
	// 失败 0xbad00005（GetScratchBufferSize 同码 = 参数无效）。
	struct NGXInstanceParameters
	{
		virtual unsigned int Set(const char* name, unsigned long long value) = 0;    // 0
		virtual unsigned int Set(const char* name, float value) = 0;                 // 1
		virtual unsigned int Set(const char* name, double value) = 0;                // 2
		virtual unsigned int Set(const char* name, unsigned int value) = 0;          // 3
		virtual unsigned int Set(const char* name, int value) = 0;                   // 4
		virtual unsigned int Set(const char* name, ID3D11Resource* value) = 0;       // 5
		virtual unsigned int Set(const char* name, ID3D12Resource* value) = 0;       // 6
		virtual unsigned int Set(const char* name, void* value) = 0;                 // 7
		virtual unsigned int Get(const char* name, unsigned long long* value) const = 0; // 8
		virtual unsigned int Get(const char* name, float* value) const = 0;          // 9
		virtual unsigned int Get(const char* name, double* value) const = 0;         // 10
		virtual unsigned int Get(const char* name, unsigned int* value) const = 0;   // 11
		virtual unsigned int Get(const char* name, int* value) const = 0;            // 12
		virtual unsigned int Get(const char* name, ID3D11Resource** value) const = 0;// 13
		virtual unsigned int Get(const char* name, ID3D12Resource** value) const = 0;// 14
		virtual unsigned int Get(const char* name, void** value) const = 0;          // 15
		virtual void Reset() = 0;                                                    // 16

		// v0.8.28：便捷方法（非虚，转发到虚 Set）——让驱动 core 分配的真 params
		// 对象也能用现有调用风格（Set4/Set2/Set7）
		void Set4(const char* name, std::uint32_t value) { Set(name, value); }
		void Set2(const char* name, float value) { Set(name, value); }
		void Set7(const char* name, ID3D12Resource* value) { Set(name, value); }
		void Set5(const char* name, std::uint32_t value) { Set(name, static_cast<int>(value)); }
		void SetVoidPointer(const char* name, void* value) { Set(name, reinterpret_cast<std::uint64_t>(value)); }
		void Set3(const char* name, void* value) { Set(name, reinterpret_cast<std::uint64_t>(value)); }
		void Set6(const char* name, void* value) { Set(name, reinterpret_cast<std::uint64_t>(value)); }
		void Set8(const char* name, void* value) { Set(name, reinterpret_cast<std::uint64_t>(value)); }
	};

	// v0.8.13：按 bridge 布局自实现参数对象——Set 存 map、Get 读 map（带类型容错）。
	// 便捷方法 Set4/Set2/Set7 保留（映射到 Set(uint)/Set(float)/Set(ID3D12Resource*)）。
	class OwnNGXParams : public NGXInstanceParameters
	{
	public:
		// --- bridge 布局的虚函数 ---
		unsigned int Set(const char* name, unsigned long long value) override { u64s_[name] = value; return kNGXSuccess; }
		unsigned int Set(const char* name, float value) override { floats_[name] = value; return kNGXSuccess; }
		unsigned int Set(const char* name, double value) override { doubles_[name] = value; return kNGXSuccess; }
		unsigned int Set(const char* name, unsigned int value) override { uints_[name] = value; return kNGXSuccess; }
		unsigned int Set(const char* name, int value) override { uints_[name] = static_cast<std::uint32_t>(value); return kNGXSuccess; }
		unsigned int Set(const char* name, ID3D11Resource* value) override { u64s_[name] = reinterpret_cast<std::uint64_t>(value); return kNGXSuccess; }
		unsigned int Set(const char* name, ID3D12Resource* value) override { u64s_[name] = reinterpret_cast<std::uint64_t>(value); return kNGXSuccess; }
		unsigned int Set(const char* name, void* value) override { u64s_[name] = reinterpret_cast<std::uint64_t>(value); return kNGXSuccess; }

		unsigned int Get(const char* name, unsigned long long* value) const override
		{
			auto it = u64s_.find(name);
			if (it != u64s_.end()) { *value = it->second; return kNGXSuccess; }
			auto it2 = uints_.find(name);
			if (it2 != uints_.end()) { *value = it2->second; return kNGXSuccess; }
			auto it3 = floats_.find(name);
			if (it3 != floats_.end()) { *value = static_cast<std::uint64_t>(it3->second); return kNGXSuccess; }
			return 0xBAD00004;
		}
		unsigned int Get(const char* name, float* value) const override
		{
			auto it = floats_.find(name);
			if (it != floats_.end()) { *value = it->second; return kNGXSuccess; }
			auto it2 = uints_.find(name);
			if (it2 != uints_.end()) { *value = static_cast<float>(it2->second); return kNGXSuccess; }
			auto it3 = u64s_.find(name);
			if (it3 != u64s_.end()) { *value = static_cast<float>(it3->second); return kNGXSuccess; }
			return 0xBAD00004;
		}
		unsigned int Get(const char* name, double* value) const override
		{
			auto it = doubles_.find(name);
			if (it != doubles_.end()) { *value = it->second; return kNGXSuccess; }
			auto it2 = floats_.find(name);
			if (it2 != floats_.end()) { *value = it2->second; return kNGXSuccess; }
			return 0xBAD00004;
		}
		unsigned int Get(const char* name, unsigned int* value) const override
		{
			auto it = uints_.find(name);
			if (it != uints_.end()) { *value = it->second; return kNGXSuccess; }
			auto it2 = u64s_.find(name);
			if (it2 != u64s_.end()) { *value = static_cast<std::uint32_t>(it2->second); return kNGXSuccess; }
			return 0xBAD00004;
		}
		unsigned int Get(const char* name, int* value) const override
		{
			auto it = uints_.find(name);
			if (it != uints_.end()) { *value = static_cast<int>(it->second); return kNGXSuccess; }
			auto it2 = u64s_.find(name);
			if (it2 != u64s_.end()) { *value = static_cast<int>(it2->second); return kNGXSuccess; }
			return 0xBAD00004;
		}
		unsigned int Get(const char* name, ID3D11Resource** value) const override
		{
			auto it = u64s_.find(name);
			if (it != u64s_.end()) { *value = reinterpret_cast<ID3D11Resource*>(it->second); return kNGXSuccess; }
			return 0xBAD00004;
		}
		unsigned int Get(const char* name, ID3D12Resource** value) const override
		{
			auto it = u64s_.find(name);
			if (it != u64s_.end()) { *value = reinterpret_cast<ID3D12Resource*>(it->second); return kNGXSuccess; }
			return 0xBAD00004;
		}
		unsigned int Get(const char* name, void** value) const override
		{
			auto it = u64s_.find(name);
			if (it != u64s_.end()) { *value = reinterpret_cast<void*>(it->second); return kNGXSuccess; }
			return 0xBAD00004;
		}
		void Reset() override { floats_.clear(); doubles_.clear(); uints_.clear(); u64s_.clear(); }

		// --- 便捷方法（现有调用兼容）---
		void Set4(const char* name, std::uint32_t value) { Set(name, value); }
		void Set2(const char* name, float value) { Set(name, value); }
		void Set7(const char* name, ID3D12Resource* value) { Set(name, value); }
		void Set5(const char* name, std::uint32_t value) { Set(name, static_cast<int>(value)); }
		void SetVoidPointer(const char* name, void* value) { Set(name, value); }
		void Set3(const char* name, void* value) { Set(name, reinterpret_cast<std::uint64_t>(value)); }
		void Set6(const char* name, void* value) { Set(name, reinterpret_cast<std::uint64_t>(value)); }
		void Set8(const char* name, void* value) { Set(name, reinterpret_cast<std::uint64_t>(value)); }

	private:
		std::unordered_map<std::string, float> floats_;
		std::unordered_map<std::string, double> doubles_;
		std::unordered_map<std::string, std::uint32_t> uints_;
		std::unordered_map<std::string, std::uint64_t> u64s_;
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
		// v0.8.14：热身只试一次（失败后不每帧重试刷屏）；GetScratchBufferSize 诊断
		bool warmupTried = false;
		unsigned int scratchSizeResult = 0;  // 0=未执行 1=成功 其他=返回码（core 缺失实锤）
		// v0.8.18：NR feature id 遍历——dlssnr 反汇编开头 mov ecx,6（可能 NR feature id=6），
		// id=1（SuperSampling）在 core=ok 下仍 0xbad00002 → 遍历 0..10 找成功 id
		int nrFeatureId = -1;         // 已锁定的 NR feature id（-1=未定）
		bool nrIdTriedAll = false;    // 遍历过全部仍失败（不再每帧遍历）
		// v0.8.21：warmup 的 dlss feature 不释放——dlss.dll 的 core 单例随其 feature
		// 存活；立即 Release 可能连带销毁 core → dlssnr 找不到。保留到 Shutdown。
		NGXHandle* warmupHandle = nullptr;
		// v0.8.23：GetCapabilityParameters 只查一次（core 就绪后）
		bool capsQueried = false;
		// v0.8.28：驱动 core 分配的真 params（AllocateParameters）——替代自实现
		// OwnNGXParams（Evaluate 0xbad00005 可能是自实现 vtable 与驱动 core 预期不符）
		NGXInstanceParameters* realParams = nullptr;
		// DestroyParameters 函数指针（释放 realParams）
		unsigned int(__cdecl* paramsDestroy)(NGXInstanceParameters*) = nullptr;

	private:
		ID3D12Device* device = nullptr;
		HMODULE ngxCoreModule = nullptr; // v0.8.22：驱动 NGX core（nvngx.dll，SkyrimUpscaler 同款）
		HMODULE coreModule = nullptr; // v0.8.11：nvngx_dlss.dll（NGX core 宿主，自举 core 会话）
		HMODULE ngxModule = nullptr;  // nvngx_dlssnr.dll（执行 CreateFeature/Evaluate 的 NR snippet）
		OwnNGXParams params;          // v0.8.10：自实现参数对象（值成员，无需 AllocateParameters）
		NGXHandle* handle = nullptr;
		unsigned int outWidth = 0;
		unsigned int outHeight = 0;
		bool needCreate = true;
	};
}  // namespace FrameGen
