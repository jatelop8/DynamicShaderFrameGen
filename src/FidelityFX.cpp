// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
// Derived from open-source projects (all GPL-3.0):
//   - Skyrim Community Shaders (https://github.com/doodlum/skyrim-community-shaders)
//   - ENBFrameGeneration (https://github.com/doodlum/ENBFrameGeneration)
// Other components: Dear ImGui / CommonLibSSE-NG / Microsoft Detours (MIT).

#include <SKSE/SKSE.h>

#include <RE/B/BSTimer.h>

#include "FrameGen.h"
#include "DX12SwapChain.h"

// ffx_api 头含 Windows API——必须放在 CommonLib 之后
#include "FidelityFX.h"

namespace FrameGen
{
	// v0.6：FSR3.1 FG 移植（doodlum/ENBFrameGeneration，GPL-3.0）
	// 输入：HUDLessColor/depth/motionVectors 共享纹理（我们的 WrappedResource 链）+ D3D12 swapchain
	// v0.6.1：全部走 ffxModule 函数表调用（运行时 loader，不链接 ffx_api.cpp）——
	// 表统一用成员 ffxModule（回调也用它，避免 g_ffxModule 空表崩溃）

	void FidelityFX::LoadFFX()
	{
		// v0.6.1：用完整后端 amd_fidelityfx_framegeneration_dx12.dll（导出全部 ffx API，
		// 与 v0.1 的 swapchain context 同源；之前的 amd_fidelityfx_dx12.dll 不存在）
		module = LoadLibraryW(L"Data\\Shaders\\Upscaling\\FidelityFX\\amd_fidelityfx_framegeneration_dx12.dll");
		if (module) {
			ffxLoadFunctions(&ffxModule, module);
			SKSE::log::info("[FidelityFX] FSR3 module loaded");
		} else {
			SKSE::log::error("[FidelityFX] LoadLibrary amd_fidelityfx_framegeneration_dx12.dll failed ({})", GetLastError());
		}
	}

	void FidelityFX::SetupFrameGeneration()
	{
		auto& fg = Get();
		auto& sc = fg.dx12SwapChain;

		// v0.6.2.2：防御——模块未加载/函数表空时直接返回（避免空表调用崩溃）
		if (!module || !ffxModule.CreateContext || !ffxModule.Configure || !ffxModule.Dispatch) {
			SKSE::log::error("[FidelityFX] FSR3 module not ready - frame generation disabled");
			return;
		}

		ffx::CreateContextDescFrameGeneration createFg{};
		createFg.displaySize = { sc.swapChainDesc.Width, sc.swapChainDesc.Height };
		createFg.maxRenderSize = createFg.displaySize;
		createFg.flags = FFX_FRAMEGENERATION_ENABLE_ASYNC_WORKLOAD_SUPPORT;
		createFg.backBufferFormat = ffxApiGetSurfaceFormatDX12(sc.swapChainDesc.Format);

		ffx::CreateBackendDX12Desc createBackend{};
		createBackend.device = sc.d3d12Device.get();

		// v0.6.1：ffxCreateContext 的 desc 是链表——手动 LinkHeaders（createFg → createBackend）
		// 再传第一个 header（ffx::CreateContext inline 的封装就是干这个的，但表调用要自己串）
		createFg.header.pNext = &createBackend.header;
		createBackend.header.pNext = nullptr;
		if (ffxModule.CreateContext(&frameGenContext, &createFg.header, nullptr) != FFX_API_RETURN_OK) {
			SKSE::log::error("[FidelityFX] Failed to create frame generation context!");
		} else {
			SKSE::log::info("[FidelityFX] Frame generation context created");
		}
	}

	float GetVerticalFOVRadFSR()
	{
		auto& fg = Get();
		auto& sc = fg.dx12SwapChain;
		static float& fac = (*(float*)(REL::RelocationID(513786, 388785).address()));
		const auto base = fac;
		const auto x = base / 1.30322540f;
		const auto vFOV = 2 * atan(x / (float(sc.swapChainDesc.Width) / float(sc.swapChainDesc.Height)));
		return vFOV;
	}

