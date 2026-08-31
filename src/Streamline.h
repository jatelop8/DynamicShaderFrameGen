// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
// Derived from open-source projects (all GPL-3.0):
//   - Skyrim Community Shaders (https://github.com/doodlum/skyrim-community-shaders)
//   - ENBFrameGeneration (https://github.com/doodlum/ENBFrameGeneration)
// Other components: Dear ImGui / CommonLibSSE-NG / Microsoft Detours (MIT).

#pragma once

// Streamline DLSS 集成（精简自 Community Shaders Streamline.cpp（GPL-3.0））
// 只保留非 VR DLSS 路径：加载 sl.interposer.dll → slInit → slSetD3DDevice →
// 每帧 slSetConstants + slSetTag + slEvaluateFeature（DLSS 超分 + 帧生成）

#include <d3d11_4.h>
#include <d3d12.h>

#define NV_WINDOWS

#pragma warning(push)
#pragma warning(disable : 4471)
#include <sl.h>
#include <sl_consts.h>
#include <sl_core_types.h>
#include <sl_dlss.h>
#include <sl_dlss_g.h>
#include <sl_matrix_helpers.h>
#include <sl_reflex.h>
#include <sl_version.h>
#pragma warning(pop)

// 前置声明（避免与 FrameGen.h 循环 include）
namespace FrameGen
{
	struct Settings;
	struct FrameBuffer;
}

namespace FrameGen
{
	class Streamline
	{
	public:
		Streamline() = default;

		static constexpr const wchar_t* PluginDir = L"Data\\Shaders\\Upscaling\\Streamline";

		bool initialized = false;
		bool triedInitialization = false;
		bool featureDLSS = false;
		bool featureDLSSG = false;   // v0.3：NVIDIA DLSSG 插帧（D3D12 路径）
		// v0.32（对齐 open-shaders）：Reflex/PCL 运行时可用标志（RSYNC pacing 必需）
		bool featureReflex = false;
		bool featurePCL = false;
		bool isRTXBelow40series = false;

		// v0.3：SL 渲染 API（DLSSG 需 D3D12；FSR3 模式用 D3D11）
		bool useD3D12 = false;

		sl::ViewportHandle viewport{ 0 };
		sl::FrameToken* frameToken = nullptr;
		HMODULE interposer = nullptr;

		// SL Interposer 函数
		PFun_slInit* slInit{};
		PFun_slShutdown* slShutdown{};
		PFun_slIsFeatureSupported* slIsFeatureSupported{};
		PFun_slIsFeatureLoaded* slIsFeatureLoaded{};
		PFun_slEvaluateFeature* slEvaluateFeature{};
		PFun_slFreeResources* slFreeResources{};
		// v0.5.12：显式分配 DLSSG feature（指南标准序列 SetOptions → AllocateResources → Evaluate）
		PFun_slAllocateResources* slAllocateResources{};
		PFun_slSetTag* slSetTag{};
		// v0.5.11：frame-based tagging（slSetTag deprecated）——dlss_g 插件要求
		// slSetTagForFrame + eUseFrameBasedResourceTagging，否则 slEvaluateFeature 报
		// eErrorMissingOrInvalidAPI(28)（"Could not find evaluateFeature callbacks"）
		PFun_slSetTagForFrame* slSetTagForFrame{};
		PFun_slSetConstants* slSetConstants{};
		PFun_slGetFeatureFunction* slGetFeatureFunction{};
		PFun_slGetNewFrameToken* slGetNewFrameToken{};
		PFun_slSetD3DDevice* slSetD3DDevice{};
		// v0.32（对齐 open-shaders）：slSetFeatureLoaded——设备绑定后显式请求
		// 加载 Reflex/PCL（SL 日志 "sl.reflex has no registered hooks" = 未激活）
		PFun_slSetFeatureLoaded* slSetFeatureLoaded{};
		// v0.5.10：manual hooking 必需——upgrade swapchain/device 为 SL 代理接口，
		// 否则 common 插件 presentCommon() 永不被调 → dlss_g evaluateFeature 回调 0x0
		PFun_slUpgradeInterface* slUpgradeInterface{};

		// DLSS 函数
		PFun_slDLSSSetOptions* slDLSSSetOptions{};

