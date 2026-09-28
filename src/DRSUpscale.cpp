// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
// Derived from Skyrim Community Shaders (https://github.com/doodlum/skyrim-community-shaders,
// GPL-3.0): Upscaling::UpscaleDepth.

// CommonLib must come before any Windows header (REX/W32 check).
#include <SKSE/SKSE.h>
#include <RE/Skyrim.h>

#include "DRSUpscale.h"

#include <d3dcommon.h>

#include <algorithm>
#include <exception>

namespace FrameGen
{
	// defined in DX12SwapChain.cpp
	winrt::com_ptr<ID3DBlob> CompileShaderFromFile(const wchar_t* a_path, const char* a_defineName, const char* a_profile);

	namespace
	{
		// The engine caches its own D3D11 state and only re-binds what it believes has
		// changed, so everything bound here must go back exactly as it was.
		struct SavedState
		{
			// Binding the upscaled buffers as outputs unbinds them from every input slot
			// of every stage, so all shader-resource slots (and the compute UAVs) are
			// saved, not just the ones this pass uses.
			static constexpr UINT kSrvSlots = D3D11_COMMONSHADER_INPUT_RESOURCE_SLOT_COUNT;
			static constexpr UINT kUavSlots = D3D11_1_UAV_SLOT_COUNT;
			enum Stage { kVS, kHS, kDS, kGS, kPS, kCS, kStages };

			explicit SavedState(ID3D11DeviceContext* a_ctx) :
				ctx(a_ctx)
			{
				ctx->IAGetInputLayout(inputLayout.put());
				ctx->IAGetPrimitiveTopology(&topology);
				ctx->VSGetShader(vs.put(), nullptr, nullptr);
				ctx->PSGetShader(ps.put(), nullptr, nullptr);
				ctx->VSGetShaderResources(0, kSrvSlots, srvs[kVS]);
				ctx->HSGetShaderResources(0, kSrvSlots, srvs[kHS]);
				ctx->DSGetShaderResources(0, kSrvSlots, srvs[kDS]);
				ctx->GSGetShaderResources(0, kSrvSlots, srvs[kGS]);
				ctx->PSGetShaderResources(0, kSrvSlots, srvs[kPS]);
				ctx->CSGetShaderResources(0, kSrvSlots, srvs[kCS]);
				ctx->CSGetUnorderedAccessViews(0, kUavSlots, uavs);
				ctx->PSGetSamplers(0, 1, sampler.put());
				ctx->PSGetConstantBuffers(0, 1, cb.put());
				ctx->RSGetState(rasterizer.put());
				viewportCount = D3D11_VIEWPORT_AND_SCISSORRECT_OBJECT_COUNT_PER_PIPELINE;
				ctx->RSGetViewports(&viewportCount, viewports);
				ctx->OMGetBlendState(blend.put(), blendFactor, &sampleMask);
				ctx->OMGetDepthStencilState(depthStencil.put(), &stencilRef);
				ctx->OMGetRenderTargets(D3D11_SIMULTANEOUS_RENDER_TARGET_COUNT, rtvs, dsv.put());
			}
			~SavedState()
			{
				ctx->IASetInputLayout(inputLayout.get());
				ctx->IASetPrimitiveTopology(topology);
				ctx->VSSetShader(vs.get(), nullptr, 0);
				ctx->PSSetShader(ps.get(), nullptr, 0);
				ID3D11SamplerState* s = sampler.get();
				ctx->PSSetSamplers(0, 1, &s);
				ID3D11Buffer* b = cb.get();
				ctx->PSSetConstantBuffers(0, 1, &b);
				ctx->RSSetState(rasterizer.get());
				ctx->RSSetViewports(viewportCount, viewports);
				ctx->OMSetBlendState(blend.get(), blendFactor, sampleMask);
				ctx->OMSetDepthStencilState(depthStencil.get(), stencilRef);
				// Outputs first: an input view restored while one of this pass's outputs
				// is still bound would be dropped again as a read/write hazard.
				ctx->OMSetRenderTargets(D3D11_SIMULTANEOUS_RENDER_TARGET_COUNT, rtvs, dsv.get());
				ctx->VSSetShaderResources(0, kSrvSlots, srvs[kVS]);
				ctx->HSSetShaderResources(0, kSrvSlots, srvs[kHS]);
				ctx->DSSetShaderResources(0, kSrvSlots, srvs[kDS]);
				ctx->GSSetShaderResources(0, kSrvSlots, srvs[kGS]);
				ctx->PSSetShaderResources(0, kSrvSlots, srvs[kPS]);
				ctx->CSSetShaderResources(0, kSrvSlots, srvs[kCS]);
				ctx->CSSetUnorderedAccessViews(0, kUavSlots, uavs, nullptr);
				for (auto& stage : srvs)
					for (auto* v : stage)
						if (v)
							v->Release();
				for (auto* v : uavs)
					if (v)
						v->Release();
				for (auto* v : rtvs)
					if (v)
						v->Release();
			}
			SavedState(const SavedState&) = delete;
			SavedState& operator=(const SavedState&) = delete;

