"""v0.73: the exit probe, and a watchdog that cannot block.

Why this exists
---------------
Every run in this investigation ends the same way: the last line is written, then
every thread stops inside one 200 ms watchdog tick. The logs could never say
whether the process died or the player simply closed the game - and a *healthy*
last tick is also what a normal quit looks like, so the watchdog alone is blind
to the difference. Two things fix that:

 1. DLL_PROCESS_DETACH. It runs when the process leaves through the loader
    (ExitProcess: a normal quit, or a crash that reached the unhandled-exception
    filter). It does NOT run when the process is killed from outside
    (TerminateProcess). One line in the watchdog file turns "no idea" into
    "left through the loader" versus "was killed".

 2. The fence queries move off the watchdog thread. v0.72 put two
    GetCompletedValue() calls in the watchdog itself - the one thread that has to
    keep writing while everything else is stuck, and those calls go into the
    display driver. A watchdog that can block is not a watchdog. A dedicated
    sampler thread now owns them, and it only samples once a hang is already
    suspected, so normal play never puts a non-owning thread inside the driver.

Also in this patch:
  * the watchdog line gains a wall clock, so it can be lined up against the other
    logs without first reverse-engineering the monotonic counter (today's cost);
  * the unfocused bypass stops throwing. It runs inside the engine's own Present
    call frame, which has no handler for our exceptions: a throw out of it ends
    the process on the spot, with no crash log and no flushed tail - which is
    exactly the shape being investigated.

Dry run by default; --apply writes. Refuses if any anchor is missing or
ambiguous, if the change is already present, or if the post-checks fail.
"""

import hashlib
import os
import shutil
import sys
import time

ROOT = r"D:/Modding/DynamicShaderFrameGen"
CPP = os.path.join(ROOT, "src/DX12SwapChain.cpp")
HDR = os.path.join(ROOT, "src/DX12SwapChain.h")
MAIN = os.path.join(ROOT, "src/main.cpp")

STAMP = time.strftime("%Y%m%d-%H%M%S")

# A marker per change, checked before anything else: re-running the script must be
# refused, not silently doubled.
MARKERS = [
    "v0.73: the fence values now come from the sampler thread",
    "v0.73: samples the GPU timeline from its own thread",
    "v0.73: no throw here",
    "v0.73: the exit probe.",
]

# ---------------------------------------------------------------------------
# DX12SwapChain.cpp
# ---------------------------------------------------------------------------

C1_OLD = """		if (ourRoot && fgRoot)
			return ourRoot == fgRoot;
		return fg == a_hwnd;
	}
"""

C1_NEW = """		if (ourRoot && fgRoot)
			return ourRoot == fgRoot;
		return fg == a_hwnd;
	}

	// v0.73: everything the watchdog needs is an atomic it can read without ever
	// entering the driver, a lock, or the CRT.
	static bool g_bypassReported = false;                    // one BYPASS line per focus loss
	static std::atomic<long long> g_lastSilentMs{ -1 };      // published by the watchdog
	static std::atomic<unsigned long long> g_hangFence11{ ~0ull };
	static std::atomic<unsigned long long> g_hangFence12{ ~0ull };
	static std::atomic<unsigned long long> g_samplerTicks{ 0 };

	// v0.73: the watchdog log path, resolved once at plugin load and kept in a plain
	// char buffer. DllMain needs it during process detach, where calling
	// SHGetFolderPath or touching the CRT is not worth the risk.
	static char g_watchdogLogPath[MAX_PATH * 2] = {};

	void InitWatchdogLogPath()
	{
		// Same directory SKSE writes its own logs to, so one folder holds the story.
		std::string p;
		char buf[MAX_PATH] = {};
		if (SUCCEEDED(::SHGetFolderPathA(nullptr, CSIDL_PERSONAL, nullptr, 0, buf))) {
			p = buf;
			p += "\\\\My Games\\\\Skyrim Special Edition\\\\SKSE\\\\";
		}
		p += "DynamicShaderFrameGen.watchdog.log";
		std::snprintf(g_watchdogLogPath, sizeof(g_watchdogLogPath), "%s", p.c_str());
	}

	const char* WatchdogLogPath()
	{
		return g_watchdogLogPath;
	}
"""

