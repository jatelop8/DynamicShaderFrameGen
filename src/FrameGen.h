// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
// Derived from open-source projects (all GPL-3.0):
//   - Skyrim Community Shaders (https://github.com/doodlum/skyrim-community-shaders)
//   - ENBFrameGeneration (https://github.com/doodlum/ENBFrameGeneration)
// Other components: Dear ImGui / CommonLibSSE-NG / Microsoft Detours (MIT).

#pragma once

// 注意：CommonLib 头必须最先（REX::W32 强制 Windows API 头在 CommonLib 之后）
#include <RE/Skyrim.h>
#include <SKSE/SKSE.h>

#include <atomic>

#include <d3d11_4.h>
#include <d3d12.h>
#include <winrt/base.h>

#include "NeuralRendering/Runtime.h"  // DLSS5 Tuning（GUI 滑块绑定）

// COM 异常辅助（精简自 CS PCH.h）
namespace DX
{
	class com_exception : public std::exception
	{
	public:
		explicit com_exception(HRESULT hr) noexcept :
			result(hr) {}
		const char* what() const override
		{
			static char s_str[64] = {};
			sprintf_s(s_str, "Failure with HRESULT of %08X", static_cast<unsigned int>(result));
			return s_str;
		}

	private:
		HRESULT result;
	};

	inline void ThrowIfFailed(HRESULT hr)
	{
		if (FAILED(hr)) {
			throw com_exception(hr);
		}
	}
}

#include "DX12SwapChain.h"
#include "Streamline.h"

namespace FrameGen
{
	// stl 别名（CommonLib 只在 RE::/REL:: 内定义，这里补一个供本插件使用）
	namespace stl = RE::stl;

	// vtable detour（无 Detours 依赖版——CS 用 Detours，这里用 VirtualProtect 直接改槽）
	template <std::size_t idx, class T>
	void detour_vfunc(void* a_target)
	{
		auto vtable = *reinterpret_cast<std::uintptr_t**>(a_target);
		T::func = vtable[idx];  // 保存原函数（REL::Relocation 赋值）
		DWORD oldProtect;
		VirtualProtect(&vtable[idx], sizeof(void*), PAGE_READWRITE, &oldProtect);
		vtable[idx] = reinterpret_cast<std::uintptr_t>(T::thunk);
		VirtualProtect(&vtable[idx], sizeof(void*), oldProtect, &oldProtect);
	}

	// 引擎 per-frame 常量缓冲布局（c0 起，寄存器映射——见 CS FrameBuffer）
	// 只取 DLSS 需要的字段（其余引擎字段不关心，按偏移跳过）
	struct Matrix
	{
		float data[4][4]{};  // row-major（引擎 shader 常量布局）
	};

	struct FrameBuffer
	{
		Matrix CameraView;                            // c0
		Matrix CameraProj;                            // c8
		Matrix CameraViewProj;                        // c16
		Matrix CameraViewProjUnjittered;              // c24
		Matrix CameraPreviousViewProjUnjittered;      // c32
		Matrix CameraProjUnjittered;                  // c40
		Matrix CameraProjUnjitteredInverse;           // c48
		Matrix CameraViewInverse;                     // c56
		Matrix CameraViewProjInverse;                 // c64
		Matrix CameraProjInverse;                     // c72
		float  CameraPosAdjust[4];                    // c80
		float  CameraPreviousPosAdjust[4];            // c82
	};