			ID3D11DeviceContext* ctx;
			winrt::com_ptr<ID3D11InputLayout> inputLayout;
			D3D11_PRIMITIVE_TOPOLOGY topology{};
			winrt::com_ptr<ID3D11VertexShader> vs;
			winrt::com_ptr<ID3D11PixelShader> ps;
			ID3D11ShaderResourceView* srvs[kStages][kSrvSlots]{};
			ID3D11UnorderedAccessView* uavs[kUavSlots]{};
			winrt::com_ptr<ID3D11SamplerState> sampler;
			winrt::com_ptr<ID3D11Buffer> cb;
			winrt::com_ptr<ID3D11RasterizerState> rasterizer;
			UINT viewportCount = 0;
			D3D11_VIEWPORT viewports[D3D11_VIEWPORT_AND_SCISSORRECT_OBJECT_COUNT_PER_PIPELINE]{};
			winrt::com_ptr<ID3D11BlendState> blend;
			FLOAT blendFactor[4]{};
			UINT sampleMask = 0;
			winrt::com_ptr<ID3D11DepthStencilState> depthStencil;
			UINT stencilRef = 0;
			ID3D11RenderTargetView* rtvs[D3D11_SIMULTANEOUS_RENDER_TARGET_COUNT]{};
			winrt::com_ptr<ID3D11DepthStencilView> dsv;
		};

		// Typeless engine formats need an explicit view format; take it from the
		// engine's own view of the source texture.
		HRESULT CreateReadView(ID3D11Device* a_device, ID3D11Texture2D* a_texture,
			ID3D11ShaderResourceView* a_engineSrv, ID3D11ShaderResourceView** a_out)
		{
			if (!a_engineSrv)
				return a_device->CreateShaderResourceView(a_texture, nullptr, a_out);
			D3D11_SHADER_RESOURCE_VIEW_DESC desc{};
			a_engineSrv->GetDesc(&desc);
			desc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;
			desc.Texture2D.MostDetailedMip = 0;
			desc.Texture2D.MipLevels = 1;
			return a_device->CreateShaderResourceView(a_texture, &desc, a_out);
		}

		void Throw(HRESULT a_hr)
		{
			if (FAILED(a_hr))
				throw std::runtime_error("HRESULT " + std::to_string(static_cast<long>(a_hr)));
		}
	}