C2_OLD = """void DX12SwapChain::StartWatchdog()
	{
		static std::atomic<bool> started{ false };
		bool expected = false;
		if (!started.compare_exchange_strong(expected, true))
			return;

		// Same directory SKSE writes its own logs to, so one folder holds the story.
		std::string path;
		{
			char buf[MAX_PATH] = {};
			if (SUCCEEDED(::SHGetFolderPathA(nullptr, CSIDL_PERSONAL, nullptr, 0, buf))) {
				path = buf;
				path += "\\\\My Games\\\\Skyrim Special Edition\\\\SKSE\\\\";
			}
			path += "DynamicShaderFrameGen.watchdog.log";
		}
"""

C2_NEW = """	// v0.73: the only thread allowed to touch the fences besides the render thread,
	// and it does nothing else. It samples ONLY while the render thread has already
	// been silent for over 1.5 s, so ordinary play never has a non-owning thread
	// inside the display driver, and a hang still gets the answer the watchdog
	// cannot produce on its own:
	//   stim keeps climbing -> the GPU timeline is alive, the render thread is
	//                          parked in CPU-side code;
	//   stim frozen while the watchdog keeps writing -> the sampler itself is parked
	//                          in the driver, which is a GPU/driver wedge.
	void DX12SwapChain::StartGpuSampler()
	{
		static std::atomic<bool> started{ false };
		bool expected = false;
		if (!started.compare_exchange_strong(expected, true))
			return;

		std::thread([this]() {
			for (;;) {
				std::this_thread::sleep_for(std::chrono::milliseconds(200));
				if (g_lastSilentMs.load() < 1500)
					continue;   // no suspected hang: stay out of the driver
				const unsigned long long f11 = d3d11Fence
					? static_cast<unsigned long long>(d3d11Fence->GetCompletedValue()) : ~0ull;
				const unsigned long long f12 = d3d12Fence
					? static_cast<unsigned long long>(d3d12Fence->GetCompletedValue()) : ~0ull;
				g_hangFence11.store(f11);
				g_hangFence12.store(f12);
				g_samplerTicks.fetch_add(1);
			}
		}).detach();
	}

	void DX12SwapChain::StartWatchdog()
	{
		static std::atomic<bool> started{ false };
		bool expected = false;
		if (!started.compare_exchange_strong(expected, true))
			return;

		StartGpuSampler();

		// v0.73: path comes from InitWatchdogLogPath() so DllMain can reuse it.
		const std::string path = WatchdogLogPath();
"""

C3_OLD = """				const long long silent = lastEnd ? (nowMs - lastEnd) : -1;
"""

C3_NEW = """				const long long silent = lastEnd ? (nowMs - lastEnd) : -1;
				g_lastSilentMs.store(silent);   // v0.73: lets the sampler decide when to look
"""

C4_OLD = """					// v0.72: the GPU-side timeline position. Two read-only queries, safe
					// from this thread. They are what separates the two ways a stall can end:
					//   both numbers frozen -> the queues stopped (cross-queue / driver wedge)
					//   both numbers moving -> the GPU is fine, the render thread is blocked
					//                          in CPU-side code
					// UINT64_MAX means the device is lost / the fence is gone.
					const unsigned long long fence11 = self.d3d11Fence
						? static_cast<unsigned long long>(self.d3d11Fence->GetCompletedValue()) : ~0ull;
					const unsigned long long fence12 = self.d3d12Fence
						? static_cast<unsigned long long>(self.d3d12Fence->GetCompletedValue()) : ~0ull;
"""

C4_NEW = """					// v0.73: the fence values now come from the sampler thread, through
					// atomics. v0.72 read them right here, which put two driver calls in
					// the one thread whose whole job is to keep writing while everything
					// else is stuck - a watchdog that can block is not a watchdog. See
					// StartGpuSampler(): stim=0 means no hang was ever suspected and the
					// field is empty; stim>0 means a hang was under investigation and the
					// numbers are live. UINT64_MAX still means device lost / no fence.
					const unsigned long long fence11 = g_hangFence11.load();
					const unsigned long long fence12 = g_hangFence12.load();
					const unsigned long long stim = g_samplerTicks.load();
					char fenceTxt[48];
					if (fence11 == ~0ull && fence12 == ~0ull)
						std::snprintf(fenceTxt, sizeof(fenceTxt), "-/-");
					else
						std::snprintf(fenceTxt, sizeof(fenceTxt), "%llu/%llu", fence11, fence12);
					// v0.73: wall clock beside the monotonic counter. Lining this file up
					// against the others needed a second log with a matching clock - the
					// absolute time of a freeze was reconstructed by subtraction. One
					// extra field removes that whole class of mistake.
					SYSTEMTIME wtc{};
					::GetLocalTime(&wtc);
"""