	void FidelityFX::Present(bool a_useFrameGeneration)
	{
		auto& fg = Get();
		auto& sc = fg.dx12SwapChain;
		auto commandList = sc.commandLists[sc.frameIndex].get();

		// v0.7.17：FG 输入 = colorOut（DLSS 超分结果 4K；失败时 = 引擎画面兜底）。
		// v0.7.13 曾改回 swapChainBufferWrapped（UI 保留）但 kFRAMEBUFFER 方案已弃。
		auto HUDLessColor = sc.colorOutWrapped ? sc.colorOutWrapped->resource.get() : (sc.swapChainBufferWrapped ? sc.swapChainBufferWrapped->resource.get() : nullptr);
		auto depth = sc.depthWrapped ? sc.depthWrapped->resource.get() : nullptr;
		auto motionVectors = sc.mvecWrapped ? sc.mvecWrapped->resource.get() : nullptr;

		// v0.7.22 诊断（节流）：FG 状态——确认插帧是否每帧执行（帧数 75 = 原生？FG 失效？）
		static std::uint32_t fgDiag = 0;
		if (++fgDiag % 180 == 1) {
			SKSE::log::info("[FrameGen] FG diag: active={} module={} color={} depth={} mvec={}",
				a_useFrameGeneration, ffxModule.Configure != nullptr,
				HUDLessColor != nullptr, depth != nullptr, motionVectors != nullptr);
		}

		if (!HUDLessColor || !depth || !motionVectors)
			return;

		FfxApiSwapchainFramePacingTuning framePacingTuning{ 0.1f, 0.1f, true, 2, false };

		ffx::ConfigureDescFrameGenerationSwapChainKeyValueDX12 framePacingTuningParameters{};
		framePacingTuningParameters.key = FFX_API_CONFIGURE_FG_SWAPCHAIN_KEY_FRAMEPACINGTUNING;
		framePacingTuningParameters.ptr = &framePacingTuning;

		// v0.6.1：表调用（ffxModule.Configure，替代 ffx::Configure inline——避免链接 ffx_api.cpp）
		if (ffxModule.Configure(&sc.ffxSwapChainContext, &framePacingTuningParameters.header) != FFX_API_RETURN_OK) {
			SKSE::log::error("[FidelityFX] Failed to configure frame pacing tuning!");
		}

		ffx::ConfigureDescFrameGeneration configParameters{};

		if (a_useFrameGeneration) {
			configParameters.frameGenerationEnabled = true;

			configParameters.frameGenerationCallback = [](ffxDispatchDescFrameGeneration* params, void* pUserCtx) -> ffxReturnCode_t {
				return FidelityFX::GetSingleton()->ffxModule.Dispatch(reinterpret_cast<ffxContext*>(pUserCtx), &params->header);
			};
			configParameters.frameGenerationCallbackUserContext = &frameGenContext;

			configParameters.HUDLessColor = ffxApiGetResourceDX12(HUDLessColor);
		} else {
			configParameters.frameGenerationEnabled = false;
			configParameters.frameGenerationCallbackUserContext = nullptr;
			configParameters.frameGenerationCallback = nullptr;
			configParameters.HUDLessColor = FfxApiResource({});
		}

		static uint64_t frameID = 0;
		configParameters.frameID = frameID;
		configParameters.swapChain = sc.swapChain;
		configParameters.onlyPresentGenerated = false;
		configParameters.allowAsyncWorkloads = true;
		configParameters.flags = 0;

		configParameters.generationRect.left = 0;
		configParameters.generationRect.top = 0;
		configParameters.generationRect.width = sc.swapChainDesc.Width;
		configParameters.generationRect.height = sc.swapChainDesc.Height;

		if (ffxModule.Configure(&frameGenContext, &configParameters.header) != FFX_API_RETURN_OK) {
			SKSE::log::error("[FidelityFX] Failed to configure frame generation!");
		}

		if (a_useFrameGeneration) {
			ffx::DispatchDescFrameGenerationPrepare dispatchParameters{};

			dispatchParameters.commandList = commandList;

			dispatchParameters.motionVectorScale.x = (float)sc.swapChainDesc.Width;
			dispatchParameters.motionVectorScale.y = (float)sc.swapChainDesc.Height;
			dispatchParameters.renderSize.width = sc.swapChainDesc.Width;
			dispatchParameters.renderSize.height = sc.swapChainDesc.Height;

			static auto gameViewport = RE::BSGraphics::State::GetSingleton();

			dispatchParameters.jitterOffset.x = gameViewport->projectionPosScaleX * float(sc.swapChainDesc.Width) / 2.0f;
			dispatchParameters.jitterOffset.y = gameViewport->projectionPosScaleY * float(sc.swapChainDesc.Height) / 2.0f;

			auto deltaTime = (float*)REL::RelocationID(523660, 410199).address();
			dispatchParameters.frameTimeDelta = *deltaTime * 1000.f;

			static auto cameraNear = (float*)(REL::RelocationID(517032, 403540).address() + 0x40);
			static auto cameraFar = (float*)(REL::RelocationID(517032, 403540).address() + 0x44);

			dispatchParameters.cameraNear = *cameraNear;
			dispatchParameters.cameraFar = *cameraFar;

			dispatchParameters.cameraFovAngleVertical = GetVerticalFOVRadFSR();
			dispatchParameters.viewSpaceToMetersFactor = 0.01428222656f;

			dispatchParameters.frameID = frameID;

			dispatchParameters.depth = ffxApiGetResourceDX12(depth);
			dispatchParameters.motionVectors = ffxApiGetResourceDX12(motionVectors);

			if (ffxModule.Dispatch(&frameGenContext, &dispatchParameters.header) != FFX_API_RETURN_OK) {
				SKSE::log::error("[FidelityFX] Failed to dispatch frame generation!");
			}
		}

		frameID++;
	}
}
