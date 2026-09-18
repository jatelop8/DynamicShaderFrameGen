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
		// v0.58: per-frame serial, advanced once per Present (see DX12SwapChain.cpp).
		// v0.50 removed OnMainUpdateJitter, which was the ONLY writer of
		// engineFrameCount -> it stays 0 forever, while EnsureFrameToken still
		// used it as the new-frame test. Result: slGetNewFrameToken was called
		// exactly once, frame index stayed 0, frameToken never advanced, and
		// slSetConstants got rejected every frame (eErrorDuplicatedConstants=27)
		// -> per-frame constants (jitter / camera matrices / clipToPrevClip /
		// frame time / Reflex pacer data) were never refreshed -> bad
		// reprojection of every generated frame -> constant flicker.
		// v0.31 already hit this exact class of bug (“must pass a frame count
		// or the frame number stalls“); v0.50 reintroduced it.
		// v0.61: one-run self-diagnosis. Every counter needed to decide WHERE a
		// remaining flicker comes from is accumulated here and printed as a single
		// [XRAY] heartbeat line, so one launch produces a conclusive log instead of
		// a stack of probes running on four different cadences that cannot be
		// correlated with each other.
		struct Diag
		{
			std::uint64_t menuFrames = 0;    // real frames with a game menu open
			std::uint64_t worldFrames = 0;
			std::uint64_t menuEdges = 0;     // menu open/close transitions
			std::uint64_t resetTrue = 0;     // frames where reset was eTrue
			std::uint64_t constsOk = 0;
			std::uint64_t constsFail = 0;
			std::int32_t constsLastR = 0;
			// presented-per-real-frame histogram (what slDLSSGGetState reported),
			// split by menu/world; index = value, clamped to 7. This is the direct
			// evidence for “did eEnableFullscreenMenuDetection do anything”: if the
			// runtime honours it, presentedMenu collapses to 1 while presentedWorld
			// holds at the accepted multiplier.
			std::uint64_t presentedAll[8] = {};
			std::uint64_t presentedMenu[8] = {};
			std::uint64_t presentedWorld[8] = {};
			std::uint32_t presentedPrev = 0;
			std::uint32_t lastFlags = 0;
			std::uint32_t lastCountedSerial = 0xFFFFFFFFu;
			bool menuOpenNow = false;

			// v0.62: pacing / limiter evidence. reflexCapUs is the cap this build
			// actually handed to Reflex; the win* fields are the real-frame interval
			// window (measured in ReflexSleep, which runs exactly once per real
			// frame). 2026-09-17 21:40 perf.csv: frames 12..77 arrived at a
			// rock-steady 102.56 ms = 4 x the 25.641 ms cap, and the panel got 39
			// presented fps instead of the intended 156. min/avg/max on the same
			// line is what separates “the limiter is applied 4x too hard”
			// (quantised) from “the GPU genuinely needs 102 ms” (wanders).
			std::uint32_t reflexCapUs = 0;
			double winMinMs = 0.0;
			double winMaxMs = 0.0;
			double winSumMs = 0.0;
			std::uint64_t winN = 0;
			std::uint32_t longFrames = 0;
			// v0.64: camera-data validity accounting. A zero ClipToPrevClip is an
			// INVALID matrix, not “camera did not move”, and it collapses DLSS-G's
			// per-generated-frame reprojection. See the clamp in CheckFrameConstants.
			std::uint64_t camValid = 0;
			std::uint64_t camInvalid = 0;
			// ---- v0.65: reprojection source accounting ----
			// engPrevEqCur is the direct evidence for “the engine's previous viewProj
			// is useless“: when it equals cur, clipToPrevClip degenerates to identity
			// and DLSS-G is told the camera never moved. engCurFrozenRun / derived*
			// cover the case where the engine's CUR matrix is itself frozen.
			std::uint64_t engPrevEqCur = 0;
			std::uint64_t engPrevDiffers = 0;
			std::uint64_t engPrevZero = 0;
			std::uint64_t engCurFrozenRun = 0;
			std::uint64_t derivedChecked = 0;
			std::uint64_t derivedMatch = 0;
			std::uint64_t derivedUsed = 0;
			std::uint64_t prevHistoryHits = 0;
			std::uint64_t prevHistoryMiss = 0;
			// ---- v1.02: rebuilt previous-camera accounting ----
			// camPrevOk: the frame carried a usable rebuild of the PREVIOUS
			// camera (Proj @ [R_prev | -R_prev @ eye_prev]). camPrevUsed: that
			// matrix was the one actually handed to DLSS-G. A value that stays 0
			// while camValid rises means the rebuild never took, and the old
			// engine-prev path is still feeding clipToPrevClip.
			std::uint64_t camPrevOk = 0;
			std::uint64_t camPrevUsed = 0;
			// v0.82: no self-maintained history -> seed from the engine's prev.
			// This build reports the engine prev as an all-zero matrix
			// (engPrevZero=241), so a value that stays 0 means the seed never took.
			std::uint64_t prevSeededFromEngine = 0;
			// v0.82: no-history branch reused a legal previous clipToPrevClip instead
			// of writing identity. Identity means 'camera did not move' to DLSS-G.
			std::uint64_t prevMissUsedLastGood = 0;
			std::uint64_t reprojSource = 0;
			// v0.66: per-tid call counting. A sentinel (“multi-thread” =
			// 0xFFFFFFFF) cannot tell a one-off thread handover from real
			// concurrency - count each tid separately instead.
			std::uint32_t tidA = 0, tidB = 0, tidC = 0;
			std::uint64_t tidCallsA = 0, tidCallsB = 0, tidCallsC = 0;
			// v0.66: determinant accounting for the clipToPrevClip guard.
			// Legal reprojection matrices must have det(upper-left 3x3) ~= 1.
			float detMin = 1.0e30f;
			float detMax = -1.0e30f;
			std::uint64_t detGuard = 0;
			// v0.67：守卫触发时改用「保留上一帧合法矩阵」而不是单位矩阵的次数。
			// detHold == detGuard 说明一直在吃上一帧的值（数据源仍未修好）。
			std::uint64_t detHold = 0;
			float curMagLast = 0.0f;
			float engPrevMagLast = 0.0f;
			float derivedMatchErr = 0.0f;
			float clipDevMax = 0.0f;
			// v0.88: max |fixedViewProj - engineViewProj|. Non-zero proves the
			// rebuilt matrix really carries the translation the engine omits;
			// -1 means the rebuild was unavailable this frame.
			float fixedVpDev = -1.0f;
			// ---- v1.03: MFG capability + stall attribution ----
			// hwMaxSeen is what slDLSSGGetState reported (numFramesToGenerateMax).
			// reqStepMax is the highest step the ladder was ever allowed to
			// request this session. hwMaxSeen < reqStepMax is the signature of
			// "the override outran the runtime": the ladder then pays one
			// multi-second rejected frame per rung of the descent, which is
			// exactly what the 18:23 run did (4x rejected, then 3x rejected,
			// with a 19945 ms frame in between).
			std::uint32_t hwMaxSeen = 0;
			std::uint32_t reqStepMax = 0;
			std::uint64_t mfgRungsSkipped = 0;   // rungs the capability guard removed
			std::uint64_t setOptStalls = 0;      // frames where the call outran the guard
		};
		Diag diag;

		// v0.70: state, not statistics, so they live outside Diag. menuWasOpen is
		// the previous frame's sample; menuResetPending is set when a menu opens
		// and consumed by CheckFrameConstants, which may run a frame later (it
		// does not run at all while the guard is engaged).
		bool menuWasOpen = false;
		bool menuResetPending = false;

		std::uint32_t frameSerial = 0;
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
		// eErrorMissingOrInvalidAPI(28)（“Could not find evaluateFeature callbacks”）
		PFun_slSetTagForFrame* slSetTagForFrame{};
		PFun_slSetConstants* slSetConstants{};
		PFun_slGetFeatureFunction* slGetFeatureFunction{};
		PFun_slGetNewFrameToken* slGetNewFrameToken{};
		PFun_slSetD3DDevice* slSetD3DDevice{};
		// v0.32（对齐 open-shaders）：slSetFeatureLoaded——设备绑定后显式请求
		// 加载 Reflex/PCL（SL 日志 “sl.reflex has no registered hooks” = 未激活）
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
		// pacing 乱 → 频闪（SL 日志 “Plugin 'sl.reflex' has no registered hooks” 实锤）。
		PFun_slReflexSleep* slReflexSleep{};
		PFun_slReflexSetOptions* slReflexSetOptions{};
		// v0.5.23：PCL marker（ePresentStart/ePresentEnd）——RSYNC（Reflex Sync pacer）
		// 靠它建立帧节奏；缺失 → RSYNC 实例 null → slAllocateResources 0xC0000005
		// （DLSS-G 指南 8.0：sl.reflex 集成必须标记 PresentStart/PresentEnd）
		PFun_slPCLSetMarker* slPCLSetMarker{};

		// v0.31（对齐 open-shaders Streamline.cpp:300-320）：多倍帧生成
		std::uint32_t dlssgMaxFramesToGenerate = 1;   // 运行时上报上限（**永不被覆盖改写**，只读）
		std::uint32_t dlssgFramesToGenerate = 1;      // 本次**向运行时请求**的插帧数
		// v0.51：诚实上报 + 安全阶梯探测。
		// v0.50 的 MFGMaxFramesOverride 只抬高本文件里的 clamp 上限，运行时仍按自己的能力
		// 校验 → slDLSSGSetOptions 每帧被拒（eErrorInvalidState=38），而插件照旧按请求值
		// 呈现 → 频闪 + 进不去游戏。现在：请求值逐级下探直到运行时接受并锁定；被拒事实
		// 如实记录；绝不把“请求值”当成“生效值”。
		std::uint32_t dlssgEffectiveMax = 1;    // max(运行时上限, 覆盖值) —— 只是请求上限，≠ 被接受

		// ---- v1.03: external MFG kernel unlocker presence ---------------------
		// DLSSG-Transfusion hooks slGetFeatureFunction and replaces
		// slDLSSGSetOptions with its own wrapper BEFORE this plugin ever gets a
		// pointer to it. Its log proves the replacement works on Ada:
		//     Applied fixed multiplier: 4x, result=0 (eOk)
		//     DLSS-G actual presentation count: 4x (maximum generated frames=5)
		//     [PERF] 4x | Kernel: Ada
		// while a direct request from this plugin for the same 4x comes back
		// eErrorInvalidState(38). Two writers on one viewport is a fight, and the
		// one that already works is not this one: when an unlocker is present,
		// this plugin stops writing numFramesToGenerate and lets the unlocker own
		// the multiplier. Everything else this plugin does - the rebuilt previous
		// camera, the family lock, the menu guard - is unaffected and remains the
		// reason the frames are worth generating at all.
		std::uint32_t dlssgAcceptedFrames = 0;  // 运行时**实际接受**的插帧数（0 = 被拒/尚未探测出）
		// ---- v1.03: stall governor -------------------------------------------
		// The 18:23 run presented ONE real frame in 33 s of uptime. Every frame
		// after the first sat in slDLSSGSetOptions for seconds, and because the
		// probe re-armed DLSS-G unconditionally the stall fed itself: a runtime
		// that is slow once stayed slow forever. The governor makes a long frame
		// cost exactly one long frame - the next ones go on cooldown until frame
		// times recover - and it records the stall so the watchdog line can name
		// the call instead of saying "still in d3d11.
		std::uint64_t mfgProbeStallMs = 0;      // duration of the frame that tripped it
		std::uint32_t mfgProbeCooldown = 0;     // frames left to skip the probe
		bool mfgProbeSkipAll = false;           // never resume: proven unusable adapter
		bool mfgInSetOptions = false;           // in-call flag, read by the watchdog

		std::uint32_t mfgProbeStep = 0;         // 阶梯探测当前档（0 = 未开始）
		bool mfgProbeLatched = false;           // 已有一档被接受 → 停止下探
		// v0.79: shown in the “MFG probe” log line so LATCHED can be told apart
		// from “the ladder has not finished descending yet”.
		bool mfgProbeWasBlocked = false;        // 上一次探测是在菜单/守卫内 => 结果不可信
		bool mfgProbeLoggedBlocked = false;     // [MFG] 每条边沿只打一次
		// v0.53: the runtime's own measurement. Streamline documents
		// numFramesActuallyPresented as “number of frames presented since the last
		// slDLSSGGetState call“ - a PER-INTERVAL count, not a cumulative one.
		// SetDLSSGOptions runs once per real frame, so this value IS the multiplier that
		// actually happened: 1 = no interpolation at all (rejected, or DLSSG idle),
		// 2 = 2x, 4 = 4x. It is the only number that proves MFG really generates frames,
		// and the FPS overlay reads it instead of inventing a factor.
		std::uint32_t dlssgFramesPresentedLast = 0;  // 0 = never queried yet

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

		// v0.50：MFG 上限覆盖（老卡多倍帧生成解锁，见 Streamline.cpp 实现注释）
		void ApplyMfgOverride(std::uint32_t a_hwMax);

		// 设置 D3D 设备（slSetD3DDevice）
		void SetD3DDevice(ID3D11Device* a_device);
		void SetD3D12Device(ID3D12Device* a_device);

		// v0.5.10：upgrade 接口为 SL 代理（swapchain 必调，presentCommon 路径）
		void UpgradeInterface(void** a_ppInterface);

		// 每帧：设置相机常量 + 评估帧生成（v0.50：DLSS 超分已拔掉，仅保留 DLSSG 插帧）
		// v0.3：DLSSG 插帧（D3D12 路径）——设置选项 + 评估
		// v0.71: a_enable=false tells the runtime to stop frame generation without
		// touching any other option. Required when the window is not in the
		// foreground: DLSS-G keeps presenting into the swap chain, and a
		// FLIP_DISCARD swap chain whose buffers nobody releases blocks Present().
		void SetDLSSGOptions(std::uint32_t a_width, std::uint32_t a_height,
			std::uint32_t a_mvecDepthW, std::uint32_t a_mvecDepthH, DXGI_FORMAT a_colorFormat,
			bool a_enable = true);
		// 返回是否成功（失败 → 调用方 Present 兜底直通，避免画面冻结）
		bool EvaluateDLSSG(ID3D12GraphicsCommandList* a_cmdList,
			ID3D12Resource* a_colorIn, ID3D12Resource* a_colorOut,
			ID3D12Resource* a_depth, ID3D12Resource* a_motionVectors,
			const FrameBuffer& a_frameBuffer);

		// v0.3：DLSSG 运行时要求 Reflex 激活（FrameGen.cpp 调用）
		void ActivateReflex();

		// v0.37（对齐 open-shaders EnsureFrameToken:411-426）：每帧统一 frame token——
		// 本帧第一次调用取新 token（帧号推进），同帧后续调用复用（IsNewFrame 判断）。
		// 之前 ReflexSleep/marker 用旧 token、EvaluateDLSSG 才取新 token → 同一帧的
		// PCL marker 跨两个 token → RSYNC 帧节奏标记错位 → pacing 乱 → 频闪。
		bool EnsureFrameToken();

		// v0.32（对齐 open-shaders Streamline.cpp:890-924）：每帧 Reflex sleep——
		// 模拟开始前调用（Present 开头），slReflexSleep 建立 RSYNC 节奏，返回后
		// 发 eSimulationStart marker。DLSSG 插帧 pacing 的必需输入。
		void ReflexSleep();

		// 释放
		void DestroyResources();

		// v0.63：游戏菜单是否打开。与 CheckFrameConstants 内部用的是同一份实现
		// （GameMenuOpenNow），Present 路径用它自行实现 eEnableFullscreenMenuDetection
		// —— Transfusion 会把该 flag 从 DLSS-G options 里剥掉，运行时收不到。
		bool MenuOpenNow();

		// v0.70: sample “is a game menu up” once per frame, BEFORE the guard
		// that consumes it, and let every consumer read that one sample.
		// Returns the sampled state. The old in-CheckFrameConstants placement
		// made the guard unverifiable - see PollMenuState() in Streamline.cpp.
		bool PollMenuState();
		bool MenuIsOpen() const;



		// v0.79: run the multiplier ladder outside the menu guard.
		// The ladder (Streamline.cpp SetDLSSGOptions) only ran on frames that
		// took Present()'s else-if branch - i.e. never while a menu was up - so a
		// REJECTED step could never step down and every “once per real frame”
		// counter in ReflexSleep() froze with it. ReflexSleep() reads
		// dlssgAcceptedFrames to compute capMult, so the FPS overlay, the live
		// menu slider and the Reflex cap were all pinned to one number for the
		// whole menu. Measured 2026-09-18 08:59: 18.08 s of menu, generation 0.
		void ProbeMfgLadder();
		void ProbeMfgLadderNote(bool a_blocked);
		// v1.03: one long frame must not cascade. Called once per real frame with
		// the interval that just elapsed; returns false while the probe is on
		// cooldown, so the caller skips the DLSS-G call entirely.
		bool MfgStallGovAllow(std::uint32_t a_frameUs);

	private:
		void CheckFrameConstants(const FrameBuffer& a_fb, float a_aspect, float a_near, float a_far);
	};
}
