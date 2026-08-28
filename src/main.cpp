// DynamicShaderFrameGen —— 独立帧生成插件（DLSS FG，作用于 ENB）
// SKSE 插件入口：INI 加载 + D3D11CreateDeviceAndSwapChain IAT 钩子
//（游戏启动早期，D3D 设备未创建时安装）

#include <RE/Skyrim.h>
#include <SKSE/SKSE.h>

#include <Windows.h>

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
			// v0.7.11：Main_UpdateJitter hook（渲染前设 DRS + jitter，CS 同款）
			FrameGen::Get().InstallDRSHook();
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

	SKSE::log::info("[FrameGen] DynamicShaderFrameGen loaded");

	auto& fg = FrameGen::Get();

	// 1. INI 配置
	fg.LoadConfig();

	// 2. D3D11CreateDeviceAndSwapChain IAT 钩子（游戏启动早期，设备未创建）
	fg.InstallCreateDeviceHook();

	// 3. 消息接口
	SKSE::GetMessagingInterface()->RegisterListener(MessageHandler);

	return true;
}