C5_OLD = """					std::fprintf(f, "[%lld] frames=%llu silent=%lldms stage=%s focus=%d "
						"fence=%llu/%llu%s\\n",
						nowMs, static_cast<unsigned long long>(frames), silent, self.lastStage(),
						g_lastFocus.load(), fence11, fence12,
						(stalled && (tick % 5) == 0) ? "   <== RENDER THREAD STALLED" : "");
"""

C5_NEW = """					std::fprintf(f, "[%lld] %02d:%02d:%02d.%03d frames=%llu silent=%lldms "
						"stage=%s focus=%d fence=%s stim=%llu%s\\n",
						nowMs, wtc.wHour, wtc.wMinute, wtc.wSecond, wtc.wMilliseconds,
						static_cast<unsigned long long>(frames), silent, self.lastStage(),
						g_lastFocus.load(), fenceTxt, stim,
						(stalled && (tick % 5) == 0) ? "   <== RENDER THREAD STALLED" : "");
"""

C6_OLD = """			if (winFocused != focusWasOn) {
				focusWasOn = winFocused;
"""

C6_NEW = """			if (winFocused != focusWasOn) {
				focusWasOn = winFocused;
				g_bypassReported = false;   // v0.73: one BYPASS report per focus loss
"""

C7_OLD = """			if (swapChain) {
				const HRESULT hrOff = swapChain->Present(0,
					Flags | static_cast<UINT>(DXGI_PRESENT_DO_NOT_WAIT));
				if (hrOff != DXGI_ERROR_WAS_STILL_DRAWING)
					DX::ThrowIfFailed(hrOff);
				// A flip may still have happened, so keep the buffer index honest for the
				// frame that resumes the normal path.
				frameIndex = swapChain->GetCurrentBackBufferIndex();
			}
"""

C7_NEW = """			if (swapChain) {
				const HRESULT hrOff = swapChain->Present(0,
					Flags | static_cast<UINT>(DXGI_PRESENT_DO_NOT_WAIT));
				// v0.73: no throw here. This runs inside the engine's own Present call
				// frame, which has no handler for our exceptions: throwing out of it ends
				// the process on the spot, with no crash log and no flushed log tail.
				// The worst case for this path is a frame that was not shown, so report
				// it once per focus loss and carry on.
				if (!g_bypassReported) {
					g_bypassReported = true;
					SKSE::log::warn("[XRAY] BYPASS present hr={:#x} ({}) flags={:#x}",
						static_cast<unsigned>(hrOff),
						hrOff == DXGI_ERROR_WAS_STILL_DRAWING
							? "buffer still in use, frame not shown" : "no flip pending",
						Flags);
				}
				// A flip may still have happened, so keep the buffer index honest for the
				// frame that resumes the normal path.
				frameIndex = swapChain->GetCurrentBackBufferIndex();
			}
"""

# ---------------------------------------------------------------------------
# DX12SwapChain.h
# ---------------------------------------------------------------------------

H1_OLD = """	class DX12SwapChain
	{
	public:
"""

H1_NEW = """	// v0.73: the watchdog log path, resolved once at plugin load (see
	// InitWatchdogLogPath in DX12SwapChain.cpp) and reused by DllMain during
	// process detach.
	void InitWatchdogLogPath();
	const char* WatchdogLogPath();

	class DX12SwapChain
	{
	public:
"""

H2_OLD = """		std::atomic<bool> watchdogStop{ false };
		void StartWatchdog();
"""

H2_NEW = """		std::atomic<bool> watchdogStop{ false };
		void StartWatchdog();
		// v0.73: samples the GPU timeline from its own thread, so the watchdog never
		// has to enter the driver itself. See the definition for the two readings.
		void StartGpuSampler();
"""

# ---------------------------------------------------------------------------
# main.cpp
# ---------------------------------------------------------------------------

M1_OLD = """#include <Windows.h>
"""

M1_NEW = """#include <Windows.h>

#include <cstdio>
"""

M2_OLD = """	// SKSE::Init 内部已自动初始化 spdlog 日志（CommonLibSSE-NG 4.x）
	SKSE::Init(a_skse);
"""