	struct Settings
	{
		bool enableFrameGen = false;   // 总开关（D3D12 proxy）
		bool forceEnable = false;      // 强制启用（<120Hz 也开）
		// v0.26：强制无边框窗口化（borderless fullscreen）——帧生成硬性要求
		// Windowed swapchain（全屏独占 → 插件不代理 → 插帧不生效）。开时把
		// 游戏窗口强制成无边框铺满屏幕（视觉等同全屏）+ swapchain 强制窗口化，
		// 让帧生成在任何玩家显示设置下都能激活。
		bool forceBorderless = true;   // 强制无边框窗口化（默认开）
		bool frameGeneration = true;   // 帧生成（false = 仅 DLSS 超分/DLAA 无插帧）
		// v0.7.24：DLSS 超分独立开关——4K 下 DLAA 重建每帧 ~3-5ms（原生 50→37→FG 100+→75）；
		// 关掉回到 v0.6.2.2 纯插帧状态（100+ 帧，画面 = 引擎原生 4K）
		bool enableUpscale = true;     // DLSS 超分/DLAA 重建（false = 仅 FSR3 插帧，帧数最高）
		// DLSS5 Neural Rendering（内置 NGX Feature 18）——开启时在 DLSS 超分结果上做
		// neural rendering（UI 前）。与帧生成互斥（跟 CS 一致：关 FG 才激活，避免
		// 两套 temporal 叠加闪烁）。
		bool neuralRenderingEnabled = false;  // INI NeuralRenderingEnabled
		int  provider = 0;             // 0=FSR3（AMD 插帧，默认） 1=DLSSG（NVIDIA 插帧）
		int  qualityMode = 1;          // DLSS 模式：0=DLAA 1=Quality 2=Balanced 3=Performance 4=UltraPerformance
		// v0.41：渲染分辨率缩放（自定义 DRS）——引擎渲染分辨率 = 输出 × 该比例，DLSS
		// 再把低分辨率画面放大回输出分辨率（真超分才有 NR/帧生成空间）。0 = 跟随
		// QualityMode 档位表（旧行为）；>0 = 自定义比例（0.30-1.00，如 0.70 = 70%）。
		float renderResolutionScale = 0.0f;  // INI RenderResolutionScale / GUI slider（0=Auto 跟随 QualityMode 档位表）
		// v0.57：mvecScale 覆盖（0 = 保留旧推导 1/renderScale，默认零行为变化）。
		// 运动矢量逐帧喂给 DLSS-G，值错了每张生成帧的 motion 都错 → 频闪。
		// 参照实现 open-shaders 的标准全屏路径用 identity（注释原话：must keep
		// mvecScale at identity or DLSS massively over-estimates motion），官方
		// 指南也写「值已在 {-1,1} 则 scale={1,1}」；而本工程用的是 v0.49k 为修重影
		// 调出的 1/renderScale（=1.5，即 150%）。两者冲突，只有游戏内 A/B 能定。
		// 设 1.00 即切到 identity。
		float mvecScaleOverride = 0.0f;   // INI MvecScaleOverride（0=旧行为 1.0=identity）
		// v0.31（对齐 open-shaders）：多倍帧生成（DLSS 4 MFG）——每真实帧生成 N 个插帧
		// （1=2x 插帧 2=3x 3=4x，取决于 GPU/SL SDK 支持，运行时 clamp 到硬件上限）
		std::uint32_t dlssgFramesToGenerate = 1;  // INI DLSSGFramesToGenerate
		// v0.50：MFG 上限覆盖（老卡多倍帧生成）——0=不覆盖（严格跟随硬件上报，默认安全）；
		// 1..5 = 强制上报上限为 N 个插帧（1=2x 2=3x 3=4x 4=5x 5=6x）。需要外部内核
		// 解锁器提供 Ada/Ampere/Turing 内核，否则运行时会被守卫退回安全倍率。
		std::uint32_t mfgMaxFramesOverride = 0;  // INI MFGMaxFramesOverride
		// v0.54：Reflex 渲染帧率上限（0 = 自动：显示器刷新率 / 帧生成总倍数 - 1）。
		// DLSSG 多倍帧生成时 present 帧率 = 渲染帧率 x 倍数，一旦超过显示器刷新率就会
		// 超发：present 队列积压、SL pacer 节奏崩 → 画面持续闪烁（v0.53 实测 160Hz 屏
		// + 4x + 写死 60fps 渲染 = 229.6 present fps，超发 43%）。非 0 时直接作为
		// 渲染帧率上限（fps），覆盖自动计算。
		int  reflexFpsLimit = 0;       // INI ReflexFpsLimit
		int  presetDLSS = 0;           // DLSS 模型预设：0=Auto 1=J 2=K 3=L 4=M
		float sharpness = 0.5f;        // v0.6.3：DLSS 超分锐化（0-1，0=关闭）；v0.7.21 默认 0.3→0.5（4K 重建需更明显锐化）
		// v0.25：DLSS-NR（NGX 直调）已移除——NR 改由外部 ReShade 方案（dlss5-dx11-bridge +
		// renodx-dlss5 addon）提供，插件不再内置任何 dlssnr 集成/补丁代码（发布安全）。
		int  streamlineLogLevel = 0;   // 0=Off 1=Default 2=Verbose
		bool fpsOverlay = true;        // v0.24：FPS 显示器（右上角粗体白字，菜单/INI 可开关）
		// v0.7.2：Skyrim 键码 = DIK 扫描码（Home=199/0xC7），不是 VK 码（0x24 无效——
		// SKSE GetIDCode 返回 DIK）。菜单/插帧统一走 PollHomeKey 每帧轮询 VK_HOME。
		std::uint32_t toggleKey = 0xC7;  // 保留（INI 兼容），实际用 VK_HOME 轮询
	};

