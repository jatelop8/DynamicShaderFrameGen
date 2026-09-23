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

// v0.62: hang forensics (watchdog thread + atomic frame stamps)
#include <atomic>
#include <thread>
// v0.81: std::string is used as a return type by DescribePresentThreads().
#include <string>

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

	// v0.73: the watchdog log path, resolved once at plugin load (see
	// InitWatchdogLogPath in DX12SwapChain.cpp) and reused by DllMain during
	// process detach.
	void InitWatchdogLogPath();
	const char* WatchdogLogPath();

	// v1.03b: DLSS-G in-call state, published by the present thread and read by the
	// watchdog thread. It lives at namespace scope because two translation units need
	// it (Streamline.cpp sets it around slDLSSGSetOptions, DX12SwapChain.cpp names it
	// in the watchdog line). Reading m_stage from the watchdog would be a data race on
	// a member the render thread writes every frame; this atomic is the safe channel.
	// The 18:23 freeze was investigated for two days behind a stage= that could only
	// say "d3d11 Wait" - it named the fence wait, never the call that never returned.
	extern std::atomic<int> g_inSetOptions;

	// v1.04b: steady_clock millisecond stamp taken the instant a blocking Present is
	// entered, published for the watchdog. Same reasoning and the same scope as
	// g_inSetOptions above: the 19:04 run read "stage=d3d11 Wait" for 19.7 s because
	// that name was the last one m_stage held before Present, not the call that
	// stalled. Printing this stamp's age names Present() itself, with no inference.
	extern std::atomic<long long> g_presentEnteredMs;
	class DX12SwapChain
	{
	public:
		winrt::com_ptr<ID3D12Device> d3d12Device;
		winrt::com_ptr<ID3D12CommandQueue> commandQueue;
		// v0.33：DLSSG 三缓冲（frameIndex 0-2）——allocator/list 与 buffer 数对齐
		winrt::com_ptr<ID3D12CommandAllocator> commandAllocators[3];
		winrt::com_ptr<ID3D12GraphicsCommandList4> commandLists[3];

		IDXGISwapChain4* swapChain = nullptr;

		DXGI_SWAP_CHAIN_DESC1 swapChainDesc;

		ffx::Context ffxSwapChainContext;  // FFX FG swapchain 上下文（帧缓冲管理）

		bool dlssgMode = false;  // v0.3：NVIDIA DLSSG 模式（普通 swapchain + SL 插帧）

		// v0.52：构建本 swapchain 时实际生效的 Provider。-1 = 尚未构建。
		// Provider 只在这里被消费（决定 dlssgMode / BufferCount / D3D12 proxy 路径），
		// 运行中改 INI 或 GUI 都不会重建 swapchain —— GUI 用它显示 "PENDING RESTART"。
		int providerAtCreate = -1;

		WrappedResource* swapChainBufferWrapped = nullptr;
		WrappedResource* colorOutWrapped = nullptr;   // v0.7.5：DLSS 超分独立输出（CS 同款，防 in-place 失效）
		WrappedResource* nrOutWrapped = nullptr;      // v0.8：DLSS-NR 输出（NGX 写这里，再拷贝呈现）
		WrappedResource* depthWrapped = nullptr;   // v0.3：DLSSG 深度共享纹理（每帧从引擎 kMAIN 拷贝）
		WrappedResource* mvecWrapped = nullptr;    // v0.3：DLSSG 运动矢量共享纹理（每帧从引擎 kMOTION_VECTOR 拷贝）

		winrt::com_ptr<ID3D11Device5> d3d11Device;
		winrt::com_ptr<ID3D11DeviceContext4> d3d11Context;

		winrt::com_ptr<ID3D11Fence> d3d11Fence;
		winrt::com_ptr<ID3D12Fence> d3d12Fence;

		// v0.33：DLSSG 三缓冲（SL pacer 余量），FSR3 双缓冲
		winrt::com_ptr<ID3D12Resource> swapChainBuffers[3];

		UINT frameIndex = 0;
		UINT64 fenceValue = 0;

		// v1.03b: how long a frame may wait for the D3D12 queue before the wait
		// is abandoned and the frame dropped. 250 ms is ~40 intended frames at
		// 160 Hz and 25x the rejected-frame cost measured in the 18:23 log
		// (capUs=6289 => 6.29 ms), so it cannot fire on a merely slow frame -
		// only on the parked one this guard was written for.
		static constexpr std::uint32_t kFenceWaitTimeoutMs = 250;

		// v0.5.5: Present stage marker for exception pinpointing (black screen debug)
		const char* m_stage = "init";
		const char* lastStage() const { return m_stage; }

		// v1.03b: a bounded replacement for ID3D11DeviceContext4::Wait.
		//
		// That call has no timeout, so a D3D12 queue that never reaches the
		// fence parks the render thread forever - which is precisely the
		// 2026-09-18 18:23 freeze: silent=19681 ms, stage=d3d11 Wait, frames=1,
		// and a 19945.3 ms frame in the main log. Polling the D3D12 fence
		// instead costs one GetCompletedValue per millisecond of hitch and turns
		// an unbounded stall into a dropped frame plus a log line that names the
		// fence, its value, the value that was actually reached and how long it
		// took. Returns true if the fence was reached.
		bool WaitFenceBounded(UINT64 a_fenceValue, std::uint32_t a_timeoutMs);

		// v0.62: hang forensics. The 21:40 run stopped writing at 21:40:44.4 -
		// the [XRAY] heartbeat, the 2 s FPS probe and Transfusion's 5 s startup
		// heartbeat all went silent together - and no line said WHICH call the
		// render thread was parked in. The watchdog keeps writing from outside the
		// render thread, and lastStage() names the call it is stuck on.
		// lastStage() already existed (v0.5.5) but was only ever read by an
		// exception handler, so a hang produced nothing at all.
		// v0.74: read by the watchdog, written by the sampler thread and by
		// Present(). These are the fields that make a GPU-side stall visible
		// while every CPU-side field still looks healthy: the 07:11 run kept
		// silent at 5-27 ms for 50 s while the D3D12 queue never advanced.
		//   g_queuedDepth  frames submitted with ExecuteCommandLists and not
		//                  yet retired by the fence. > 3 means the CPU ran
		//                  ahead of the GPU, i.e. Present stopped providing
		//                  backpressure.
		//   g_lastPresentCount / g_flipDesync  does the swap chain actually
		//                  flip, and does frameIndex still agree with the
		//                  index DXGI reports.
		std::atomic<unsigned long long> g_queuedDepth{ 0 };
		std::atomic<unsigned long long> g_lastPresentCount{ 0 };
		std::atomic<unsigned long long> g_flipDesync{ 0 };

		std::atomic<std::uint64_t> frameCounter{ 0 };
		std::atomic<long long> lastFrameEndMs{ 0 };
		std::atomic<bool> watchdogStop{ false };

		// v0.81 -- present-thread census (observation only; v0.80's latch was
		// reverted). v0.80 refused every thread but the first one to enter
		// Present(), on the assumption that two ids meant two presenters fighting
		// over one swap chain. The 09:31 run disproved it: the "owner" had
		// presented ONCE (it is the init thread) while the refused thread had
		// presented 300+ times (it is the engine render thread). Refusing it
		// stopped every real present - the freeze v0.80 was supposed to cure.
		// So: observe, count, report, and never refuse.
		struct PresentThreadStat
		{
			std::uint32_t tid = 0;
			std::uint64_t frames = 0;
			long long firstMs = 0;
			long long lastMs = 0;
		};
		static constexpr int kPresentThreadMax = 8;
		PresentThreadStat presentThreads[kPresentThreadMax];
		std::atomic<int> presentThreadCount{ 0 };
		std::uint64_t presentCensusFrames = 0;
		void CensusPresentThread();
		std::string DescribePresentThreads();

		// v0.79 -- menu-guard decoupling.
		// The MFG multiplier ladder used to live entirely behind Present()'s
		// else-if branch, which the menu guard short-circuits. Exposed here so
		// Present() can run the probe on EVERY frame and only then decide.
		std::uint64_t menuBlockedFrames = 0;
		std::uint64_t menuUnblockedFrames = 0;
		std::uint64_t mfgWarned = 0;
		void StartWatchdog();
		// v0.73: samples the GPU timeline from its own thread, so the watchdog never
		// has to enter the driver itself. See the definition for the two readings.
		void StartGpuSampler();

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
		// ---- v1.22 PIXEL PROBE ----
		// See PixelProbeTick() in the .cpp for the full argument. In one line: every
		// witness this file already has (Present's return, presentAge, dsync, the
		// presented-per-real-frame ratio) reports that a flip HAPPENED, and not one
		// of them can see that the same picture was flipped again. The 00:30 run
		// measured ratio = 4.00 with dsync = 0 and presentAge 5-8 ms while the player
		// reported a frozen screen, which is the gap this closes.
		void PixelProbeTick();
		winrt::com_ptr<ID3D11Texture2D> pixelProbeStaging;
		D3D11_BOX pixelProbeBox{};
		std::uint32_t pixelProbeWidth = 0;
		std::uint32_t pixelProbeHeight = 0;
		std::uint64_t pixelProbeLastMs = 0;
		std::uint64_t pixelProbeLastHash = 0;
		std::uint32_t pixelProbeSamples = 0;
		std::uint32_t pixelProbeChanged = 0;
		std::uint32_t pixelProbeUnchanged = 0;
		std::uint32_t pixelProbeStreak = 0;
		std::uint32_t pixelProbeMaxStreak = 0;
		bool pixelProbeReady = false;
		bool pixelProbeDisabled = false;
		// v1.23 -- two-phase sampling state. v1.22 copied and mapped in the same
		// call, so the Map never once succeeded and the probe logged nothing at all
		// (00:58 run: armed at 00:58:14.810, zero samples in 39 s).
		bool pixelProbeCopyPending = false;      // a copy for the NEXT tick is in flight
		bool pixelProbeSelfWitnessFired = false; // the "armed but silent" alarm
		std::uint32_t pixelProbeSrcW = 0;        // size we armed against; a change rearms
		std::uint32_t pixelProbeSrcH = 0;
		std::uint32_t pixelProbeDropped = 0;     // copy landed too late to read
		// A hash streak only means "frozen" if the camera was moving: with a still
		// camera DLSS-G's interpolated output is legitimately identical to the real
		// frame, so the streak alone cannot separate a still picture from a stale one.
		std::uint32_t pixelProbeMovedDuringStreak = 0;
		// v1.26 -- oscillation state. A flicker is neither a change nor a freeze:
		// the presented image cycles through a small set of states, so the hash
		// differs on every sample and the "changed" counter calls it healthy.
		// What separates it from real content is that the set stays tiny and that
		// its brightness swings. 8 samples at 2 Hz = a 4 s window.
		std::uint64_t pixelProbeRingHash[8] = {};
		float pixelProbeRingLum[8] = {};
		std::uint32_t pixelProbeRingFill = 0;
		std::uint32_t pixelProbeRingAt = 0;
		float pixelProbeLum = 0.0f;
		std::uint32_t pixelProbeFlickerFired = 0;
		std::uint64_t pixelProbeArmedMs = 0;

		// ---- v1.33 BACK-BUFFER PROBE ----
		// The 19:11 run forced this. Two instruments disagreed for 28 s: [PIXEL]
		// (colorOut -- the D3D11 copy of what we hand TO DLSS-G) took 74 distinct
		// values while the [SCREEN] capture kept showing 3. That puts the break
		// between them, and exactly one object sits between them that no
		// instrument in this project has ever read: the D3D12 swap-chain back
		// buffer DXGI actually flips. This probe hashes it.
		//
		// Three channels then read side by side, each compared only against its
		// own history:
		//   [PIXEL]  colorOut  = engine image (we hand this TO DLSS-G)
		//   [BACKBUF] back buffer = the frame we ask DXGI to present
		//   [SCREEN] desktop capture = what the panel displays
		// A picture that changes in the first and not the third is not enough to
		// localise anything; all three collapse the question to one of two edges.
		//
		// Same two-phase design as PixelProbeTick, for the same reason (v1.22
		// copied and mapped in one call and never produced a single sample): the
		// copy is recorded on the frame's own command list just before it closes,
		// and harvested on a LATER tick once the fence reports that frame done.
		// Nothing here ever waits; a sample that cannot be read is dropped and
		// counted, never retried inside the same tick.
		void BackBufferProbeHarvest();
		void BackBufferProbeIssue(ID3D12GraphicsCommandList* a_cmdList, ID3D12Resource* a_backBuffer,
			UINT a_frameIndex);
		winrt::com_ptr<ID3D12Resource> backProbeReadback;
		D3D12_PLACED_SUBRESOURCE_FOOTPRINT backProbeFootprint{};
		UINT backProbeW = 0;                 // pixels hashed per row (padding excluded)
		UINT backProbeH = 0;                 // rows hashed
		std::uint32_t backProbeBytesPerPx = 4;
		std::uint64_t backProbeLastMs = 0;
		std::uint64_t backProbeLastHash = 0;
		std::uint64_t backProbeFenceAtCopy = 0;   // fence value whose completion carries the copy
		std::uint64_t backProbePendingSinceMs = 0;
		// L39, the rule this project had to learn the hard way: an instrument that
		// produces nothing looks exactly like a healthy one. Arm time plus a
		// one-shot alarm, same as the D3D11 probe has.
		std::uint64_t backProbeArmedMs = 0;
		// v1.34: the self-witness below has to measure "we never got a chance to
		// sample", not "no sample 15 s after the arming". On the 21:26 run it fired
		// 20 s after arming while the loading screen was still up and Present had not
		// been entered once -- it accused a probe that could not have produced
		// anything. The clock now starts at the first Present entry, which is the
		// first moment a sample is even possible.
		std::uint64_t backProbeFirstPresentMs = 0;
		// v1.34: WHICH of the swap chain's buffers this sample came from. The back
		// buffer is an array and consecutive frames use different slots, so a series
		// of samples reading a different slot each time shows "3 distinct hashes"
		// while every slot is in fact frozen -- and the reverse can hide a rotation.
		// Without this index the 3-value pattern cannot be told from slot rotation,
		// which is exactly the ambiguity that made the previous run's [BACKBUF]
		// evidence unreadable. 0xFFFFFFFF = no sample taken yet.
		UINT backProbeFrameIndex = 0xFFFFFFFFu;
		bool backProbeSelfWitnessFired = false;
		std::uint32_t backProbeSamples = 0;
		std::uint32_t backProbeChanged = 0;
		std::uint32_t backProbeUnchanged = 0;
		std::uint32_t backProbeDropped = 0;        // fence never reported the copy as done
		std::uint32_t backProbeDeferred = 0;       // a copy was already in flight: skipped, not queued
		std::uint32_t backProbeStreak = 0;
		std::uint32_t backProbeMaxStreak = 0;
		bool backProbeReady = false;
		bool backProbeDisabled = false;
		bool backProbePending = false;
		UINT backProbeSrcW = 0;
		UINT backProbeSrcH = 0;
	};
}
