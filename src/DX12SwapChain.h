// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
// Derived from open-source projects (all GPL-3.0):
//   - Skyrim Community Shaders (https://github.com/doodlum/skyrim-community-shaders)
//   - ENBFrameGeneration (https://github.com/doodlum/ENBFrameGeneration)
// Other components: Dear ImGui / CommonLibSSE-NG / Microsoft Detours (MIT).

#pragma once

// DX12SwapChain.h —— D3D12 Proxy（精简自 Community Shaders（GPL-3.0））
// WrappedResource：D3D11 共享纹理 ↔ D3D12 资源互操作
// DXGISwapChainProxy：游戏拿到的假 swapchain（接口转发 + Present 拦截）
// DX12SwapChain：D3D12 设备/队列/FFX FG swapchain/双缓冲/共享 Fence

#include <Windows.Foundation.h>
#include <stdio.h>
#include <winrt/base.h>
#include <wrl/client.h>
#include <wrl/wrappers/corewrappers.h>

#include <d3d11_4.h>
#include <d3d12.h>

#include <directx/d3dx12.h>

#include <FidelityFX/api/include/dx12/ffx_api_dx12.hpp>
#include <FidelityFX/framegeneration/include/dx12/ffx_api_framegeneration_dx12.hpp>

namespace FrameGen
{
	class WrappedResource
	{
	public:
		WrappedResource(D3D11_TEXTURE2D_DESC a_texDesc, ID3D11Device5* a_d3d11Device, ID3D12Device* a_d3d12Device);
		~WrappedResource();

		ID3D11Texture2D* resource11 = nullptr;
		winrt::com_ptr<ID3D12Resource> resource;
		// v0.5：不再创建 srv/uav/rtv（深度/typeless 格式建视图会抛异常，且零使用点）；
		// 只做 D3D11 共享纹理 ↔ D3D12 同底层内存（CopyResource 目标 / DLSSG 读）
		// v0.5.7（CS 方案）：depth 共享纹理自建 R32_FLOAT 非深度格式，按 BindFlags 建
		// srv/rtv（depth shader 拷贝需要 RTV；mvec 拷贝无需视图但保留 srv 备用）
		ID3D11ShaderResourceView* srv = nullptr;
		ID3D11RenderTargetView* rtv = nullptr;
		// v0.7.6：UAV 视图——DLSS 超分输出（colorOut）要求（NGX 以 UAV 写入，
		// 缺则 RWFlagMissing → 输出永不被写 → 全黑）
		ID3D11UnorderedAccessView* uav = nullptr;
	};

	struct DXGISwapChainProxy : IDXGISwapChain
	{
	public:
		DXGISwapChainProxy(IDXGISwapChain4* a_swapChain);

		IDXGISwapChain4* swapChain;

		// v0.7.10：GetDesc 返回渲染尺寸——Skyrim 渲染分辨率从 swapchain desc 初始化，
		// 不改则引擎仍按输出 4K 渲染（DRS 无效时画面裁剪 1/4）
		std::uint32_t renderWidth = 0;
		std::uint32_t renderHeight = 0;

		/****IUnknown****/
		virtual HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** ppvObj) override;
		virtual ULONG STDMETHODCALLTYPE AddRef() override;
		virtual ULONG STDMETHODCALLTYPE Release() override;

		/****IDXGIObject****/
		virtual HRESULT STDMETHODCALLTYPE SetPrivateData(_In_ REFGUID Name, UINT DataSize, _In_reads_bytes_(DataSize) const void* pData) override;
		virtual HRESULT STDMETHODCALLTYPE SetPrivateDataInterface(_In_ REFGUID Name, _In_opt_ const IUnknown* pUnknown) override;
		virtual HRESULT STDMETHODCALLTYPE GetPrivateData(_In_ REFGUID Name, _Inout_ UINT* pDataSize, _Out_writes_bytes_(*pDataSize) void* pData) override;
		virtual HRESULT STDMETHODCALLTYPE GetParent(_In_ REFIID riid, _COM_Outptr_ void** ppParent) override;

		/****IDXGIDeviceSubObject****/
		virtual HRESULT STDMETHODCALLTYPE GetDevice(_In_ REFIID riid, _COM_Outptr_ void** ppDevice) override;