M2_NEW = """	// SKSE::Init 内部已自动初始化 spdlog 日志（CommonLibSSE-NG 4.x）
	SKSE::Init(a_skse);

	// v0.73: cache the watchdog log path before anything can go wrong, so the
	// exit probe in DllMain is a pure Win32 append with no path resolution.
	FrameGen::InitWatchdogLogPath();
"""

M3_OLD = """	// 3. 消息接口
	SKSE::GetMessagingInterface()->RegisterListener(MessageHandler);

	return true;
}
"""

M3_NEW = """	// 3. 消息接口
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
		if (path && path[0] != '\\0') {
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
					"writes no line like this\\n",
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
"""

EDITS = [
    (CPP, "C1 focus helpers -> atomic bookkeeping + log path", C1_OLD, C1_NEW),
    (CPP, "C2 StartWatchdog -> sampler + cached path", C2_OLD, C2_NEW),
    (CPP, "C3 publish silent for the sampler", C3_OLD, C3_NEW),
    (CPP, "C4 watchdog fence block -> atomics + wall clock", C4_OLD, C4_NEW),
    (CPP, "C5 watchdog fprintf -> wall clock + fence text + stim", C5_OLD, C5_NEW),
    (CPP, "C6 reset the bypass report on the focus edge", C6_OLD, C6_NEW),
    (CPP, "C7 bypass: report, never throw", C7_OLD, C7_NEW),
    (HDR, "H1 declare the log path helpers", H1_OLD, H1_NEW),
    (HDR, "H2 declare StartGpuSampler", H2_OLD, H2_NEW),
    (MAIN, "M1 cstdio for snprintf", M1_OLD, M1_NEW),
    (MAIN, "M2 resolve the log path at load", M2_OLD, M2_NEW),
    (MAIN, "M3 DllMain exit probe", M3_OLD, M3_NEW),
]

# Strings that must survive from earlier versions, so a bad anchor cannot quietly
# drop a previous fix. Checked as "at least", because comments mention them too.
# (text, minimum count)
SURVIVORS = [
    ("FocusAllowsPresenting", 2),            # v0.71 helper + its call site
    ("unfocused bypass", 1),                 # v0.72
    ("DXGI_PRESENT_DO_NOT_WAIT", 1),         # v0.72, the bypass present
    ("g_lastFocus", 3),                      # v0.71 sample + store + read
    ("StartMenuProbeDisabled", 0),           # nonsense control: must be absent
]


def eol_of(text):
    return "CRLF" if "\r\n" in text else "LF"


def match_anchor(text, old, new):
    """EOL-adaptive anchor match.

    Returns (anchor, replacement, hits). The replacement is converted the same way
    as the anchor, so a CRLF file stays CRLF throughout -- inserting a bare-LF
    block into main.cpp (which is CRLF) would leave the file half converted.
    """
    if text.count(old) == 1:
        return old, new, 1
    if "\r\n" not in old:
        swapped = old.replace("\n", "\r\n")
        if text.count(swapped) == 1:
            return swapped, new.replace("\n", "\r\n"), 1
    else:
        swapped = old.replace("\r\n", "\n")
        if text.count(swapped) == 1:
            return swapped, new.replace("\r\n", "\n"), 1
    return None, None, text.count(old) + text.count(swapped)


def brace_delta(text):
    return text.count("{") - text.count("}")