	ID3D11ShaderResourceView* DRSUpscale::SourceFor(ID3D11Device* a_device, ID3D11DeviceContext* a_ctx,
		ID3D11Texture2D* a_texture, ID3D11ShaderResourceView* a_engineSrv, ID3D11Texture2D* a_engineCopy, ID3D11ShaderResourceView* a_engineCopySrv,
		ReadCopy& a_own)
	{
		if (a_engineCopy && a_engineCopySrv) {
			a_ctx->CopyResource(a_engineCopy, a_texture);
			return a_engineCopySrv;
		}
		D3D11_TEXTURE2D_DESC src{};
		a_texture->GetDesc(&src);
		if (a_own.texture) {
			D3D11_TEXTURE2D_DESC have{};
			a_own.texture->GetDesc(&have);
			if (have.Width != src.Width || have.Height != src.Height || have.Format != src.Format) {
				a_own.srv = nullptr;
				a_own.texture = nullptr;
			}
		}
		if (!a_own.texture) {
			D3D11_TEXTURE2D_DESC desc = src;
			desc.MipLevels = 1;
			desc.BindFlags = D3D11_BIND_SHADER_RESOURCE;
			desc.CPUAccessFlags = 0;
			desc.MiscFlags = 0;
			desc.Usage = D3D11_USAGE_DEFAULT;
			if (FAILED(a_device->CreateTexture2D(&desc, nullptr, a_own.texture.put())) ||
				FAILED(CreateReadView(a_device, a_own.texture.get(), a_engineSrv, a_own.srv.put()))) {
				SKSE::log::error("[DRS] could not create a read copy ({}x{} fmt {})", src.Width, src.Height,
					static_cast<int>(src.Format));
				a_own.srv = nullptr;
				a_own.texture = nullptr;
				return nullptr;
			}
			SKSE::log::info("[DRS] own read copy created ({}x{} fmt {})", src.Width, src.Height, static_cast<int>(src.Format));
		}
		if (src.MipLevels > 1)
			a_ctx->CopySubresourceRegion(a_own.texture.get(), 0, 0, 0, 0, a_texture, 0, nullptr);
		else
			a_ctx->CopyResource(a_own.texture.get(), a_texture);
		return a_own.srv.get();
	}

