// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
//
// Runtime.h - DLSS Neural Rendering (DLSS5) NGX Feature 18 runtime wrapper.
// Ported from Community Shaders / Open Shaders (GPL-3.0):
//   YtzyFvra/skyrim-community-shaders, branch feature/dlssnr-vr
//   src/Features/Upscaling/NeuralRendering/Runtime.h
// (NGX Feature 18 = DLSSNR, loaded directly from nvngx_dlssnr.dll on a private
//  D3D12 session - no Streamline, no ReShade bridge.)

#pragma once

#include <cstdint>
#include <filesystem>
#include <string>

struct ID3D12Device;
struct ID3D12GraphicsCommandList;
struct ID3D12Resource;

namespace NeuralRendering
{
	// v1.45：单帧内串联的神经渲染层数上限。每一层是一个独立的 NGX Feature 18
	// 实例（各自持有自己的时域历史与内部资源），所以这个数字同时是"每帧成本"
	// 与"显存占用"的上限 —— 不是免费的效果叠加。
	// 槽位 = 层号：非 VR 下 slot 0 是第一层，slot 1..kMaxNRLayers-1 是第 2..N 层。
	inline constexpr std::uint32_t kMaxNRLayers = 8;

	struct Tuning
	{
		float intensity = 0.8f;
		float localToneStrength = 0.75f;
		float localStructureStrength = 0.9f;
		float skinStructureStrength = 0.9f;
		std::uint32_t style = 3;
		bool useAutoMask = true;
		bool uiCorrection = false;
		// v0.44：DLSSNR 输入分辨率缩放（性能优化）。1.0 = 全分辨率（默认，
		// 与 output 同分辨率）；0.5 = 半分辨率输入（FP8 张量计算量减 ~75%，
		// 由 DLSSNR 原生 Upscaling 放大回 output）。0.5~0.75 是推荐区间。
		float renderScale = 1.0f;
		// v1.45：多层神经渲染（NRLayers）。1 = 关闭（v1.44 行为）。>=2 时同一帧内把
		// 神经渲染串联 N 遍：第 k 层的 color 输入是第 k-1 层的输出，depth/mvec guides
		// 全程复用（同一帧、同一相机，guides 不随层变化）。
		std::uint32_t layers = 1;
	};

	enum class RuntimeStatus
	{
		NotProbed, NotFound, VersionUnavailable, UnsupportedVersion, LoadFailed, MissingExport,
		Ready, InitializationFailed, CoreUnavailable, ParameterAllocationFailed, Initialized,
	};

	class Runtime
	{
	public:
		static Runtime& Instance();
		~Runtime();
		Runtime(const Runtime&) = delete;
		Runtime& operator=(const Runtime&) = delete;

		bool Probe(const std::filesystem::path& explicitPath = {});
		bool Initialize(ID3D12Device* device, const std::filesystem::path& dataPath = {});
		bool Execute(ID3D12GraphicsCommandList* commandList, std::uint32_t slot,
			ID3D12Resource* color, ID3D12Resource* depth, ID3D12Resource* motionVectors, ID3D12Resource* output,
			std::uint32_t inputWidth, std::uint32_t inputHeight, std::uint32_t outputWidth, std::uint32_t outputHeight,
			float motionVectorScaleX, float motionVectorScaleY, const Tuning& tuning, bool reset);
		void ResetFeature(std::uint32_t slot);
		void ResetFeatures();
		void Shutdown();

		[[nodiscard]] RuntimeStatus Status() const { return status_; }
		[[nodiscard]] const std::string& Version() const { return version_; }
		[[nodiscard]] const std::string& Detail() const { return detail_; }
		[[nodiscard]] std::uint32_t NgxResult() const { return ngxResult_; }
		[[nodiscard]] std::uint32_t ApplicationId() const { return applicationId_; }
		[[nodiscard]] std::uint32_t ApiVersion() const { return apiVersion_; }
		[[nodiscard]] std::uint64_t SuccessfulFrames() const { return successfulFrames_; }

	private:
		Runtime() = default;
		void* module_ = nullptr;
		void* parameters_ = nullptr;
		void* featureHandles_[kMaxNRLayers]{};
		std::uint32_t featureInputWidth_[kMaxNRLayers]{};
		std::uint32_t featureInputHeight_[kMaxNRLayers]{};
		std::uint32_t featureOutputWidth_[kMaxNRLayers]{};
		std::uint32_t featureOutputHeight_[kMaxNRLayers]{};
		ID3D12Device* device_ = nullptr;
		RuntimeStatus status_ = RuntimeStatus::NotProbed;
		std::filesystem::path path_;
		std::string version_;
		std::string detail_;
		std::uint32_t ngxResult_ = 0;
		std::uint32_t applicationId_ = 0;
		std::uint32_t apiVersion_ = 0;
		std::uint64_t successfulFrames_ = 0;
	};

	const char* ToString(RuntimeStatus status);
}
