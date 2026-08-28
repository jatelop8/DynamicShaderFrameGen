#pragma once

// ImguiMenu.h - v0.7: in-game settings menu (Dear ImGui + D3D11 backend)
// Menu toggle: Home long-press. Render point: DX12SwapChain::Present (
// FSR3 branch, before copying shared texture to D3D12) - menu drawn onto
// the shared texture, goes through FG with the frame.
// Input: manual (mouse GetCursorPos/buttons polled each frame + keyboard events
// forwarded from InputEventHandler). No WndProc hook needed.

#include <cstdint>
#include <d3d11.h>

struct ImGuiContext;

namespace FrameGen
{
	class FrameGen;

	class ImguiMenu
	{
	public:
		static ImguiMenu* GetSingleton()
		{
			static ImguiMenu singleton;
			return &singleton;
		}

		void Init(ID3D11Device* a_device, ID3D11DeviceContext* a_context, HWND a_hwnd);
		void Shutdown();

		bool visible = false;
		void Toggle() { visible = !visible; }

		// Draw each frame (called in Present FSR3 branch, before shared-texture copy)
		void Draw(FrameGen& a_fg);

		// Keyboard event forwarding (called from InputEventHandler)
		void OnKeyEvent(std::uint32_t a_key, bool a_pressed);

	private:
		bool initialized = false;
		HWND hwnd = nullptr;
		void DrawMenu(FrameGen& a_fg);
	};
}