	bool DRSUpscale::EnsureResources(ID3D11Device* a_device)
	{
		if (ready)
			return true;
		if (failed || !a_device)
			return false;
		try {
			auto vsBlob = CompileShaderFromFile(L"Data\\Shaders\\Upscaling\\UpscaleVS.hlsl", "VSHADER", "vs_5_0");
			Throw(a_device->CreateVertexShader(vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), nullptr, vs.put()));
			auto depthBlob = CompileShaderFromFile(L"Data\\Shaders\\Upscaling\\DRSUpscalePS.hlsl", "DEPTH", "ps_5_0");
			Throw(a_device->CreatePixelShader(depthBlob->GetBufferPointer(), depthBlob->GetBufferSize(), nullptr, depthPS.put()));
			auto waterBlob = CompileShaderFromFile(L"Data\\Shaders\\Upscaling\\DRSUpscalePS.hlsl", "UNDERWATER", "ps_5_0");
			Throw(a_device->CreatePixelShader(waterBlob->GetBufferPointer(), waterBlob->GetBufferSize(), nullptr, underwaterPS.put()));

			D3D11_BUFFER_DESC cbDesc{};
			cbDesc.ByteWidth = sizeof(Constants);
			cbDesc.Usage = D3D11_USAGE_DYNAMIC;
			cbDesc.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
			cbDesc.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
			Throw(a_device->CreateBuffer(&cbDesc, nullptr, constants.put()));

			D3D11_SAMPLER_DESC sd{};
			sd.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
			sd.AddressU = sd.AddressV = sd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
			sd.ComparisonFunc = D3D11_COMPARISON_NEVER;
			sd.MaxLOD = D3D11_FLOAT32_MAX;
			Throw(a_device->CreateSamplerState(&sd, sampler.put()));

			D3D11_RASTERIZER_DESC rd{};
			rd.FillMode = D3D11_FILL_SOLID;
			rd.CullMode = D3D11_CULL_NONE;
			rd.DepthClipEnable = FALSE;
			Throw(a_device->CreateRasterizerState(&rd, rasterizer.put()));

			D3D11_BLEND_DESC bd{};
			bd.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
			bd.RenderTarget[1].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
			Throw(a_device->CreateBlendState(&bd, blend.put()));

			// Like CS: always write depth, leave stencil untouched.
			D3D11_DEPTH_STENCIL_DESC dd{};
			dd.DepthEnable = TRUE;
			dd.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ALL;
			dd.DepthFunc = D3D11_COMPARISON_ALWAYS;
			dd.StencilEnable = FALSE;
			Throw(a_device->CreateDepthStencilState(&dd, depthWrite.put()));

			ready = true;
			SKSE::log::info("[DRS] upscale shaders ready (UpscaleVS + DRSUpscalePS DEPTH/UNDERWATER)");
		} catch (const std::exception& e) {
			failed = true;
			SKSE::log::error("[DRS] upscale shader init failed - engine buffers stay at render size ({})", e.what());
		}
		return ready;
	}

	void DRSUpscale::SetConstants(ID3D11DeviceContext* a_ctx, float a_scaleX, float a_scaleY,
		float a_jitterX, float a_jitterY, std::uint32_t a_width, std::uint32_t a_height)
	{
		const float w = static_cast<float>(std::max(1u, a_width));
		const float h = static_cast<float>(std::max(1u, a_height));
		Constants c{};
		c.uvScale[0] = a_scaleX;
		c.uvScale[1] = a_scaleY;
		c.jitterUV[0] = a_jitterX / w;
		c.jitterUV[1] = a_jitterY / h;
		c.uvMax[0] = a_scaleX - 0.5f / w;
		c.uvMax[1] = a_scaleY - 0.5f / h;
		D3D11_MAPPED_SUBRESOURCE m{};
		if (SUCCEEDED(a_ctx->Map(constants.get(), 0, D3D11_MAP_WRITE_DISCARD, 0, &m))) {
			std::memcpy(m.pData, &c, sizeof(c));
			a_ctx->Unmap(constants.get(), 0);
		}
	}

	bool DRSUpscale::UpscaleEngineBuffers(ID3D11Device* a_device, ID3D11DeviceContext* a_ctx,
		float a_scaleX, float a_scaleY, float a_jitterX, float a_jitterY)
	{
		auto* renderer = RE::BSGraphics::Renderer::GetSingleton();
		if (!renderer || !a_ctx || !EnsureResources(a_device))
			return false;

		auto& ds = renderer->GetDepthStencilData().depthStencils;
		auto& depth = ds[RE::RENDER_TARGETS_DEPTHSTENCIL::kMAIN];
		auto& depthCopy = ds[RE::RENDER_TARGETS_DEPTHSTENCIL::kMAIN_COPY];
		auto& rts = renderer->GetRuntimeData().renderTargets;
		auto& refraction = rts[RE::RENDER_TARGETS::kREFRACTION_NORMALS];
		auto& saoZ = rts[RE::RENDER_TARGETS::kSAO_CAMERAZ];
		auto& water = rts[RE::RENDER_TARGETS::kUNDERWATER_MASK];

		static bool missingLogged = false;
		if (!depth.texture || !depth.views[0] || !depthCopy.texture || !depthCopy.depthSRV ||
			!refraction.texture || !refraction.RTV || !saoZ.RTV || !water.texture || !water.RTV) {
			if (!missingLogged) {
				missingLogged = true;
				SKSE::log::warn("[DRS] engine buffers incomplete (depth={} copy={} refr={}/{} sao={} water={}/{}) - skipping upscale",
					depth.texture != nullptr, depthCopy.texture != nullptr, refraction.texture != nullptr,
					refraction.textureCopy != nullptr, saoZ.RTV != nullptr, water.texture != nullptr, water.textureCopy != nullptr);
			}
			return false;
		}

		D3D11_TEXTURE2D_DESC depthDesc{};
		depth.texture->GetDesc(&depthDesc);
		D3D11_TEXTURE2D_DESC waterDesc{};
		water.texture->GetDesc(&waterDesc);

		SavedState saved(a_ctx);

		a_ctx->IASetInputLayout(nullptr);
		a_ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
		a_ctx->VSSetShader(vs.get(), nullptr, 0);
		a_ctx->RSSetState(rasterizer.get());
		a_ctx->OMSetBlendState(blend.get(), nullptr, 0xffffffff);
		ID3D11SamplerState* s = sampler.get();
		a_ctx->PSSetSamplers(0, 1, &s);
		ID3D11Buffer* b = constants.get();
		a_ctx->PSSetConstantBuffers(0, 1, &b);

		// Copy the sources: one texture cannot be read and written at the same time.
		a_ctx->OMSetRenderTargets(0, nullptr, nullptr);
		a_ctx->CopyResource(depthCopy.texture, depth.texture);
		ID3D11ShaderResourceView* refractionSrc = SourceFor(a_device, a_ctx, refraction.texture, refraction.SRV, refraction.textureCopy, refraction.SRVCopy, refractionCopy);
		ID3D11ShaderResourceView* waterSrc = SourceFor(a_device, a_ctx, water.texture, water.SRV, water.textureCopy, water.SRVCopy, waterCopy);
		if (!refractionSrc || !waterSrc)
			return false;

		// 1) depth + refraction normals + SAO camera Z at full size
		D3D11_VIEWPORT vp{ 0.0f, 0.0f, static_cast<float>(depthDesc.Width), static_cast<float>(depthDesc.Height), 0.0f, 1.0f };
		a_ctx->RSSetViewports(1, &vp);
		SetConstants(a_ctx, a_scaleX, a_scaleY, a_jitterX, a_jitterY, depthDesc.Width, depthDesc.Height);
		a_ctx->OMSetDepthStencilState(depthWrite.get(), 0);
		ID3D11ShaderResourceView* depthSrvs[2] = { refractionSrc, depthCopy.depthSRV };
		a_ctx->PSSetShaderResources(0, 2, depthSrvs);
		ID3D11RenderTargetView* depthRtvs[2] = { refraction.RTV, saoZ.RTV };
		a_ctx->OMSetRenderTargets(2, depthRtvs, depth.views[0]);
		a_ctx->PSSetShader(depthPS.get(), nullptr, 0);
		a_ctx->Draw(3, 0);

		// 2) underwater mask (half resolution; jitter in its own texels)
		ID3D11ShaderResourceView* nullSrvs[2] = { nullptr, nullptr };
		a_ctx->PSSetShaderResources(0, 2, nullSrvs);
		D3D11_VIEWPORT wvp{ 0.0f, 0.0f, static_cast<float>(waterDesc.Width), static_cast<float>(waterDesc.Height), 0.0f, 1.0f };
		a_ctx->RSSetViewports(1, &wvp);
		const float waterJx = a_jitterX * static_cast<float>(waterDesc.Width) / static_cast<float>(std::max(1u, depthDesc.Width));
		const float waterJy = a_jitterY * static_cast<float>(waterDesc.Height) / static_cast<float>(std::max(1u, depthDesc.Height));
		SetConstants(a_ctx, a_scaleX, a_scaleY, waterJx, waterJy, waterDesc.Width, waterDesc.Height);
		a_ctx->OMSetDepthStencilState(nullptr, 0);
		ID3D11ShaderResourceView* waterSrv[1] = { waterSrc };
		a_ctx->PSSetShaderResources(0, 1, waterSrv);
		ID3D11RenderTargetView* waterRtv[1] = { water.RTV };
		a_ctx->OMSetRenderTargets(1, waterRtv, nullptr);
		a_ctx->PSSetShader(underwaterPS.get(), nullptr, 0);
		a_ctx->Draw(3, 0);

		a_ctx->PSSetShaderResources(0, 2, nullSrvs);
		a_ctx->OMSetRenderTargets(0, nullptr, nullptr);

		static bool firstLogged = false;
		if (!firstLogged) {
			firstLogged = true;
			SKSE::log::info("[DRS] engine buffers upscaled: scale ({:.3f},{:.3f}) depth {}x{} water {}x{} jitter ({:.3f},{:.3f})",
				a_scaleX, a_scaleY, depthDesc.Width, depthDesc.Height, waterDesc.Width, waterDesc.Height, a_jitterX, a_jitterY);
		}
		return true;
	}
}
