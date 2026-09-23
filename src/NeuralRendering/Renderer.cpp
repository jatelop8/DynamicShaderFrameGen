// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
//
// Renderer.cpp - DLSS Neural Rendering D3D11 front-end (non-VR).
// Ported from Community Shaders / Open Shaders (GPL-3.0):
//   YtzyFvra/skyrim-community-shaders, branch feature/dlssnr-vr
//   src/Features/Upscaling/NeuralRendering/Renderer.cpp

#include <SKSE/SKSE.h>

#include "Renderer.h"

#include "D3D12Interop.h"

#include <algorithm>
#include <array>
#include <utility>

#include <d3d11.h>
#include <d3dcompiler.h>
#include <dxgi.h>
#include <wrl/client.h>

namespace NeuralRendering
{
	namespace
	{
		bool GetTextureDesc(ID3D11Resource* resource, D3D11_TEXTURE2D_DESC& desc)
		{
			Microsoft::WRL::ComPtr<ID3D11Texture2D> texture;
			if (!resource || FAILED(resource->QueryInterface(IID_PPV_ARGS(&texture))))
				return false;
			texture->GetDesc(&desc);
			return true;
		}

		bool Matches(const SharedTexture& texture, const D3D11_TEXTURE2D_DESC& desc)
		{
			return texture.resource11 && texture.desc.Width == desc.Width && texture.desc.Height == desc.Height &&
			       texture.desc.Format == desc.Format && texture.desc.ArraySize == desc.ArraySize &&
			       texture.desc.MipLevels == desc.MipLevels && texture.desc.SampleDesc.Count == desc.SampleDesc.Count;
		}

		D3D11_TEXTURE2D_DESC MakeSharedDesc(const D3D11_TEXTURE2D_DESC& source, std::uint32_t width,
			std::uint32_t height, UINT bindFlags)
		{
			auto desc = source;
			desc.Width = width;
			desc.Height = height;
			desc.MipLevels = 1;
			desc.ArraySize = 1;
			desc.SampleDesc.Count = 1;
			desc.SampleDesc.Quality = 0;
			desc.Usage = D3D11_USAGE_DEFAULT;
			desc.BindFlags = bindFlags;
			desc.CPUAccessFlags = 0;
			desc.MiscFlags = 0;
			return desc;
		}
	}

	class Renderer::State
	{
	public:
		struct EyeResources
		{
			SharedTexture color;
			SharedTexture depth;
			SharedTexture motionVectors;
			SharedTexture output;
		};