		/****IDXGISwapChain****/
		virtual HRESULT STDMETHODCALLTYPE Present(UINT SyncInterval, UINT Flags) override;
		virtual HRESULT STDMETHODCALLTYPE GetBuffer(UINT Buffer, _In_ REFIID riid, _COM_Outptr_ void** ppSurface) override;
		virtual HRESULT STDMETHODCALLTYPE SetFullscreenState(BOOL Fullscreen, _In_opt_ IDXGIOutput* pTarget) override;
		virtual HRESULT STDMETHODCALLTYPE GetFullscreenState(_Out_opt_ BOOL* pFullscreen, _COM_Outptr_opt_result_maybenull_ IDXGIOutput** ppTarget) override;
		virtual HRESULT STDMETHODCALLTYPE GetDesc(_Out_ DXGI_SWAP_CHAIN_DESC* pDesc) override;
		virtual HRESULT STDMETHODCALLTYPE ResizeBuffers(UINT BufferCount, UINT Width, UINT Height, DXGI_FORMAT NewFormat, UINT SwapChainFlags) override;
		virtual HRESULT STDMETHODCALLTYPE ResizeTarget(_In_ const DXGI_MODE_DESC* pNewTargetParameters) override;
		virtual HRESULT STDMETHODCALLTYPE GetContainingOutput(_COM_Outptr_ IDXGIOutput** ppOutput) override;
		virtual HRESULT STDMETHODCALLTYPE GetFrameStatistics(_Out_ DXGI_FRAME_STATISTICS* pStats) override;
		virtual HRESULT STDMETHODCALLTYPE GetLastPresentCount(_Out_ UINT* pLastPresentCount) override;
	};

	class DX12SwapChain
	{
	public:
		winrt::com_ptr<ID3D12Device> d3d12Device;
		winrt::com_ptr<ID3D12CommandQueue> commandQueue;
		winrt::com_ptr<ID3D12CommandAllocator> commandAllocators[2];
		winrt::com_ptr<ID3D12GraphicsCommandList4> commandLists[2];

		IDXGISwapChain4* swapChain = nullptr;

		DXGI_SWAP_CHAIN_DESC1 swapChainDesc;

		ffx::Context ffxSwapChainContext;  // FFX FG swapchain 上下文（帧缓冲管理）

		bool dlssgMode = false;  // v0.3：NVIDIA DLSSG 模式（普通 swapchain + SL 插帧）

		WrappedResource* swapChainBufferWrapped = nullptr;
		WrappedResource* colorOutWrapped = nullptr;   // v0.7.5：DLSS 超分独立输出（CS 同款，防 in-place 失效）
		WrappedResource* depthWrapped = nullptr;   // v0.3：DLSSG 深度共享纹理（每帧从引擎 kMAIN 拷贝）
		WrappedResource* mvecWrapped = nullptr;    // v0.3：DLSSG 运动矢量共享纹理（每帧从引擎 kMOTION_VECTOR 拷贝）

		winrt::com_ptr<ID3D11Device5> d3d11Device;
		winrt::com_ptr<ID3D11DeviceContext4> d3d11Context;

		winrt::com_ptr<ID3D11Fence> d3d11Fence;
		winrt::com_ptr<ID3D12Fence> d3d12Fence;

		winrt::com_ptr<ID3D12Resource> swapChainBuffers[2];

		UINT frameIndex = 0;
		UINT64 fenceValue = 0;

		// v0.5.5: Present stage marker for exception pinpointing (black screen debug)
		const char* m_stage = "init";
		const char* lastStage() const { return m_stage; }

		DXGISwapChainProxy* swapChainProxy = nullptr;

		void CreateD3D12Device(IDXGIAdapter* a_adapter);
		void CreateSwapChain(IDXGIAdapter* adapter, DXGI_SWAP_CHAIN_DESC swapChainDesc, bool a_enableFrameGeneration, bool a_dlssgMode, std::uint32_t a_qualityMode);
		void CreateInterop();

		DXGISwapChainProxy* GetSwapChainProxy();
		void SetD3D11Device(ID3D11Device* a_d3d11Device);
		void SetD3D11DeviceContext(ID3D11DeviceContext* a_d3d11Context);

		HRESULT Present(UINT SyncInterval, UINT Flags);
		HRESULT GetDevice(_In_ REFIID riid, _COM_Outptr_ void** ppDevice);

		// v0.5.7（CS 方案）：depth shader 拷贝（引擎 D32_FLOAT → R32_FLOAT 共享纹理）
		void CopyDepthToShared(ID3D11ShaderResourceView* a_depthSRV, ID3D11RenderTargetView* a_depthRTV);
		winrt::com_ptr<ID3D11VertexShader> upscaleVS;
		winrt::com_ptr<ID3D11PixelShader> copyDepthPS;
		winrt::com_ptr<ID3D11RasterizerState> upscaleRasterizerState;
		winrt::com_ptr<ID3D11BlendState> upscaleBlendState;
		bool depthCopyReady = false;
		HANDLE GetFrameLatencyWaitableObject();
		// v0.7.8：共享 VS/光栅/混合状态（depth/mvec/color 拷贝三处共用）
		void EnsureUpscaleStates();

		// v0.7.8：渲染分辨率缩放（DRS 等效）——渲染分辨率 = 输出 × QualityMode 比例，
		// DLSS 把低分辨率画面放大回输出分辨率（超分才有效果；不降渲染则超分无放大可做）。
		float renderScaleX = 1.0f;
		float renderScaleY = 1.0f;
		std::uint32_t renderWidth = 0;
		std::uint32_t renderHeight = 0;

		// v0.7.8：mvec 采样放大拷贝（引擎 mvec 渲染尺寸 → 4K 共享纹理，FSR3 FG 用）
		void CopyMvecToShared(ID3D11ShaderResourceView* a_mvecSRV, ID3D11RenderTargetView* a_mvecRTV);
		winrt::com_ptr<ID3D11PixelShader> copyMvecPS;
		bool mvecCopyReady = false;
		bool mvecCopyFailed = false;

		// v0.7.8：color 采样放大拷贝（超分失败兜底：游戏画面渲染尺寸 → colorOut 4K）
		void CopyColorToShared(ID3D11ShaderResourceView* a_colorSRV, ID3D11RenderTargetView* a_colorRTV);
		winrt::com_ptr<ID3D11PixelShader> copyColorPS;
		bool colorCopyReady = false;
		bool colorCopyFailed = false;
	};
}
