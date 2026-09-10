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
			const std::uint32_t inputWidth = std::max(1u, guideWidth);
			const std::uint32_t inputHeight = std::max(1u, guideHeight);

			if (!interop.IsInitialized() && !InitializeInterop(device, context))
				return false;
			if (Runtime::Instance().Status() != RuntimeStatus::Initialized && !InitializeRuntime())
				return false;
			if (!EnsureResources(color, depth, motionVectors, inputWidth, inputHeight, colorWidth, colorHeight))
				return LatchFailure("shared resource creation", interop.LastError());

			auto& eye = eyes[0];
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

			ID3D12GraphicsCommandList* commandList = nullptr;
			if (!interop.BeginD3D12(&commandList))
				return LatchFailure("BeginD3D12", interop.LastError());
			D3D12_RESOURCE_BARRIER barriers[4]{};
			ID3D12Resource* resources[4]{
				eye.color.resource12.Get(), eye.depth.resource12.Get(),
				eye.motionVectors.resource12.Get(), eye.output.resource12.Get()
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
			const bool succeeded = Runtime::Instance().Execute(commandList, 0,
				eye.color.resource12.Get(), eye.depth.resource12.Get(), eye.motionVectors.resource12.Get(),
				eye.output.resource12.Get(), inputWidth, inputHeight, colorWidth, colorHeight,
				motionVectorScaleX, motionVectorScaleY, tuning, resetPending);
			for (auto& barrier : barriers)
				std::swap(barrier.Transition.StateBefore, barrier.Transition.StateAfter);
			commandList->ResourceBarrier(static_cast<UINT>(std::size(barriers)), barriers);
			if (!interop.EndD3D12())
				return LatchFailure("EndD3D12", interop.LastError());
			if (!succeeded)
				return LatchFailure("Feature 18", static_cast<HRESULT>(Runtime::Instance().NgxResult()));

			context->CopyResource(output, eye.output.resource11.Get());
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
			// v0.44：color/depth/mvec 用 input 分辨率（guideWidth/guideHeight），
			// output 用 output 分辨率（colorWidth/colorHeight）。renderScale<1 时
			// input < output，DLSSNR 在低分辨率跑 + 原生 upscale。
			auto colorDesc = MakeSharedDesc(colorSource, guideWidth, guideHeight, sharedFlags);
			auto outputDesc = MakeSharedDesc(colorSource, colorWidth, colorHeight, D3D11_BIND_UNORDERED_ACCESS);
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