		bool Apply(ID3D11Device* device, ID3D11DeviceContext* context,
			ID3D11Resource* color, ID3D11Resource* depth, ID3D11ShaderResourceView* depthSRV,
			ID3D11Resource* motionVectors, ID3D11Resource* output,
			std::uint32_t guideWidth, std::uint32_t guideHeight,
			std::uint32_t colorWidth, std::uint32_t colorHeight,
			float motionVectorScaleX, float motionVectorScaleY, const Tuning& tuning)
		{
			if (failureLatched || !device || !context || !color || !depth || !depthSRV || !motionVectors || !output)
				return false;

			// v0.46（renodx 同款）：DLSSNR 输入 = 引擎渲染分辨率（guideWidth/Height，
			// DRS viewport），output = 呈现分辨率（colorWidth/Height）。神经网络在低
			// 分辨率跑（FP8 计算按渲染面积，快）+ 原生 Upscaling 放大回 output。
			// 从 kMAIN（渲染目标）subrect 1:1 取渲染区域，非 colorOut downscale
			// （downscale 丢细节 + 多一次处理）。input 由调用方传渲染分辨率。
			std::uint32_t inputWidth = std::max(1u, guideWidth);
			std::uint32_t inputHeight = std::max(1u, guideHeight);
			// v1.38：接线 NRRenderScale（v0.44 声明、INI/菜单暴露，但此前没有任何消费者）。
			// DRS 未生效时 guide 区域 == 输出尺寸，神经网络只能按全分辨率跑（约 15 ms/帧）。
			// 把 NR 输入按比例调小、交给 DLSSNR 原生超分放回去，FP8 张量计算量最多减 ~75%。
			// renderScale == 1.0（默认）时 scaledW >= guideW，useDownscale 恒 false，
			// 走原 subrect 路径 —— 行为与改动前完全一致。
			if (tuning.renderScale > 0.0f && tuning.renderScale < 0.999f) {
				const std::uint32_t scaledWidth =
					std::max(1u, static_cast<std::uint32_t>(colorWidth * tuning.renderScale + 0.5f));
				const std::uint32_t scaledHeight =
					std::max(1u, static_cast<std::uint32_t>(colorHeight * tuning.renderScale + 0.5f));
				inputWidth = std::min(inputWidth, scaledWidth);
				inputHeight = std::min(inputHeight, scaledHeight);
			}
			const bool useDownscale =
				inputWidth < std::max(1u, guideWidth) || inputHeight < std::max(1u, guideHeight);

			if (!interop.IsInitialized() && !InitializeInterop(device, context))
				return false;
			if (Runtime::Instance().Status() != RuntimeStatus::Initialized && !InitializeRuntime())
				return false;
			if (!EnsureResources(color, depth, motionVectors, inputWidth, inputHeight, colorWidth, colorHeight))
				return LatchFailure("shared resource creation", interop.LastError());

			auto& eye = eyes[0];
			if (useDownscale) {
				// v1.43: only depth/mvec are taken at the low-resolution guide extent; the
				// Color copy stays at the presentation extent (1:1).  v1.38..v1.42 also
				// downscaled Color, and that is the one input DLSSNR rejected.
				D3D11_TEXTURE2D_DESC colorSourceDesc{};
				if (!GetTextureDesc(color, colorSourceDesc))
					return LatchFailure("color texture description", E_FAIL);
				const std::uint32_t copyWidth = std::min(colorWidth, colorSourceDesc.Width);
				const std::uint32_t copyHeight = std::min(colorHeight, colorSourceDesc.Height);
				static std::uint32_t scaleDiag = 0;
				if (++scaleDiag % 300 == 1)
					SKSE::log::info("[DLSSNR] renderScale path: guides={}x{} color/output={}x{} "
						"copy={}x{} (v1.43)",
						inputWidth, inputHeight, colorWidth, colorHeight, copyWidth, copyHeight);
				D3D11_BOX colorBox{};
				colorBox.left = 0;
				colorBox.top = 0;
				colorBox.front = 0;
				colorBox.right = copyWidth;
				colorBox.bottom = copyHeight;
				colorBox.back = 1;
				context->CopySubresourceRegion(eye.color.resource11.Get(), 0, 0, 0, 0, color, 0, &colorBox);
				Microsoft::WRL::ComPtr<ID3D11ShaderResourceView> mvecSRV;
				if (FAILED(device_->CreateShaderResourceView(motionVectors, nullptr, mvecSRV.GetAddressOf())))
					return LatchFailure("nr mvec SRV creation", E_FAIL);
				if (!CopyDepthGuide(context, depthSRV, eye.depth.uav11.Get(), inputWidth, inputHeight))
					return LatchFailure("depth guide conversion", E_FAIL);
				if (!Downscale(context, mvecSRV.Get(), eye.motionVectors.uav11.Get(), inputWidth, inputHeight))
					return LatchFailure("mvec downscale", E_FAIL);
			} else {
				// subrect 1:1 拷贝：从源纹理左上角 [0,0,inputWidth,inputHeight] 区域
				// （DRS viewport 内容）取到 input 共享纹理，无 downscale。
				D3D11_BOX box{};
				box.left = 0;
				box.top = 0;
				box.front = 0;
				box.right = inputWidth;
				box.bottom = inputHeight;
				box.back = 1;
				context->CopySubresourceRegion(eye.color.resource11.Get(), 0, 0, 0, 0, color, 0, &box);
				if (!CopyDepthGuide(context, depthSRV, eye.depth.uav11.Get(), inputWidth, inputHeight))
					return LatchFailure("depth guide conversion", E_FAIL);
				context->CopySubresourceRegion(eye.motionVectors.resource11.Get(), 0, 0, 0, 0, motionVectors, 0, &box);
			}

			ID3D12GraphicsCommandList* commandList = nullptr;
			if (!interop.BeginD3D12(&commandList))
				return LatchFailure("BeginD3D12", interop.LastError());
			// v1.45 —— 多层神经渲染（DLSS5 layers）。
			//
			// 每一层把上一层的输出当作自己的 color 输入再跑一遍；depth/mvec guides 全程复用
			// （同一帧、同一相机 ⇒ guides 与层数无关，所以只在这之前上传一次）。层与层之间
			// 不需要任何拷贝：eye.color 与 eye.output 是同规格（同尺寸/格式、SRV|UAV）的两张
			// 共享纹理，第 k 层用一张当输入、另一张当输出，下一层把角色对调 —— 纯乒乓。
			//
			// 全部录制在**同一条 command list** 上，层间顺序由 GPU 保证（没有 CPU 同步、没有
			// 额外的 D3D11<->D3D12 摆渡）。层数 1 时这条路径与 v1.44 等价：A -> B，然后把 B
			// 拷回调用方（奇偶交替见下方 result11）。
			//
			// 每层用自己的 NGX 句柄（slot = 层号）⇒ 每层有自己的时域历史。共用一个句柄也能
			// "叠"，但那样第 2 层会拿第 1 层刚刚在同一帧写过的历史做时域比对（delta≈0），
			// 语义是错的。
			const std::uint32_t layersRequested = std::clamp<std::uint32_t>(tuning.layers, 1u, kMaxNRLayers);
			std::uint32_t layersDone = 0;
			bool firstLayerFailed = false;
			for (std::uint32_t layer = 0; layer < layersRequested; ++layer) {
				ID3D12Resource* layerInput = (layer % 2 == 0) ? eye.color.resource12.Get() : eye.output.resource12.Get();
				ID3D12Resource* layerOutput = (layer % 2 == 0) ? eye.output.resource12.Get() : eye.color.resource12.Get();
				D3D12_RESOURCE_BARRIER barriers[4]{};
				ID3D12Resource* resources[4]{
					layerInput, eye.depth.resource12.Get(),
					eye.motionVectors.resource12.Get(), layerOutput
				};
				for (std::size_t index = 0; index < std::size(barriers); ++index) {
					barriers[index].Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
					barriers[index].Transition.pResource = resources[index];
					barriers[index].Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
					barriers[index].Transition.StateBefore = D3D12_RESOURCE_STATE_COMMON;
					barriers[index].Transition.StateAfter = index == 3 ? D3D12_RESOURCE_STATE_UNORDERED_ACCESS :
					                                                           D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;
				}
				commandList->ResourceBarrier(static_cast<UINT>(std::size(barriers)), barriers);
				const bool layerOk = Runtime::Instance().Execute(commandList, layer,
					layerInput, eye.depth.resource12.Get(), eye.motionVectors.resource12.Get(),
					layerOutput, inputWidth, inputHeight, colorWidth, colorHeight,
					motionVectorScaleX, motionVectorScaleY, tuning, resetPending);
				for (auto& barrier : barriers)
					std::swap(barrier.Transition.StateBefore, barrier.Transition.StateAfter);
				commandList->ResourceBarrier(static_cast<UINT>(std::size(barriers)), barriers);
				if (!layerOk) {
					// 第 0 层失败 = 旧版语义：NR 整条链路锁死（LatchFailure，见循环之后）。
					// 第 k>=1 层失败（驱动不再允许创建第 k 个 Feature 18 实例，或该实例的
					// evaluate 返回 InvalidParameter）**不锁死**：退回已经算好的层数。否则把
					// 层数调高一次就把 DLSS5 整个弄没了 —— 那比看不到多层效果严重得多。
					if (layer == 0) {
						firstLayerFailed = true;
						break;
					}
					static std::uint32_t layerFailLogged = 0;
					if (++layerFailLogged % 300 == 1)
						SKSE::log::warn("[DLSSNR] multi-layer: layer {}/{} failed ngx=0x{:08X} - keeping {} layer(s)",
							layer, layersRequested, Runtime::Instance().NgxResult(), layersDone);
					break;
				}
				layersDone = layer + 1;
			}
			// 注意：第 0 层失败也不能在 recording 状态下直接返回 —— EndD3D12 必须先跑完，
			// 否则 interop 的 recording_ 永远为真，之后任何 BeginD3D12 都会被 E_UNEXPECTED 拒掉。
			if (!interop.EndD3D12())
				return LatchFailure("EndD3D12", interop.LastError());
			if (firstLayerFailed)
				return LatchFailure("Feature 18", static_cast<HRESULT>(Runtime::Instance().NgxResult()));

			if (layersRequested > 1) {
				static std::uint32_t layerDiag = 0;
				if (++layerDiag % 120 == 1)
					SKSE::log::info("[DLSSNR] multi-layer: {}/{} pass(es) chained, guides reused, one command list",
						layersDone, layersRequested);
			}

			// 结果停在最后一个成功的层写的那张纹理上：第 1 层写完在 output、第 2 层在 color、
			// 第 3 层又回 output ……（奇偶交替）。
			ID3D11Resource* result11 = (layersDone % 2 == 1) ? eye.output.resource11.Get() : eye.color.resource11.Get();
			context->CopyResource(output, result11);
			resetPending = false;
			return true;
		}

