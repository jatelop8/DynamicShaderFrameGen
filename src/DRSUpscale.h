// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.

#pragma once

// Linux build (dlss-quality): engine DRS follow-up after the DLSS evaluation.
// With quality modes 1-4 Skyrim renders depth, refraction normals, SAO camera Z and
// the underwater mask only into the render sub-rect. After Community Shaders
// Upscaling::UpscaleDepth (GPL-3.0), this class stretches them to full size before
// the post-processing hook sets the DRS lock and post-processing and ENB read the
// full textures.

#include <d3d11.h>
#include <winrt/base.h>

#include <cstdint>

namespace FrameGen
{
	class DRSUpscale
	{
	public:
		// a_scale*: render sub-rect / full size; a_jitter*: this frame's jitter in render
		// pixels. Returns true when every buffer was upscaled. The context's D3D11 state
		// is the same afterwards as before.
		bool UpscaleEngineBuffers(ID3D11Device* a_device, ID3D11DeviceContext* a_ctx,
			float a_scaleX, float a_scaleY, float a_jitterX, float a_jitterY);

	private:
		struct Constants
		{
			float uvScale[2];
			float jitterUV[2];
			float uvMax[2];
			float pad[2];
		};

		// A private read copy of an engine render target. The engine only allocates
		// textureCopy for some targets (in vanilla LoreRim not for refraction normals
		// or the underwater mask), so the copy is made here when it is missing.
		struct ReadCopy
		{
			winrt::com_ptr<ID3D11Texture2D> texture;
			winrt::com_ptr<ID3D11ShaderResourceView> srv;
		};
		static ID3D11ShaderResourceView* SourceFor(ID3D11Device* a_device, ID3D11DeviceContext* a_ctx,
			ID3D11Texture2D* a_texture, ID3D11ShaderResourceView* a_engineSrv, ID3D11Texture2D* a_engineCopy, ID3D11ShaderResourceView* a_engineCopySrv,
			ReadCopy& a_own);

		bool EnsureResources(ID3D11Device* a_device);
		void SetConstants(ID3D11DeviceContext* a_ctx, float a_scaleX, float a_scaleY,
			float a_jitterX, float a_jitterY, std::uint32_t a_width, std::uint32_t a_height);

		bool ready = false;
		bool failed = false;
		winrt::com_ptr<ID3D11VertexShader> vs;
		winrt::com_ptr<ID3D11PixelShader> depthPS;
		winrt::com_ptr<ID3D11PixelShader> underwaterPS;
		winrt::com_ptr<ID3D11Buffer> constants;
		winrt::com_ptr<ID3D11SamplerState> sampler;
		winrt::com_ptr<ID3D11RasterizerState> rasterizer;
		winrt::com_ptr<ID3D11BlendState> blend;
		winrt::com_ptr<ID3D11DepthStencilState> depthWrite;
		ReadCopy refractionCopy;
		ReadCopy waterCopy;
	};
}
