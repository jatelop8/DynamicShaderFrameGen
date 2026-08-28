#pragma once

// v0.6：FSR3.1 FG —— 用 FidelityFX-SDK（CS 同款）头，与 DX12SwapChain.cpp 一致
#include <FidelityFX/api/include/dx12/ffx_api_dx12.hpp>
#include <FidelityFX/api/include/ffx_api.hpp>
#include <FidelityFX/api/include/ffx_api_loader.h>
#include <FidelityFX/framegeneration/include/ffx_framegeneration.hpp>

namespace FrameGen
{
	// v0.6：AMD FSR 3.1 Frame Generation（Provider=0）——移植自 doodlum/ENBFrameGeneration
	// （MIT/开源，288K 下载验证）：FSR3 FG 无模型依赖、无闭源插件、ENB 共存成熟，
	// 绕开 DLSSG 的 sl.dlss_g allocate 崩溃问题。
	class FidelityFX
	{
	public:
		static FidelityFX* GetSingleton()
		{
			static FidelityFX singleton;
			return &singleton;
		}

		HMODULE module = nullptr;

		ffx::Context swapChainContext{};
		ffx::Context frameGenContext{};
		ffxFunctions ffxModule{};

		void LoadFFX();
		void SetupFrameGeneration();
		void Present(bool a_useFrameGeneration);
	};
}