		void Reset()
		{
			interop.WaitForIdle();
			Runtime::Instance().Shutdown();
			interop.Shutdown();
			eyes = {};
			resetPending = true;
			failureLatched = false;
			copyDepthGuideCS_.Reset();
		}

		void ResetHistory()
		{
			interop.WaitForIdle();
			Runtime::Instance().ResetFeatures();
			resetPending = true;
		}

		[[nodiscard]] bool IsFailureLatched() const { return failureLatched; }

	private:
		bool CopyDepthGuide(ID3D11DeviceContext* context, ID3D11ShaderResourceView* source,
			ID3D11UnorderedAccessView* destination, std::uint32_t width, std::uint32_t height)
		{
			if (!destination)
				return false;
			if (!copyDepthGuideCS_) {
				if (!device_)
					return false;
				Microsoft::WRL::ComPtr<ID3DBlob> blob;
				Microsoft::WRL::ComPtr<ID3DBlob> errorBlob;
				const HRESULT hr = D3DCompileFromFile(
					L"Data\\Shaders\\Upscaling\\NeuralRendering\\CopyDepthGuideCS.hlsl",
					nullptr, nullptr, "main", "cs_5_0", 0, 0, blob.GetAddressOf(), errorBlob.GetAddressOf());
				if (FAILED(hr)) {
					if (errorBlob)
						SKSE::log::error("[DLSSNR] CopyDepthGuideCS compile failed: {}",
							static_cast<const char*>(errorBlob->GetBufferPointer()));
					return false;
				}
				Microsoft::WRL::ComPtr<ID3D11ComputeShader> shader;
				if (FAILED(device_->CreateComputeShader(blob->GetBufferPointer(), blob->GetBufferSize(), nullptr, shader.GetAddressOf())))
					return false;
				copyDepthGuideCS_ = shader;
			}
			context->CSSetShader(copyDepthGuideCS_.Get(), nullptr, 0);
			context->CSSetShaderResources(0, 1, &source);
			context->CSSetUnorderedAccessViews(0, 1, &destination, nullptr);
			context->Dispatch((width + 7) / 8, (height + 7) / 8, 1);
			ID3D11ShaderResourceView* nullSRV = nullptr;
			ID3D11UnorderedAccessView* nullUAV = nullptr;
			context->CSSetShaderResources(0, 1, &nullSRV);
			context->CSSetUnorderedAccessViews(0, 1, &nullUAV, nullptr);
			context->CSSetShader(nullptr, nullptr, 0);
			return true;
		}

