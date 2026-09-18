// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
// Derived from open-source projects (all GPL-3.0):
//   - Skyrim Community Shaders (https://github.com/doodlum/skyrim-community-shaders)
//   - ENBFrameGeneration (https://github.com/doodlum/ENBFrameGeneration)
// Other components: Dear ImGui / CommonLibSSE-NG / Microsoft Detours (MIT).

// DynamicShaderFrameGen —— 独立帧生成插件（DLSS FG，作用于 ENB）
// SKSE 插件入口：INI 加载 + D3D11CreateDeviceAndSwapChain IAT 钩子
//（游戏启动早期，D3D 设备未创建时安装）

#include <RE/Skyrim.h>
#include <SKSE/SKSE.h>

#include <Windows.h>

#include <cstdio>

#include "FrameGen.h"

#define DLLEXPORT __declspec(dllexport)

namespace
{
	void MessageHandler(SKSE::MessagingInterface::Message* a_msg)
	{
		switch (a_msg->type) {
		case SKSE::MessagingInterface::kDataLoaded:
			SKSE::log::info("[FrameGen] Data loaded - frame generation plugin ready");
			// 输入开关键（Home）——DataLoaded 后 BSInputDeviceManager 可用
			FrameGen::Get().InstallInputHook();
			// v0.50（用户拍板拔掉 DLSS 超分）：移除 InstallDRSHook + InstallMainPostProcessingHook。
			// 引擎回到 2560 全分辨率渲染（无 DRS、无 DLSS 超分、无 Halton jitter），
			// 只保留 DLSS5(DLSSNR) + FSR3 FG 串联。DLSS 超分/DRS/jitter 相关代码保留但不调用。
			// DLSS5 Neural Rendering 入口（MenuManagerDrawInterfaceStart，UI 绘制前）
			FrameGen::Get().InstallMenuHook();
			break;
		}
	}
}

// Modern CommonLibSSE-NG convention: SKSEPlugin_Version + SKSEPlugin_Load.
// Project rule (2026-08-19): UsesAddressLibrary() + UsesUpdatedStructs() only.
// No UsesNoStructs() (writes versionIndependenceEx @0x304, unknown to SKSE 2.2.6),
// no CompatibleVersions (would hard-lock game version -> fatal error).
extern "C" DLLEXPORT constinit auto SKSEPlugin_Version = []() noexcept {
	SKSE::PluginVersionData v;
	v.PluginName("DynamicShaderFrameGen");
	v.PluginVersion(1);
	v.UsesAddressLibrary();
	v.UsesUpdatedStructs();
	return v;
}();

extern "C" DLLEXPORT bool SKSEAPI SKSEPlugin_Query(const SKSE::QueryInterface* a_skse, SKSE::PluginInfo* a_info)
{
	a_info->infoVersion = SKSE::PluginInfo::kVersion;
	a_info->name = SKSEPlugin_Version.pluginName;
	a_info->version = SKSEPlugin_Version.pluginVersion;

	if (a_skse->IsEditor()) {
		return false;
	}

	return true;
}

