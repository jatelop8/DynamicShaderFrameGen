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
			// v1.52：共存开关检查（默认两个都是 1 = 与 v1.51 行为完全一致）。
			// CommunityShaders 会 detour/thunk 同一批引擎函数头，两边都以为自己是链头
			// -> 跳转目标互相覆盖 -> EXCEPTION_BREAKPOINT（crash-2026-09-22-12-05-34）。
			// 装了 CS 的整合包必须把 INI 里这两项改成 0。
			if (!FrameGen::Get().settings.menuDrawHook || !FrameGen::Get().settings.pollInputHook) {
				SKSE::log::warn("[FrameGen] LEGACY-HOOK SUPPRESSION ACTIVE: MenuDrawHook={} PollInputHook={} "
					"- the engine hook(s) CommunityShaders also owns are NOT installed this run",
					FrameGen::Get().settings.menuDrawHook ? 1 : 0,
					FrameGen::Get().settings.pollInputHook ? 1 : 0);
			}
			// 输入开关键（Home）——DataLoaded 后 BSInputDeviceManager 可用
			FrameGen::Get().InstallInputHook();
			// v0.7.11：Main_UpdateJitter hook（渲染前设 DRS + jitter，CS 同款）
			FrameGen::Get().InstallDRSHook();
			// v0.48：Main_PostProcessing hook（DLSS 超分迁到 ENB 前）
			FrameGen::Get().InstallMainPostProcessingHook();
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

// v1.09: keep the previous session's log.
//
// CommonLibSSE-NG's spdlog sink is a rotating logger whose base file is
// truncated when it is opened, so every launch destroys the previous run's
// evidence. That is exactly how the one run that reproduced the freeze
// (2026-09-19 07:36) was lost: it was overwritten six minutes later by the next
// launch, and the freeze could no longer be re-examined from the log that saw
// it. One copy before SKSE::Init keeps it.
//
// The archive name is `DynamicShaderFrameGen.<YYYYMMDD>-<HHMMSS>.log`, which
// sorts chronologically. Archives older than 7 days are deleted. The delete is
// restricted to files matching `DynamicShaderFrameGen.20*.log`, so it can never
// touch the watchdog log or any other plugin's log -- the `20` prefix is the
// year, and the watchdog log is named `.watchdog.log`.
static void ArchivePreviousLog()
{
	const char* wd = FrameGen::WatchdogLogPath();
	if (wd == nullptr || wd[0] == '\0')
		return;

	char dir[MAX_PATH] = {};
	std::snprintf(dir, sizeof(dir), "%s", wd);
	int cut = -1;
	for (int i = 0; dir[i] != '\0'; ++i)
		if (dir[i] == '\\')
			cut = i;
	if (cut <= 0)
		return;
	dir[cut] = '\0';

	char src[MAX_PATH] = {};
	std::snprintf(src, sizeof(src), "%s\\DynamicShaderFrameGen.log", dir);
	if (::GetFileAttributesA(src) == INVALID_FILE_ATTRIBUTES)
		return;   // no previous run to preserve

	SYSTEMTIME st{};
	::GetLocalTime(&st);
	for (int attempt = 0; attempt < 120; ++attempt) {
		char dst[MAX_PATH] = {};
		::GetLocalTime(&st);   // refresh so a long copy cannot skew the stamp
		std::snprintf(dst, sizeof(dst),
			"%s\\DynamicShaderFrameGen.%04d%02d%02d-%02d%02d%02d.log",
			dir, st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
		if (::CopyFileA(src, dst, TRUE))       // TRUE = never overwrite
			break;
		if (::GetLastError() != ERROR_FILE_EXISTS)
			break;
		::Sleep(1000);                          // collision: wait for the next second
	}

	// Prune. Cutoff string is YYYYMMDD; the stamp starts at offset 21, which is
	// the length of "DynamicShaderFrameGen.".
	FILETIME nowFt{};
	::GetSystemTimeAsFileTime(&nowFt);
	ULARGE_INTEGER t{};
	t.LowPart = nowFt.dwLowDateTime;
	t.HighPart = nowFt.dwHighDateTime;
	t.QuadPart -= 7ull * 24ull * 60ull * 60ull * 10000000ull;
	FILETIME cutFt{};
	cutFt.dwLowDateTime = t.LowPart;
	cutFt.dwHighDateTime = t.HighPart;
	SYSTEMTIME cutSt{};
	char cutoff[16] = {};
	if (::FileTimeToSystemTime(&cutFt, &cutSt))
		std::snprintf(cutoff, sizeof(cutoff), "%04d%02d%02d", cutSt.wYear, cutSt.wMonth, cutSt.wDay);
	if (cutoff[0] == '\0')
		return;

	char pattern[MAX_PATH] = {};
	std::snprintf(pattern, sizeof(pattern), "%s\\DynamicShaderFrameGen.20*.log", dir);
	WIN32_FIND_DATAA fd{};
	HANDLE hf = ::FindFirstFileA(pattern, &fd);
	if (hf == INVALID_HANDLE_VALUE)
		return;
	do {
		if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0u)
			continue;
		const char* stamp = fd.cFileName + 21;
		bool older = true;
		for (int i = 0; i < 8; ++i) {
			if (stamp[i] == '\0') { older = false; break; }
			if (stamp[i] < cutoff[i]) break;
			if (stamp[i] > cutoff[i]) { older = false; break; }
		}
		if (!older)
			continue;
		char victim[MAX_PATH] = {};
		std::snprintf(victim, sizeof(victim), "%s\\%s", dir, fd.cFileName);
		::DeleteFileA(victim);
	} while (::FindNextFileA(hf, &fd) != 0);
	::FindClose(hf);
}

extern "C" DLLEXPORT bool SKSEAPI SKSEPlugin_Load(const SKSE::LoadInterface* a_skse)
{
	// SKSE::Init 内部已自动初始化 spdlog 日志（CommonLibSSE-NG 4.x）
	// v1.09: SKSE::Init opens the spdlog sink, which truncates the log file. Copy
	// the previous session's log out of the way first, or the run that reproduced
	// the bug is destroyed by the run that follows it.
	// v1.10: the watchdog path must exist BEFORE the copy below, because
	// ArchivePreviousLog() resolves the directory from it and returns at its
	// first guard when the buffer is still empty. v1.09 had the two calls in
	// the other order, and the 11:30 run is the proof: it produced no
	// DynamicShaderFrameGen.20*.log at all, so the archive never ran.
	// InitWatchdogLogPath() is SHGetFolderPathA plus a snprintf - safe before
	// SKSE::Init, idempotent, and it stays cached for the DllMain exit probe.
	FrameGen::InitWatchdogLogPath();
	ArchivePreviousLog();

	SKSE::Init(a_skse);

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