		bool Downscale(ID3D11DeviceContext* context, ID3D11ShaderResourceView* source,
			ID3D11UnorderedAccessView* destination, std::uint32_t dstWidth, std::uint32_t dstHeight)
		{
			if (!source || !destination)
				return false;
			if (!downscaleCS_) {
				if (!device_)
					return false;
				Microsoft::WRL::ComPtr<ID3DBlob> blob;
				Microsoft::WRL::ComPtr<ID3DBlob> errorBlob;
				const HRESULT hr = D3DCompileFromFile(
					L"Data\\Shaders\\Upscaling\\NeuralRendering\\DownscaleCS.hlsl",
					nullptr, nullptr, "main", "cs_5_0", 0, 0, blob.GetAddressOf(), errorBlob.GetAddressOf());
				if (FAILED(hr)) {
					if (errorBlob)
						SKSE::log::error("[DLSSNR] DownscaleCS compile failed: {}",
							static_cast<const char*>(errorBlob->GetBufferPointer()));
					return false;
				}
				Microsoft::WRL::ComPtr<ID3D11ComputeShader> shader;
				if (FAILED(device_->CreateComputeShader(blob->GetBufferPointer(), blob->GetBufferSize(), nullptr, shader.GetAddressOf())))
					return false;
				downscaleCS_ = shader;
			}
			context->CSSetShader(downscaleCS_.Get(), nullptr, 0);
			context->CSSetShaderResources(0, 1, &source);
			context->CSSetUnorderedAccessViews(0, 1, &destination, nullptr);
			context->Dispatch((dstWidth + 7) / 8, (dstHeight + 7) / 8, 1);
			ID3D11ShaderResourceView* nullSRV = nullptr;
			ID3D11UnorderedAccessView* nullUAV = nullptr;
			context->CSSetShaderResources(0, 1, &nullSRV);
			context->CSSetUnorderedAccessViews(0, 1, &nullUAV, nullptr);
			context->CSSetShader(nullptr, nullptr, 0);
			return true;
		}

