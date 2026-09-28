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
		// v1.01: allow DLSS5 NR to run in series with frame generation.
		// 0 = mutually exclusive (v0.69 behaviour, default).
		// 1 = NR runs first on the real frame, then DLSS-G interpolates it.
		// Read from INI (NRAllowWithFrameGen) and exposed in the GUI.
		bool nrAllowWithFrameGen = false;
		// v1.21 -- INTEROP FENCE. v0.75 withdrew the D3D11 -> D3D12 wait
		// ("kD3D12WaitsOnD3D11 = false") on the argument that the fence value
		// had sat at its initial 1 for 50 s. A fence nobody signals looks
		// exactly like that. What the withdrawal costs: the D3D12 queue then
		// reads swapChainBufferWrapped / colorOutWrapped -- which the engine and
		// NR write through D3D11 -- with no ordering at all, while the note at
		// DX12SwapChain's "fence before" comment still says the design relies on
		// that ordering. 1 = restore it (default), 0 = the v0.75 behaviour.
	bool interopFenceWait = true;   // INI InteropFenceWait
	// Linux build: D3D12 presents the previous, finished frame (see DX12SwapChain,
	// "PipelinedPresent"). Ordering stays, the wait goes away, +1 frame latency.
	bool pipelinedPresent = false;  // INI PipelinedPresent
	// v1.44 -- FENCE WAIT MODE. This is the one knob that separates this build
	// from the Sep 11 build at the end of Present(), and it is worth a setting
	// rather than a constant because the two behaviours differ by a whole
	// frame of CPU/GPU overlap.
	//
	// The end of every frame signals the shared fence on the D3D12 queue and
	// then has to wait for it. d3d11Fence and d3d12Fence wrap the SAME fence
	// object (CreateInterop opens it on both devices), so the wait can be
	// placed on either timeline:
	//   1 = CPU polls d3d12Fence->GetCompletedValue() until it passes
	//       (v1.03b..v1.43). The poll runs on the render thread, so the CPU
	//       submits a frame and then blocks until the GPU has finished it -
	//       no frame is ever prepared while the previous one is executing.
	//   0 = d3d11Context->Wait(d3d11Fence, v): the wait is queued on the D3D11
	//       timeline and the CPU returns immediately, which is what the Sep 11
	//       build did and why it reached 56.12 base at 2K.
	//
	// Measured 2026-09-21, same box, same 2K output, same FSR3 2x chain:
	//   Sep 11 build (queue-side wait)         base 56.12 (17.8 ms)
	//   this build    (CPU poll), watchdog     92-98% of samples in
	//                                          "stage=d3d11 Wait", base 36.08
	// The watchdog number alone is not proof - it is exactly where the code
	// was told to block - which is why this is a switch and not a conclusion.
	//
	// Mode 1 keeps the v1.03b anti-freeze guard (it can time out and drop a
	// frame); mode 0 cannot hang the CPU, but a fence that is never signalled
	// stalls the D3D11 queue instead - the 2026-09-18 18:23 failure. If the
	// game freezes on mode 0, this line is the one to flip back.
	bool fenceWaitBusy = false;     // INI FenceWaitBusy (1 = CPU poll, 0 = queue-side)
	// Linux build: SyncInterval of the D3D12 Present without frame generation. The
	// author presents with a fixed 1 (VSync). 0 = no VSync; VRR and the frame limiter
	// (SSEDisplayTweaks) set the pace then. Measured 2026-09-27: no FPS difference
	// between 0 and 1 once PipelinedPresent is on.
	int presentInterval = 1;        // INI PresentInterval (1 = VSync like the author, 0 = off)
	// Linux build (dlss-quality): with quality modes 1-4 the engine renders into a DRS
	// sub-rect. Community Shaders NOPs the vanilla DRS controller for that
	// (35556/36555+0x2D). 1 = like CS, 0 = controller stays (v0.48c experiment).
	// Only applies with render scale < 1; DLAA is untouched.
	bool vanillaDRSNop = true;      // INI VanillaDRSNop
	// v1.21 -- THE FADER MENU IS NOT A MENU. IsMenuOpen("Fader Menu") is true
		// the whole time the player is in the world (23:38 run: fade=1 for 40+ s
		// with paused=0, ld=0 and the clock at timescale 20), so counting it as
		// one engages the v0.63 guard on essentially every frame and DLSS-G is
		// never handed a frame. 1 = the fader counts only while we cannot yet be
		// in the world (start-up + loads), 0 = never counts. See GameMenuOpenNow.
		bool menuGuardFader = true;     // INI MenuGuardFader
		// v1.22 -- PIXEL PROBE (default 1). Samples a 64x64 block from the centre of
		// the frame the plugin hands to the swap chain, once per second, and reports
		// whether that content changed. It exists because up to v1.21 a frozen screen
		// and a healthy one produced the same log: presents, presentAge, dsync and the
		// presented-per-real-frame ratio are all witnesses that a flip happened, and
		// none of them can see the same picture being flipped again (ledger L38).
		// Read-only and self-disabling; 0 switches it off without a rebuild.
		bool pixelProbe = true;         // INI PixelProbe
		// v1.34 -- T2. The T1 run renamed the SECOND DLSS-G writer (DLSSG-Transfusion,
		// loaded as dinput8.dll) away before launch, and its own log was untouched for
		// the whole session -- the freeze was bit-for-bit the same. So the second writer
		// is not the cause, and the break is on our side of the flip.
		//
		// With this on, the passthrough CopyResource runs even when dlssgOk is true: it
		// overwrites whatever DLSS-G did -- or did not -- put in the back buffer with our
		// own colorOut. Picture comes back  -> DLSS-G never filled the back buffer.
		// Picture still frozen -> the back buffer does hold new content and the break is
		// downstream of us, in the flip. Diagnostic switch; default off, no effect on a
		// normal run. The run prints its value at INI load so "was it even read" can
		// never be confused with "it was read and did nothing".
		bool forceBackBufferCopy = false;  // INI ForceBackBufferCopy
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
		// v1.46：MFG 倍率的持久化开关（默认 0 = 不碰外部文件）。
		//
		// 背景（实测取证，见账本 §84.25 / §84.28）：本插件的 DLSSGFramesToGenerate 只被
		// 本插件自己读，而实际上屏倍率由第三方注入型 mod DLSSG-Transfusion 决定 —— 它
		// 在启动时读一次游戏根目录的 DLSSG-Transfusion.json（日志原话：
		// "Initial control: ... multiplier=4x ...; config: <游戏目录>\DLSSG-Transfusion.json"），
		// 之后在渲染线程持续 reapply，覆盖本插件发出的任何 SetOptions 请求。所以菜单里
		// 改倍率写自己的 INI 是"改了等于没改"：重启后依然是 json 里那个数。
		//
		// 唯一让"菜单改 -> 重启 -> 生效"成真的路径，就是把值也写进那份 json。但那是
		// 另一个作者的文件，本插件默认不动它 —— 必须用户在菜单里显式勾选本开关才写，
		// 且每次写前自动备份。0 = 只写自己的 INI（默认、安全）。1 = 同时写 json。
		std::uint32_t writeTransfusionConfig = 0;  // INI WriteTransfusionConfig
		// v0.54：Reflex 渲染帧率上限（0 = 自动：显示器刷新率 / 帧生成总倍数 - 1）。
		// DLSSG 多倍帧生成时 present 帧率 = 渲染帧率 x 倍数，一旦超过显示器刷新率就会
		// 超发：present 队列积压、SL pacer 节奏崩 → 画面持续闪烁（v0.53 实测 160Hz 屏
		// + 4x + 写死 60fps 渲染 = 229.6 present fps，超发 43%）。非 0 时直接作为
		// 渲染帧率上限（fps），覆盖自动计算。
		int  reflexFpsLimit = 0;       // INI ReflexFpsLimit
		// v0.63：菜单期间不插帧（DLSSGFlags::eEnableFullScreenMenuDetection 的插件侧
		// 替代实现 —— Transfusion 会把那个 flag 从 DLSS-G options 里剥掉）。菜单是 2D
		// UI，被当 3D 内容插值 = 主菜单画面持续闪。0 = 旧行为（菜单也插帧）。
		bool menuDisableFrameGen = true;  // INI MenuDisableFrameGen
		// v1.52 -- 共存开关（默认 1 = 行为与 v1.51 完全一致）。
		//
		// 背景：这两个引擎函数同时也是 CommunityShaders (CS) 的 hook 目标。
		// CS 在 12:04:44 先后 detour 了 BSInputDeviceManager::PollInputDevices 与
		// MenuManager::DrawInterfaceStart，本插件 50 秒后（12:05:34）对**同一批函数头**
		// 再下 detour —— 两边都以为自己是链头，跳转目标互相覆盖，装完 hook 0.25 秒即
		// EXCEPTION_BREAKPOINT（crash-2026-09-22-12-05-34.log，崩点落在所有模块区间外）。
		//
		// 让用户能关掉其中一个去隔离冲突。关掉的代价：
		//   menuDrawHook=0 -> MenuManagerDrawInterfaceStart 不再被 detour。
		//     OnMenuDrawStart() 自 v0.50 起是空函数（DLSS 超分已拔掉，kFRAMEBUFFER
		//     方案恒 null 属死代码），所以功能无损失，只损失"UI 绘制前"这个时机点。
		//   pollInputHook=0 -> 菜单打开时不再吞设备输入事件。ImGui 自己的鼠标走
		//     GetCursorPos/GetAsyncKeyState 轮询、键盘走 SKSE InputEvent（AddEventSink），
		//     都不依赖这个 hook，所以菜单照常可用；代价是菜单打开时鼠标仍会转动游戏视角。
		bool menuDrawHook = true;      // INI MenuDrawHook
		bool pollInputHook = true;     // INI PollInputHook
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

		// Linux build (dlss-quality): per-frame DRS state. The jitter hook sets
		// drsEngaged; the post-processing hook records drsFrameScale for the guide
		// copies in Present (by then the engine ratio is back at 1).
		bool drsEngaged = false;
		float drsFrameScaleX = 1.0f;
		float drsFrameScaleY = 1.0f;
		// True when this frame's depth was stretched to full size (guide copies then
		// sample depth 1:1 and only the motion vectors through drsFrameScale).
		bool drsDepthUpscaled = false;
		// Linux build (dlss-quality): DLSS output in kMAIN's own format. colorOutWrapped
		// is the 8-bit shared presentation texture; CopyResource from it into the
		// 16-bit float kMAIN is invalid in D3D11 and was silently dropped, so the DLSS
		// result never reached the image (DLAA included). Dumped 2026-09-28.
		winrt::com_ptr<ID3D11Texture2D> dlssOut;
		ID3D11Texture2D* EnsureDLSSOutput(ID3D11Texture2D* a_like);
		// Projection jitter before the jitter hook overwrote it; restored before the
		// UI draws (like CS PostDisplay), DRS mode only.
		float drsSavedProjX = 0.0f;
		float drsSavedProjY = 0.0f;
		// Render scale < 1 chosen at load time (quality mode 1-4); only then does
		// InstallDRSHook install the NOP and the lock hooks.
		bool DRSRequested() const;
		// ENB is loaded. ENB renders the scene with the DRS ratio applied a second time
		// (scene at 0.44 of the frame for ratio 0.67, measured 2026-09-28), so quality
		// modes 1-4 fall back to DLAA while it is present.
		static bool ENBLoaded();
		void InstallDRSLockHooks();

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

		// v0.7.11：安装 Main_UpdateJitter hook（CS 同款）——引擎每帧渲染前回调，
		// 用其 State* 参数设置引擎 DRS（dynamicResolution）渲染分辨率 + DLSS jitter。
		// 在渲染前设置（vs Present 帧尾），引擎重建 kMAIN 为目标渲染分辨率。
		void InstallDRSHook();
		void OnMainUpdateJitter(RE::BSGraphics::State* a_state);

		// v0.48：Main_PostProcessing hook（CS 同款）——引擎后处理管线入口（体积光照后、
		// 后处理前）。此时做 DLSS 超分（kMAIN → 中间纹理 → 写回 kMAIN），后处理（含 ENB）
		// 读超分结果 → DLSS 锐化/LMK 在 ENB 前生效 + ENB 保留。之前 DLSS 在 Present（ENB
		// 后），锐化被 ENB 盖掉。
		void InstallMainPostProcessingHook();
		void OnMainPostProcessing();

		// v0.7.13：安装 MenuManagerDrawInterfaceStart hook（CS 同款）——引擎 UI 绘制
		// 开始前回调。此时把 DLSS 超分结果写入引擎 kFRAMEBUFFER（4K），UI 随后叠加
		// 到 kFRAMEBUFFER 上 → composite → 后缓冲 = 超分画面 + UI（不丢 UI）。
		void InstallMenuHook();
		void OnMenuDrawStart();

		// 垂直 FOV（弧度）——DLSSG 相机常量校验需要（CS 同款 REL ID + atan 公式）
		float GetVerticalFOVRad();

		// 帧生成是否激活（Home 可切换；INI Enable=1 时初始开启）
		std::atomic<bool> fgActive{ false };
		
		// v1.23 -- last clipDev the constants path computed, i.e.
		// max|I - clipToPrevClip|. Identity (a genuinely still camera) reads 0.000061;
		// the pixel probe reads this at 1 Hz so that ten identical frames with a still
		// camera are not reported as a frozen screen.
		std::atomic<float> lastClipDev{ 0.0f };

		// perFrame 常量缓冲（REL ID）
		static ID3D11Buffer** GetPerFrameBuffer();

		// 当前帧相机缓存（Map hook 填充；Unmap 后为稳定副本）
		FrameBuffer* GetFrameBuffer() { return mappedFrameBuffer; }
		FrameBuffer frameBufferCopy{};  // v0.5：Unmap 时拷贝的稳定副本（Present 读它）

		// Map hook 写入缓存（ID3D11DeviceContext_Map::thunk 调用）
		void SetMappedFrameBuffer(FrameBuffer* a_fb) { mappedFrameBuffer = a_fb; }

		// v0.67: camera snapshot continuity gate
		// 实测 22:42 运行：det(inv(cur) x prev) 只取 -0.025248（77 帧）与 1.000000
		// 两个值。行列式恒等式要求「同一套相机数据」时恰好为 1，出现**固定**的非 1
		// 值只有一个解释：同一个 perFrame 缓冲每帧被写入**两组不同的相机数据**
		// （菜单 3D 背景相机 vs 世界相机），frameBufferCopy 每帧被后写的那组覆盖。
		// 于是 cur/prev 永远跨来源 -> det 非法 -> 钳成单位矩阵 -> DLSS-G 收到的
		// 相机运动**恒为 0**（Transfusion 侧 4/4 次 clipToPrev=identity 佐证）。
		// 闸门：相机世界位置必须与上一次接受的快照连续（一帧内跳跃 > 400 单位
		// 不可能是真实运动）。连续拒绝 12 次判定为真实传送/场景切换，重新锁定。
		bool AcceptCameraSnapshot(const FrameBuffer& a_src);
		std::uint64_t snapAccept = 0;
		std::uint64_t snapRejectJump = 0;
		std::uint64_t snapRejectZero = 0;
		std::uint64_t snapRelock = 0;
		std::uint64_t snapArrivals = 0;   // 到达的快照总数（含被丢弃的）
		float snapLastDist = 0.0f;        // 本次到达与上次接受的距离（sqrt 后）
		float snapAcceptDist = 0.0f;      // 上一次被接受的到达距离
		// v0.68: accepted-snapshot cumulative travel. Stays ~0 while the player walks
		// => the captured camera is not tracking the view camera (capture-layer defect).
		float snapPathLen = 0.0f;
		bool  snapHaveLast = false;
		float snapLastPos[3] = { 0.0f, 0.0f, 0.0f };
		std::uint32_t snapConsecReject = 0;

		// ---- v0.78: frozen-matrix detection (the real capture-layer defect) ----
		// The 08:59 run proved a snapshot can be byte-identical across 2.3 s and
		// 4196 accepts while the player walks: the position is stable (so the JUMP
		// gate never fires) and the magnitude is healthy (so `usable` passes), yet
		// the matrix never changes -> clipToPrev = I -> DLSS-G is told the camera
		// is still -> clipDevMax == 0.0000 while moving.
		//
		// A still camera produces an identical matrix too, and that is legitimate,
		// so identity alone is not the test. The test is: an identical matrix that
		// arrives AFTER we have seen a different one in between. Two identical
		// matrices separated by a different camera cannot both be “the scene is
		// still“ - that is a stale perFrame slot being re-read.
		bool  snapHaveLastMat = false;
		float snapLastMat[4][4] = {};
		std::uint64_t snapFrozenRepeats = 0;   // identical-after-different count
		std::uint64_t snapFrozenReject = 0;    // rejected because of the above
		bool  snapSawDifferentSinceRepeat = false;
		// ---- v0.94: source locking (replaces the distance gate) --------------
		// The 16:04 CTD proved one perFrame buffer carries SEVERAL cameras that
		// take turns: two CONSTANT slots (-50,600,80) and (-160,160,128), plus a
		// smoothly moving one (-50, 900->894, 96). Publishing all of them hands
		// DLSS-G a camera hundreds of units from the last one every frame.
		//
		// v0.67 tried to pick one by distance (<400 units = same camera) and
		// locked onto a CONSTANT slot while rejecting the moving one. The test
		// asks the wrong question: not "is it far" but "does it CONTINUE the
		// stream I am already publishing".
		//
		// An arrival continues the stream when it is a SMALL STEP from the last
		// published position. A constant slot is recognisable because it repeats
		// an exactly identical value, which a moving camera never does.
		std::uint64_t snapLockPublish = 0;    // arrivals published onto the stream
		std::uint64_t snapLockHold = 0;       // arrivals withheld (other source)
		std::uint64_t snapLockRelock = 0;     // times the stream was re-acquired
		std::uint32_t snapLockStill = 0;      // consecutive non-continuing arrivals
		bool  snapLockHave = false;           // a stream is locked
	// ---- v1.00: world-camera fingerprint lock ----
	// The arrival stream carries two projection families that the distance
	// test cannot separate (see tools/patch_v100_camfingerprint_1.py header):
	//
	//   WORLD  ProjUnj[0][0] = 0.149184   (player camera, view translation 0)
	//   MENU   ProjUnj[0][0] = 0.8391     (3D menu / UI scene camera)
	//
	// 5.62x apart. The lock keeps the fingerprint of the family it accepted and
	// refuses to re-acquire onto a different family, which is what let the MENU
	// camera take over frameBufferCopy and freeze the picture.
	float snapLockProj00 = 0.0f;      // ProjUnj[0][0] of the locked family
	bool  snapLockProjValid = false;  // the fingerprint above is meaningful
	std::uint64_t snapLockFamilyRej = 0;  // arrivals refused for being another family
	// ---- v1.07: the family lock gets a RELEASE PATH ----
	// v1.00 wrote "a different projection family may NEVER re-acquire" and
	// stopped there. The result is a state machine with no transition out of
	// the locked state: snapLockHave / snapLockProjValid / snapLockProj00 are
	// only ever SET, never cleared. Whichever family got locked held the
	// stream until the process exited, and the real camera was refused
	// forever.
	//
	// 22:02 run (v1.06): the world camera ProjUnj[0][0]=0.149184 arrived
	// every frame and was rejected 309 times as "another render pass"; the
	// lock ended on 0.8391 - pos (-243.0,-415.3,118.6), whose row3
	// (-0.00391655,0.999991,0.0015,0) is the matrix v0.86 had already
	// identified as a mis-offset read of the perFrame constant buffer, not a
	// camera. lock(hold/re)=2725/2416 with still=0: the release threshold
	// was unreachable. clipToPrev stayed identity, so the picture did not
	// advance while 4x presented.
	//
	// The caller already computes the edge that belongs here - c.reset, the
	// menu open/close and camera-discontinuity edge - and uses it to tell
	// DLSS-G to discard its history. The locked camera is part of that same
	// history. It hears about it now.
	bool snapLockReleasePending = false;  // raised by the reset/menu edge
	std::uint64_t snapLockReleased = 0;   // times the family lock was released
	std::uint64_t snapLockRelockJump = 0; // same-family teleports that took the anchor
	std::uint64_t snapLockAdopted = 0;    // times a position snapshot was adopted

	// ---- v1.09: is the PUBLISHED stream actually moving? ----
	// `snapAccept` counts publishes, not changes. The 09:55 run published a
	// byte-identical matrix 19 288 times in a row, so a dead capture layer and a
	// healthy one looked identical in the log. This counter separates them, and
	// it is live on both providers because the gate runs in the Map/Unmap hook.
	std::uint64_t snapMatChanges = 0;   // publishes whose matrix differed from the previous one
	// ---- v1.11: the takeover gate watches the published stream -------------
	// snapMatChanges proves the stream is ALIVE over a whole run; it cannot
	// prove it is alive NOW. This one can: consecutive publishes that carried
	// a byte-identical matrix. Reset on exactly one branch (the matrix
	// changed) so nothing that suffers stagnation can zero it -- which is
	// precisely what was wrong with the counter v1.10 gated on.
	//
	// The 14:20 run measured the failure this detects: after the world started,
	// pos=(-243.05,-415.31,118.56), matChanges frozen at 542, move=0.0000,
	// clipDev=0.000061 -- while a walking family (proj00=1) was refused
	// ~100 times a second. 200 stale publishes is ~0.6 s of that.
	std::uint64_t snapPubStale = 0;
	bool  snapPubHaveMat = false;
	float snapPubLastMat[4][4] = {};

	// ---- v1.13: capture-side content filter ----
	// The perFrame constant buffer is mapped ~22 times per rendered frame and
	// only one of those writes is the engine's camera.  snapNonCamera counts
	// the snapshots dropped because CameraProj is orthographic (no perspective
	// divide), snapSkipsSinceCam counts them consecutively and drives the
	// fallback that abandons the filter.  Both are printed by [CAM] pub as
	// `cap={}/{}`.  A healthy world run looks like cap=~fps/0..30.
	std::uint64_t snapNonCamera = 0;
	std::uint64_t snapSkipsSinceCam = 0;

	// ---- v1.14 probe: a census of the WRITERS sharing the perFrame buffer.
	// After v1.13 the orthographic writer is dropped, yet the published camera is
	// still byte-identical for a whole world session (19:39 run: pos == prevPos ==
	// (-243.05,-415.31,118.56), move 0.0000, path stuck at 63.91, clipDev pinned
	// at its floor of 0.000061 across 274 frames).  The decisive question is
	// whether ANY writer here moves its CameraPosAdjust: if none does, no
	// acceptance rule can ever produce motion and the SOURCE has to change.
	// The table is bounded to kSnapCensusMax signatures; snapCensusNew counts
	// arrivals whose position is not within 1.0 unit of any already-known one.
	static constexpr std::uint32_t kSnapCensusMax = 8;
	float snapCensus[kSnapCensusMax][3] = {};
	std::uint32_t snapCensusCount = 0;
	std::uint64_t snapCensusNew = 0;
	std::uint64_t snapCensusLogged = 0;

	// ---- v1.15: motion measured per projection family --------------------
	// v1.14's census counted "positions differing from the first eight seen",
	// which a single PARKED writer also increments without bound. These count
	// the step between CONSECUTIVE arrivals, bucketed by proj00, so a live
	// family is separable from a parked one by reading `moved` on [CAM] FAM.
	// v1.15b: 8 slots was not enough of a margin -- the menu period of the
	// 21:15 run alone showed four distinct proj00 values, and a family dropped
	// because the table was full is exactly the one we are hunting.
	static constexpr std::uint32_t kSnapFamMax = 16;
	bool snapFamSeen[kSnapFamMax] = {};
	float snapFamProj[kSnapFamMax] = {};
	float snapFamPos[kSnapFamMax][3] = {};
	bool snapFamHavePos[kSnapFamMax] = {};
	std::uint64_t snapFamMoved[kSnapFamMax] = {};
	float snapFamStep[kSnapFamMax] = {};
	std::uint64_t snapFamMovedTotal = 0;
	float snapFamStepTotal = 0.0f;
	std::uint64_t snapFamLogged = 0;
	bool snapFamOverflowLogged = false;

	// ---- v1.16: selection against the live player camera -------------------
	// read/match/adopt are per-second counters reset by the [CAM] PC dump;
	// snapPcAdopt is the cumulative total.
	std::uint64_t snapPcRead = 0;
	std::uint64_t snapPcMatch = 0;
	std::uint64_t snapPcAdopt = 0;
	std::uint64_t snapPcAdoptSec = 0;
	std::uint64_t snapPcReject = 0;   // v1.17: refused because it is not the camera
	bool snapPcEverMatched = false;   // the reference proved itself at least once
	float snapPcBestDist = 1.0e38f;
	float snapPcBestProj = 0.0f;
	float snapPcLast[3] = {};
	bool snapPcSawAny = false;
	// ---- v1.17: the reference as authority, not only as a selector ---------
	// snapPcRefSeen is a latch measured in seconds: set to kPcRefHoldSec on
	// every match, decremented once per second by the [CAM] PC dump. While it is
	// non-zero the reference is demonstrably arriving, so a non-camera arrival
	// may neither anchor nor be published. If the reference stops matching the
	// latch expires and the pre-v1.17 behaviour returns, which is what keeps this
	// gate from being able to wedge the lock.
	std::uint32_t snapPcRefSeen = 0;
	// v1.17: the motion witness, printed as eyeD on the [CAM] PC line.
	float snapPcEyeStep = 0.0f;
	float snapPcPrevEye[3] = {};
	bool snapPcEyeHave = false;
	// ---- v1.16: census detail, per family, per second ----------------------
	std::uint32_t snapFamArrSec[kSnapFamMax] = {};
	std::uint32_t snapFamSpanN[kSnapFamMax] = {};
	float snapFamMinP[kSnapFamMax][3] = {};
	float snapFamMaxP[kSnapFamMax][3] = {};

	// ---- v1.10: a MOVING family beats a STILL lock ---------------------- 
	// The 11:30 run is the measurement this exists for. The reset edge at
	// 11:33:15.482 released the lock and "the next arrival" took it -- and that
	// arrival was proj00=0.8391 at pos (-243.05,-415.31,118.56), a SCENE-FIXED
	// position byte-identical to the cameraPos the 23:10 run recorded two days
	// earlier. The real camera (proj00=1) then walked
	// (-125.7,210.8,188.4) -> (255.0,804.7,-94.4) and was refused ~90 times a
	// second, so frameBufferCopy stayed frozen (matChanges 168 for nine seconds,
	// path 65.41, move 0.0000, still 1570/90) and clipToPrevClip collapsed to I.
	//
	// CORRECTION (v1.17, 22:22 run): "the real camera (proj00=1)" above is
	// WRONG and was never measured -- it was inferred from travel, which is the
	// same inference the whole v1.00..v1.15 line rested on. The v1.16 ground
	// truth settled it: RE::PlayerCamera::cameraRoot->world.translate reads
	// (-243.049,-415.315,118.624) while the proj00=0.8391 arrival reads
	// (-243.0493,-415.3115,118.5582) -- 0.00 units apart, 397 times a second.
	// 0.8391 IS the player camera. proj00=1 sits at (-126.2,211.5,189.2) with
	// span (974.8,901.5,86.7) and stepSum 542149, i.e. a bucket of at least two
	// writers ~1000 units apart -- an offscreen/orthographic pass, not a walking
	// camera. Every conclusion v1.10..v1.15 drew from "the refused arriving
	// family is the camera" is therefore inverted. Kept as the record of how the
	// inversion happened; the v1.17 guard above does not depend on it.
	//
	// So the refused stream is allowed to take the anchor -- but only after it
	// has demonstrated travel of its own. kCamStillTol, the threshold v0.94
	// used unconditionally, is a dead constant (v1.09 finding D2): the lock has
	// no release path of its own, which is why 1570 consecutive refusals changed
	// nothing.
	float snapForeignMove = 0.0f;      // travel of the CURRENTLY refused family
	bool  snapForeignHave = false;     // the field above has a previous sample
	float snapForeignPos[3] = { 0.0f, 0.0f, 0.0f };
	float snapForeignProj00 = 0.0f;    // which family the travel belongs to
	std::uint64_t snapForeignTakeover = 0;  // times a moving family took the anchor

		// ---- v0.83: instrument the gate so a log can name which branch fires ----
		// snapFrozenReject / snapFrozenRepeats already existed but were never
		// printed, so the 13:22 run could not tell whether the v0.78 frozen gate
		// was the thing rejecting every arrival. These are observation only.
		std::uint64_t mapPerFrameHits = 0;      // Map() matched the perFrame buffer
		std::uint64_t unmapPerFrameHits = 0;    // Unmap() had a live tlsMappedFB
		std::uint64_t snapIdenticalArrivals = 0;  // matrix == snapLastMat
		std::uint64_t snapDifferentArrivals = 0;  // matrix != snapLastMat

		// v0.86: arrivals dropped because CameraViewProjUnjittered is not a
		// homogeneous matrix -- its [3][3] is not 1. The 14:20 run accepted a
		// matrix whose fourth row was (-0.00391655, 0.999991, 0.0015, 0), i.e.
		// [3][3] == 0: not a camera at all, but a mis-offset read of the
		// perFrame constant buffer. Legitimate cameras in the same log
		// (#2, #6301, #12349, #16764) all carry [3][3] == 1.
		std::uint64_t snapRejectShape = 0;
		// v0.84: how many times a different matrix reset the consecutive-identical
		// run. If this stays 0 for a whole run, the gate is still counting without
		// resetting and the freeze will come back.
		std::uint64_t snapFrozenResets = 0;

	private:
		FrameBuffer* mappedFrameBuffer = nullptr;
	};

	FrameGen& Get();
}