		// v0.3：DLSSG / Reflex 函数
		PFun_slDLSSGSetOptions* slDLSSGSetOptions{};
		// v0.31（对齐 open-shaders）：DLSSG 状态查询（多倍帧生成上限）
		PFun_slDLSSGGetState* slDLSSGGetState{};
		// v0.32（对齐 open-shaders）：Reflex sleep——**RSYNC pacing 建立的必需输入**。
		// 每帧 slReflexSleep 在模拟开始前调用（Reflex 延迟标记），返回后发
		// eSimulationStart。缺失 → sl.reflex 不注册 hooks → RSYNC 无同步 → 插帧
		// pacing 乱 → 频闪（SL 日志 "Plugin 'sl.reflex' has no registered hooks" 实锤）。
		PFun_slReflexSleep* slReflexSleep{};
		PFun_slReflexSetOptions* slReflexSetOptions{};
		// v0.5.23：PCL marker（ePresentStart/ePresentEnd）——RSYNC（Reflex Sync pacer）
		// 靠它建立帧节奏；缺失 → RSYNC 实例 null → slAllocateResources 0xC0000005
		// （DLSS-G 指南 8.0：sl.reflex 集成必须标记 PresentStart/PresentEnd）
		PFun_slPCLSetMarker* slPCLSetMarker{};

		// v0.31（对齐 open-shaders Streamline.cpp:300-320）：多倍帧生成
		std::uint32_t dlssgMaxFramesToGenerate = 1;   // 硬件支持上限（slDLSSGGetState 查询）
		std::uint32_t dlssgFramesToGenerate = 1;      // 用户配置（INI DLSSGFramesToGenerate）

		// v0.5.23：Present 前后 PCL 标记（RSYNC 建立）
		// v0.31（对齐 open-shaders DX12SwapChain.cpp:365-403）：补全 PCL 序列——
		// eSimulationEnd → eRenderSubmitStart →（资源标记）→ eRenderSubmitEnd →
		// ePresentStart → Present → ePresentEnd。DLSSG 的 RSYNC 帧节奏依赖完整
		// 序列，只发 present 部分 → pacing 乱 → 频闪（20:17 用户实锤）。
		void PresentMarkerSimulationEnd();
		void PresentMarkerRenderStart();
		void PresentMarkerRenderEnd();
		void PresentMarkerStart();
		void PresentMarkerEnd();

		// 加载 interposer + slInit（游戏启动时）
		void LoadInterposer(const Settings& a_settings);

		// 检测 DLSS/DLSSG 支持
		void CheckFeatures(IDXGIAdapter* a_adapter);

		// 绑定 DLSS/DLSSG/Reflex 功能函数
		void PostDevice();

		// 设置 D3D 设备（slSetD3DDevice）
		void SetD3DDevice(ID3D11Device* a_device);
		void SetD3D12Device(ID3D12Device* a_device);

		// v0.5.10：upgrade 接口为 SL 代理（swapchain 必调，presentCommon 路径）
		void UpgradeInterface(void** a_ppInterface);

		// 每帧：设置相机常量 + DLSS 选项 + 评估（超分 + 帧生成）
		// v0.7.6：返回是否成功——失败时调用方把原画面拷进 colorOut 兜底（防黑屏）
		// v0.7.8：a_renderWidth/Height = 渲染分辨率（colorIn/depth/mvec extent），
		// 输出 extent = 输出分辨率（fg.screenWidth/Height）——超分放大
		bool EvaluateDLSS(ID3D11DeviceContext* a_ctx,
			ID3D11Resource* a_colorIn, ID3D11Resource* a_colorOut,
			ID3D11Resource* a_depth, ID3D11Resource* a_motionVectors,
			std::uint32_t a_renderWidth, std::uint32_t a_renderHeight,
			const FrameBuffer& a_frameBuffer,
			const Settings& a_settings);

		// v0.3：DLSSG 插帧（D3D12 路径）——设置选项 + 评估
		void SetDLSSGOptions(std::uint32_t a_width, std::uint32_t a_height,
			std::uint32_t a_mvecDepthW, std::uint32_t a_mvecDepthH, DXGI_FORMAT a_colorFormat);
		// 返回是否成功（失败 → 调用方 Present 兜底直通，避免画面冻结）
		bool EvaluateDLSSG(ID3D12GraphicsCommandList* a_cmdList,
			ID3D12Resource* a_colorIn, ID3D12Resource* a_colorOut,
			ID3D12Resource* a_depth, ID3D12Resource* a_motionVectors,
			const FrameBuffer& a_frameBuffer);

		// v0.3：DLSSG 运行时要求 Reflex 激活（FrameGen.cpp 调用）
		void ActivateReflex();

		// v0.32（对齐 open-shaders Streamline.cpp:890-924）：每帧 Reflex sleep——
		// 模拟开始前调用（Present 开头），slReflexSleep 建立 RSYNC 节奏，返回后
		// 发 eSimulationStart marker。DLSSG 插帧 pacing 的必需输入。
		void ReflexSleep();

		// 释放
		void DestroyResources();

	private:
		void CheckFrameConstants(const FrameBuffer& a_fb, float a_aspect, float a_near, float a_far);
		void SetDLSSOptions(std::uint32_t a_outputWidth, const Settings& a_settings);
	};
}