		bool InitializeInterop(ID3D11Device* device, ID3D11DeviceContext* context)
		{
			device_ = device;
			Microsoft::WRL::ComPtr<IDXGIDevice> dxgiDevice;
			Microsoft::WRL::ComPtr<IDXGIAdapter> adapter;
			HRESULT result = device->QueryInterface(IID_PPV_ARGS(&dxgiDevice));
			if (SUCCEEDED(result)) result = dxgiDevice->GetAdapter(&adapter);
			if (FAILED(result) || !interop.Initialize(adapter.Get(), device, context))
				return LatchFailure("D3D12 interop initialization", FAILED(result) ? result : interop.LastError());
			return true;
		}

		bool InitializeRuntime()
		{
			auto& runtime = Runtime::Instance();
			if (!runtime.Probe() || !runtime.Initialize(interop.Device()))
				return LatchFailure("runtime initialization", static_cast<HRESULT>(runtime.NgxResult()));
			SKSE::log::info("[DLSSNR] initialized version={} appId=0x{:08X} api=0x{:X}",
				runtime.Version(), runtime.ApplicationId(), runtime.ApiVersion());
			return true;
		}

		bool EnsureResources(ID3D11Resource* color, ID3D11Resource* depth,
			ID3D11Resource* motionVectors, std::uint32_t guideWidth, std::uint32_t guideHeight,
			std::uint32_t colorWidth, std::uint32_t colorHeight)
		{
			D3D11_TEXTURE2D_DESC colorSource{}, depthSource{}, motionSource{};
			if (!GetTextureDesc(color, colorSource) || !GetTextureDesc(depth, depthSource) ||
				!GetTextureDesc(motionVectors, motionSource))
				return false;
			const UINT sharedFlags = D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_UNORDERED_ACCESS;
			// v1.43: the Color texture goes back to the PRESENTATION extent, matching the
			// upstream Community Shaders implementation this file is ported from.  Upstream
			// always builds Color as colorWidth x colorHeight; only depth/mvec are taken at
			// the low-resolution guide extent.  v1.38..v1.42 downscaled Color as well, and
			// every run in that configuration had Evaluate answer 0xBAD00005
			// (InvalidParameter) with frames=0 -- the one configuration that ever worked
			// (renderScale=1.00) is exactly the one where guide == color == presentation.
			auto colorDesc = MakeSharedDesc(colorSource, colorWidth, colorHeight, sharedFlags);
			// v1.45：多层神经渲染需要 output 纹理也能被当作下一层的 color **输入**读，
			// 所以它与 color 纹理同规格（SRV|UAV）。两张纹理互为输入/输出乒乓对，
			// 层与层之间因此不需要任何拷贝。单层时这个改动无语义影响。
			auto outputDesc = MakeSharedDesc(colorSource, colorWidth, colorHeight, sharedFlags);
			auto depthDesc = MakeSharedDesc(depthSource, guideWidth, guideHeight, sharedFlags);
			depthDesc.Format = DXGI_FORMAT_R32_FLOAT;
			auto motionDesc = MakeSharedDesc(motionSource, guideWidth, guideHeight, sharedFlags);
			auto& eye = eyes[0];
			if (Matches(eye.color, colorDesc) && Matches(eye.output, outputDesc) &&
				Matches(eye.depth, depthDesc) && Matches(eye.motionVectors, motionDesc))
				return true;

			if (!interop.WaitForIdle())
				return false;
			Runtime::Instance().ResetFeature(0);
			eye = {};
			if (!interop.CreateSharedTexture(colorDesc, eye.color, "NeuralRendering::Color") ||
				!interop.CreateSharedTexture(outputDesc, eye.output, "NeuralRendering::Output") ||
				!interop.CreateSharedTexture(depthDesc, eye.depth, "NeuralRendering::Depth") ||
				!interop.CreateSharedTexture(motionDesc, eye.motionVectors, "NeuralRendering::Motion"))
				return false;
			resetPending = true;
			SKSE::log::info("[DLSSNR] resources guides={}x{} color={}x{}", guideWidth, guideHeight, colorWidth, colorHeight);
			return true;
		}