	class FrameGen
	{
	public:
		Settings settings;

		// DLSS5 Neural Rendering 调优参数（GUI 滑块实时改，Apply 每帧传入；对齐 CS）
		NeuralRendering::Tuning nrTuning;

		// 加载 INI 配置（main.cpp 启动时调用）
		void LoadConfig();

		// D3D 状态
		bool        d3d12SwapChainActive = false;
		bool        lowRefreshRate = false;
		double      refreshRate = 0;
		float       screenWidth = 0;
		float       screenHeight = 0;

		ID3D11Device*        d3d11Device = nullptr;
		ID3D11DeviceContext* d3d11Context = nullptr;

		Streamline   streamline;
		DX12SwapChain dx12SwapChain;

		// 相机近远平面（REL ID 定位，引擎常量）
		float* cameraNear = nullptr;
		float* cameraFar = nullptr;

		// v0.34（对齐 open-shaders）：DLSS Halton jitter（OnMainUpdateJitter 计算，
		// CheckFrameConstants 喂给 SL——DLSSG 运动估计需要精确 jitter，之前恒 0）
		float jitterX = 0.0f;
		float jitterY = 0.0f;

		// v0.37b：引擎帧号（OnMainUpdateJitter 更新）——EnsureFrameToken 的
		// IsNewFrame 判断基准（同帧复用 token，防每帧取两次）
		std::uint32_t engineFrameCount = 0;

		// D3D11 创建完成（PatchIAT 钩子内调用）
		void OnD3D11Created(ID3D11Device* a_device, ID3D11DeviceContext* a_context);
		// v0.7.2：每帧轮询 Home 键（GetAsyncKeyState）——短按切插帧，长按开菜单
		// （SKSE 输入事件是按下/抬起才触发、按住不持续，长按检测必须轮询硬件状态）
		void PollHomeKey();

		// 建立 D3D12 proxy（替换 swapchain）
		void CreateD3D12Proxy(IDXGIAdapter* a_adapter, const DXGI_SWAP_CHAIN_DESC& a_swapChainDesc);

		// 安装 ID3D11DeviceContext::Map/Unmap 钩子（偷看 perFrame 常量缓冲）
		void InstallContextHooks(ID3D11DeviceContext* a_context);

		// 安装 D3D11CreateDeviceAndSwapChain IAT 钩子（main.cpp 启动时调用）
		void InstallCreateDeviceHook();

		// 安装输入开关键（Home）——DataLoaded 后注册
		void InstallInputHook();

		// v0.26：强制无边框窗口化（幂等，每帧可调）——游戏窗口改无边框 +
		// 铺满所在显示器。CreateDevice hook 首次应用，Present 每帧防重置。
		void EnsureBorderless();
		HWND hwnd = nullptr;  // 游戏主窗口（CreateDevice hook 时记录）

		// v0.50：DLSS 超分/DRS/Halton jitter 已全部拔掉（引擎回到 2560 原生渲染）。
		// InstallDRSHook / OnMainUpdateJitter / InstallMainPostProcessingHook /
		// OnMainPostProcessing 已移除。仅保留 DLSS5(DLSSNR) + FSR3 FG 串联。

		// v0.7.13：安装 MenuManagerDrawInterfaceStart hook（CS 同款）——引擎 UI 绘制
		// 开始前回调。此时把 DLSS 超分结果写入引擎 kFRAMEBUFFER（4K），UI 随后叠加
		// 到 kFRAMEBUFFER 上 → composite → 后缓冲 = 超分画面 + UI（不丢 UI）。
		void InstallMenuHook();
		void OnMenuDrawStart();

		// 垂直 FOV（弧度）——DLSSG 相机常量校验需要（CS 同款 REL ID + atan 公式）
		float GetVerticalFOVRad();

		// 帧生成是否激活（Home 可切换；INI Enable=1 时初始开启）
		std::atomic<bool> fgActive{ false };

		// perFrame 常量缓冲（REL ID）
		static ID3D11Buffer** GetPerFrameBuffer();

		// 当前帧相机缓存（Map hook 填充；Unmap 后为稳定副本）
		FrameBuffer* GetFrameBuffer() { return mappedFrameBuffer; }
		FrameBuffer frameBufferCopy{};  // v0.5：Unmap 时拷贝的稳定副本（Present 读它）

		// Map hook 写入缓存（ID3D11DeviceContext_Map::thunk 调用）
		void SetMappedFrameBuffer(FrameBuffer* a_fb) { mappedFrameBuffer = a_fb; }

	private:
		FrameBuffer* mappedFrameBuffer = nullptr;
	};

	FrameGen& Get();
}