def main():
    apply = "--apply" in sys.argv

    # --- idempotence guard first (checked before any anchor work) ---
    for p in (CPP, HDR, MAIN):
        text = open(p, "r", encoding="utf-8", newline="").read()
        for m in MARKERS:
            if m in text:
                print("REFUSED -- already applied: %r found in %s" % (m, os.path.basename(p)))
                return 1

    contents = {}
    for p in (CPP, HDR, MAIN):
        contents[p] = open(p, "r", encoding="utf-8", newline="").read()

    # --- anchors ---
    plan = []
    bad = 0
    for path, label, old, new in EDITS:
        text = contents[path]
        anchor, repl, n = match_anchor(text, old, new)
        if anchor is None:
            print("REFUSED -- %-56s anchor x%d (want 1)" % (label, n))
            bad += 1
            continue
        if text.count(repl) > 0:
            print("REFUSED -- %-56s replacement already present" % label)
            bad += 1
            continue
        plan.append((path, label, anchor, repl))
        print("ok       %-56s anchor x1" % label)
    if bad:
        print("REFUSED, nothing written")
        return 1

    # --- apply in memory, per file ---
    new_contents = dict(contents)
    for path, label, anchor, new in plan:
        s = new_contents[path]
        assert s.count(anchor) == 1, label
        new_contents[path] = s.replace(anchor, new, 1)

    # --- post-checks ---
    cpp = new_contents[CPP]
    hdr = new_contents[HDR]
    mn = new_contents[MAIN]

    checks = [
        ("no driver call left in the watchdog", cpp.count("self.d3d11Fence"), 0),
        ("no driver call left in the watchdog", cpp.count("self.d3d12Fence"), 0),
        ("sampler owns both queries", cpp.count("GetCompletedValue()"), 2),
        ("bypass no longer throws", cpp.count("DX::ThrowIfFailed(hrOff)"), 0),
        ("bypass reports", cpp.count("BYPASS present hr="), 1),
        ("wall clock in the watchdog line", cpp.count('%02d:%02d:%02d.%03d'), 1),
        ("sampler started (call site)", cpp.count("StartGpuSampler();"), 1),
        ("path helper used", cpp.count("WatchdogLogPath()"), 4),
        ("hdr: sampler declared", hdr.count("void StartGpuSampler();"), 1),
        ("hdr: path helper declared", hdr.count("const char* WatchdogLogPath();"), 1),
        ("main: exit probe", mn.count("DLL_PROCESS_DETACH"), 3),
        ("main: DllMain", mn.count("DllMain"), 2),
        ("main: path resolved at load", mn.count("FrameGen::InitWatchdogLogPath();"), 1),
    ]
    ok = True
    for label, got, want in checks:
        flag = "ok  " if got == want else "FAIL"
        if got != want:
            ok = False
        print("%s     %-44s %d (want %d)" % (flag, label, got, want))

    # survivors (counted across both source files)
    for text, want in SURVIVORS:
        got = cpp.count(text)
        good = got >= want if want > 0 else got == 0
        flag = "ok  " if good else "FAIL"
        if not good:
            ok = False
        print("%s     survivor %-36s %d (want >=%d)" % (flag, text, got, want))

    for p in (CPP, HDR, MAIN):
        d = brace_delta(new_contents[p]) - brace_delta(contents[p])
        flag = "ok  " if d == 0 else "FAIL"
        if d != 0:
            ok = False
        print("%s     brace delta %-32s %d" % (flag, os.path.basename(p), d))

    # ordering assertion: the sample must sit above the guard that reads it
    i_sample = cpp.find("g_lastFocus.store(")
    i_guard = cpp.find("const bool focusBlock = !winFocused;")
    i_bypass = cpp.find("m_stage = \"unfocused bypass\";")
    order_ok = 0 < i_sample < i_bypass and i_guard == -1
    print("%s     ordering sample < bypass, no stale focusBlock" % ("ok  " if order_ok else "FAIL"))
    if not order_ok:
        ok = False

    if not ok:
        print("REFUSED, nothing written")
        return 1

    if not apply:
        print("\nDRY RUN ok -- %d edits in %d files; re-run with --apply" % (len(plan), 3))
        return 0

    # --- write, with a backup ---
    for p in (CPP, HDR, MAIN):
        bak = p + ".bak-" + STAMP
        shutil.copy2(p, bak)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(new_contents[p])
        print("wrote %-28s backup %s" % (os.path.basename(p), os.path.basename(bak)))

    # --- read back from disk and re-verify (never trust the in-memory copy) ---
    print("\nreadback:")
    for p in (CPP, HDR, MAIN):
        got = open(p, "r", encoding="utf-8", newline="").read()
        b = got.encode("utf-8")
        same = got == new_contents[p]
        eol = eol_of(got)
        lone = got.count("\r") - got.count("\r\n")
        print("  %-28s %7d B  md5=%s  roundtrip=%s  eol=%s lone_CR=%d delta=%d" % (
            os.path.basename(p), len(b), hashlib.md5(b).hexdigest()[:12],
            "ok" if same else "MISMATCH", eol, lone,
            brace_delta(got) - brace_delta(contents[p])))
        if not same or lone != 0:
            print("  !! readback mismatch, restore from .bak-" + STAMP)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