		bool LatchFailure(const char* operation, HRESULT error)
		{
			failureLatched = true;
			SKSE::log::error("[DLSSNR] {} failed hr/ngx=0x{:08X} status={} detail={}",
				operation, static_cast<std::uint32_t>(error), ToString(Runtime::Instance().Status()), Runtime::Instance().Detail());
			return false;
		}

		D3D12Interop interop;
		Microsoft::WRL::ComPtr<ID3D11Device> device_;
		Microsoft::WRL::ComPtr<ID3D11ComputeShader> copyDepthGuideCS_;
		Microsoft::WRL::ComPtr<ID3D11ComputeShader> downscaleCS_;
		std::array<EyeResources, 1> eyes;
		bool resetPending = true;
		bool failureLatched = false;
	};

	Renderer::Renderer() : state_(new State()) {}
	Renderer::~Renderer() { delete state_; }
	Renderer& Renderer::Instance() { static Renderer instance; return instance; }

	bool Renderer::Apply(ID3D11Device* device, ID3D11DeviceContext* context,
		ID3D11Resource* color, ID3D11Resource* depth, ID3D11ShaderResourceView* depthSRV,
		ID3D11Resource* motionVectors, ID3D11Resource* output,
		std::uint32_t guideWidth, std::uint32_t guideHeight, std::uint32_t colorWidth, std::uint32_t colorHeight,
		float motionVectorScaleX, float motionVectorScaleY, const Tuning& tuning)
	{
		return state_->Apply(device, context, color, depth, depthSRV, motionVectors, output,
			guideWidth, guideHeight, colorWidth, colorHeight, motionVectorScaleX, motionVectorScaleY, tuning);
	}

	void Renderer::Reset() { state_->Reset(); }
	void Renderer::ResetHistory() { state_->ResetHistory(); }
	bool Renderer::IsFailureLatched() const { return state_->IsFailureLatched(); }
	std::uint32_t Renderer::NgxResult() const { return Runtime::Instance().NgxResult(); }
	std::uint64_t Renderer::SuccessfulFrames() const { return Runtime::Instance().SuccessfulFrames(); }
	const char* Renderer::StatusText() const { return ToString(Runtime::Instance().Status()); }
}