extern "C" DLLEXPORT bool SKSEAPI SKSEPlugin_Load(const SKSE::LoadInterface* a_skse)
{
	// SKSE::Init 内部已自动初始化 spdlog 日志（CommonLibSSE-NG 4.x）
	SKSE::Init(a_skse);

	// v0.73: cache the watchdog log path before anything can go wrong, so the
	// exit probe in DllMain is a pure Win32 append with no path resolution.
	FrameGen::InitWatchdogLogPath();

	SKSE::log::info("[FrameGen] DynamicShaderFrameGen loaded (build {} {})", __DATE__, __TIME__);

	// v0.61: identify the exact DLL the game loaded. "Which copy is actually
	// running" (build tree vs MO2 mods dir vs overwrite) could not be answered
	// from the log more than once. Module path + write time settles it in one line.
	{
		HMODULE self = nullptr;
		if (::GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
		                         GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
		        reinterpret_cast<LPCSTR>(&MessageHandler), &self) &&
			self) {
			char dllPath[MAX_PATH] = {};
			::GetModuleFileNameA(self, dllPath, MAX_PATH);
			WIN32_FILE_ATTRIBUTE_DATA fad{};
			// v0.69: real run time. RUN START below prints __DATE__/__TIME__, which is
			// the BUILD stamp -- it reads like the session start and misled two separate
			// timeline reconstructions (the 23:07 session looked like it began 22:59).
			SYSTEMTIME runSt{};
			::GetLocalTime(&runSt);
			SKSE::log::info("[XRAY] RUN TIME {}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}",
				runSt.wYear, runSt.wMonth, runSt.wDay, runSt.wHour, runSt.wMinute, runSt.wSecond);
			SYSTEMTIME st{};
			if (::GetFileAttributesExA(dllPath, GetFileExInfoStandard, &fad) &&
				::FileTimeToSystemTime(&fad.ftLastWriteTime, &st)) {
				SKSE::log::info("[XRAY] RUN START {} - dll={} mtime={:04d}-{:02d}-{:02d} {:02d}:{:02d} size={}B",
					__DATE__ " " __TIME__, dllPath, st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute,
					static_cast<unsigned long long>(
						(static_cast<unsigned long long>(fad.nFileSizeHigh) << 32) |
						static_cast<unsigned long long>(fad.nFileSizeLow)));
			} else {
				SKSE::log::info("[XRAY] RUN START {} - dll={}", __DATE__ " " __TIME__, dllPath);
			}
		}
	}

	auto& fg = FrameGen::Get();

	// 1. INI 配置
	fg.LoadConfig();

	// 2. D3D11CreateDeviceAndSwapChain IAT 钩子（游戏启动早期，设备未创建）
	fg.InstallCreateDeviceHook();

	// 3. 消息接口
	SKSE::GetMessagingInterface()->RegisterListener(MessageHandler);

	return true;
}

// v0.73: the exit probe.
//
// Every run in this investigation ended the same way - a last line, then every
// thread stops inside one 200 ms watchdog tick - and the logs could not say
// whether the process died or the game was simply closed, because a healthy last
// tick is also what a normal quit looks like.
//
// DLL_PROCESS_DETACH is the one place that knows. It runs when the process leaves
// through the loader: ExitProcess, i.e. the game quitting (or crashing and
// reaching the unhandled-exception filter). It does NOT run when the process is
// killed from outside by TerminateProcess. So one appended line splits the
// remaining possibilities in two, and it is written with the Win32 API rather
// than the CRT because the CRT's ordering during process detach is not something
// to be clever about.
BOOL APIENTRY DllMain(HMODULE a_module, DWORD a_reason, LPVOID a_reserved)
{
	(void)a_module;
	if (a_reason == DLL_PROCESS_DETACH && a_reserved != nullptr) {
		// a_reserved != null during DETACH means the whole process is going away.
		const char* path = FrameGen::WatchdogLogPath();
		if (path && path[0] != '\0') {
			HANDLE h = ::CreateFileA(path, FILE_APPEND_DATA,
				FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS,
				FILE_ATTRIBUTE_NORMAL, nullptr);
			if (h != INVALID_HANDLE_VALUE) {
				SYSTEMTIME st{};
				::GetLocalTime(&st);
				char buf[256];
				const int n = std::snprintf(buf, sizeof(buf),
					"[exit] DLL_PROCESS_DETACH %02d:%02d:%02d.%03d reserved=%p  "
					"<== the process left through the loader (the game quit itself, or a "
					"crash reached the unhandled-exception filter); a killed process "
					"writes no line like this\n",
					st.wHour, st.wMinute, st.wSecond, st.wMilliseconds, a_reserved);
				if (n > 0) {
					DWORD written = 0;
					::WriteFile(h, buf, static_cast<DWORD>(n), &written, nullptr);
				}
				::CloseHandle(h);
			}
		}
	}
	return TRUE;
}
