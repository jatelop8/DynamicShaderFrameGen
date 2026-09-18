# -*- coding: utf-8 -*-
"""
v1.01 - let DLSS5 Neural Rendering run IN SERIES with frame generation.

WHY
The two features the user wants -- "dlss5 用上" and "多倍帧生成成功" -- cannot
both be active today, because v0.69 hard-wired them as mutually exclusive:

    if (fg.settings.neuralRenderingEnabled && fgGeneratingNow) {
        ... "DLSSNR suppressed: frame generation is active ..."
    }
    if (fg.settings.neuralRenderingEnabled && !fgGeneratingNow) {
        ... Apply(...)
    }

v0.42 chained them deliberately and left the escape hatch in ImguiMenu.cpp:373
("若叠加闪烁再回退互斥"). v0.69 read the 2026-09-17 23:07 run as proof that
stacking flickers. But that run had TWO other faults active at the same time:

  * `real fps 53 -> 27 the instant FG engaged`  -- the v0.63 pacing defect still
    present (the Reflex cap was dividing by the multiplier twice), fixed later;
  * `[DLSSNR] frames 179->359->539->719` plus "D3D12 command contexts saturated"
    -- NR was running at FULL resolution (NRRenderScale=1.00) on every frame,
    so it simply could not keep up.

So the v0.69 conclusion ("stacking is a flicker source") is not established by
that run: it is confounded with pacing and with NR cost.

THE ORDER MATTERS, AND IT IS ALREADY CORRECT
Present() already does the right thing for chaining:

    1096  CopyResource(colorOut <- swapChainBuffer)   (ENB + upscale result)
    1113  [mutual exclusion, to be removed]
    1162  NeuralRendering::Apply(..., nrColor, ...)   NR writes the frame back
    1215  fence sync (D3D11 -> D3D12)
    1327  EvaluateDLSSG(..., swapChainBufferWrapped->resource, ...)

and with dlssgMode on, `nrColor` IS `swapChainBufferWrapped->resource11`
(line 1129) -- the very resource EvaluateDLSSG consumes. NR therefore rewrites
the exact texture DLSS-G then reads, and the fence between them orders the two.
NR in series *before* DLSSG is structurally sound; only the gate blocks it.

WHAT THIS PATCH DOES
  - keeps the gate, but as a SETTING: NRAllowWithFrameGen (default 0 = today's
    mutually-exclusive behaviour), so the change is opt-in and one INI line
    reverts it without touching code;
  - when enabled, NR runs on the frame DLSS-G is about to interpolate;
  - when disabled, the previous behaviour is byte-for-byte unchanged;
  - logs which mode is in force, once, so a log can be read unambiguously.

NOT DONE HERE (deliberately): no change to NRRenderScale. Full-resolution NR on
every frame is a large cost and is the most likely cause of the 27 fps in the
2026-09-17 run. That is a tuning decision, not a correctness one, and the INI
already carries the knob.

Run with --apply to write; without it, dry-run only.
"""
import io
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWAP = os.path.join(ROOT, "src", "DX12SwapChain.cpp")
HDR = os.path.join(ROOT, "src", "FrameGen.h")
CPP = os.path.join(ROOT, "src", "FrameGen.cpp")
INI = os.path.join(ROOT, "SKSE", "Plugins", "DynamicShaderFrameGen.ini")
APPLY = "--apply" in sys.argv

OLD_GATE = """		if (fg.settings.neuralRenderingEnabled && fgGeneratingNow) {
			static bool nrStackLogged = false;
			if (!nrStackLogged) {
				nrStackLogged = true;
				SKSE::log::warn("[FrameGen] DLSSNR suppressed: frame generation is active - "
					"NR and DLSS-G are two temporal processors and stacking them is a "
					"direct flicker source (v0.42 note: revert to mutual exclusion if "
					"it flickers). Toggle key disables FG and NR resumes.");
			}
		}"""

NEW_GATE = """		// ---- v1.01: NR may run IN SERIES with frame generation ----
		// The mutual exclusion above is now a SETTING (NRAllowWithFrameGen,
		// default 0 = unchanged). Rationale and evidence: see the header of
		// tools/patch_v101_nrserial_1.py.
		//
		// The v0.69 conclusion ("stacking is a flicker source") came from a run
		// that also had the v0.63 pacing defect (real fps 53->27 on FG engage)
		// and full-resolution NR (NRRenderScale=1.00, "D3D12 command contexts
		// saturated") live at the same time, so it is confounded and does not by
		// itself justify keeping the feature pair impossible.
		//
		// The ORDER is already right for chaining: with dlssgMode on, nrColor is
		// swapChainBufferWrapped->resource11 (line below), which is exactly the
		// resource EvaluateDLSSG consumes, and the fence at "d3d11 Signal(fence)"
		// orders NR's write before DLSS-G's read. NR runs first, DLSS-G
		// interpolates the neural-rendered frame.
		const bool nrSuppressed = fgGeneratingNow && !fg.settings.nrAllowWithFrameGen;
		if (fg.settings.neuralRenderingEnabled && nrSuppressed) {
			static bool nrStackLogged = false;
			if (!nrStackLogged) {
				nrStackLogged = true;
				SKSE::log::warn("[FrameGen] DLSSNR suppressed: frame generation is active - "
					"NR and DLSS-G are two temporal processors and stacking them is a "
					"direct flicker source (v0.42 note: revert to mutual exclusion if "
					"it flickers). Set NRAllowWithFrameGen=1 to chain them instead "
					"(v1.01), or press the toggle key to disable FG and NR resumes.");
			}
		} else if (fg.settings.neuralRenderingEnabled && fgGeneratingNow) {
			static bool nrChainLogged = false;
			if (!nrChainLogged) {
				nrChainLogged = true;
				SKSE::log::info("[FrameGen] DLSSNR CHAINED with frame generation (v1.01, "
					"NRAllowWithFrameGen=1): NR runs first on the real frame, DLSS-G then "
					"interpolates the neural-rendered result.");
			}
		}"""

OLD_APPLY_GATE = """		if (fg.settings.neuralRenderingEnabled && !fgGeneratingNow) {"""
NEW_APPLY_GATE = """		if (fg.settings.neuralRenderingEnabled && !nrSuppressed) {"""

OLD_MEMBER = """		bool neuralRenderingEnabled = false;  // INI NeuralRenderingEnabled"""
NEW_MEMBER = """		bool neuralRenderingEnabled = false;  // INI NeuralRenderingEnabled
		// v1.01: allow DLSS5 NR to run in series with frame generation.
		// 0 = mutually exclusive (v0.69 behaviour, default).
		// 1 = NR runs first on the real frame, then DLSS-G interpolates it.
		// Read from INI (NRAllowWithFrameGen) and exposed in the GUI.
		bool nrAllowWithFrameGen = false;"""

OLD_PARSE = """			else if (key == "NeuralRenderingEnabled")
				settings.neuralRenderingEnabled = readBool(line, false);"""
NEW_PARSE = """			else if (key == "NeuralRenderingEnabled")
				settings.neuralRenderingEnabled = readBool(line, false);
			// v1.01：允许 DLSS5 NR 与帧生成串联（默认 0 = 保持 v0.69 的互斥）
			else if (key == "NRAllowWithFrameGen")
				settings.nrAllowWithFrameGen = readBool(line, false);"""


def eol_of(text, anchor):
    i = text.index(anchor)
    j = text.find("\n", i)
    if j < 0:
        return "\n"
    return "\r\n" if text[j - 1] == "\r" else "\n"


def conv(s, nl):
    if "\r\n" in s:
        return s
    return s.replace("\n", "\r\n") if nl == "\r\n" else s


def main():
    files = {}
    for p in (SWAP, HDR, CPP):
        with io.open(p, "r", encoding="utf-8", newline="") as f:
            files[p] = f.read()

    for p, t in files.items():
        if "NRAllowWithFrameGen" in t:
            print("REFUSED: marker already present in %s - patch has run" % os.path.basename(p))
            return 1

    edits = [
        (SWAP, "swap/gate", OLD_GATE, NEW_GATE),
        (SWAP, "swap/apply-gate", OLD_APPLY_GATE, NEW_APPLY_GATE),
        (HDR, "hdr/member", OLD_MEMBER, NEW_MEMBER),
        (CPP, "cpp/parse", OLD_PARSE, NEW_PARSE),
    ]

    for path, label, old, new in edits:
        t = files[path]
        nl = eol_of(t, old.split("\n")[0])
        old_c, new_c = conv(old, nl), conv(new, nl)
        n = t.count(old_c)
        if n != 1:
            print("REFUSED: anchor '%s' occurs %d times (must be exactly 1)" % (label, n))
            return 1
        files[path] = t.replace(old_c, new_c)
        print("  ok: %s" % label)

    swap, hdr, cpp = files[SWAP], files[HDR], files[CPP]
    n_swap = swap.replace("\r\n", "\n")
    checks = [
        ("gate now conditional", "const bool nrSuppressed = fgGeneratingNow && !fg.settings.nrAllowWithFrameGen;" in n_swap),
        ("apply gate uses nrSuppressed", "if (fg.settings.neuralRenderingEnabled && !nrSuppressed) {" in n_swap),
        ("chain log present", "DLSSNR CHAINED with frame generation (v1.01" in n_swap),
        ("old unconditional suppression gone",
         'if (fg.settings.neuralRenderingEnabled && fgGeneratingNow) {\n\t\t\tstatic bool nrStackLogged' not in n_swap),
        ("hdr: member present", "bool nrAllowWithFrameGen = false;" in hdr),
        ("cpp: parsed from INI", 'key == "NRAllowWithFrameGen"' in cpp),
        ("swap: brace balance", swap.count("{") - swap.count("}") == open(SWAP, "rb").read().decode("utf-8").count("{") - open(SWAP, "rb").read().decode("utf-8").count("}")),
        ("cpp: brace balance", cpp.count("{") - cpp.count("}") == open(CPP, "rb").read().decode("utf-8").count("{") - open(CPP, "rb").read().decode("utf-8").count("}")),
    ]
    ok = True
    for label, cond in checks:
        print("  %-38s %s" % (label, "PASS" if cond else "FAIL"))
        ok = ok and cond
    if not ok:
        print("REFUSED: post-conditions failed, nothing written")
        return 1

    if not APPLY:
        print("\nDRY RUN - re-run with --apply")
        return 0

    for p in (SWAP, HDR, CPP):
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(files[p])
    print("\nAPPLIED: DLSS5 NR can run in series with frame generation (opt-in)")

    # INI: document the new key next to NeuralRenderingEnabled
    try:
        with io.open(INI, "r", encoding="utf-8", newline="") as f:
            ini = f.read()
        if "NRAllowWithFrameGen" not in ini:
            anchor = "NeuralRenderingEnabled=1"
            add = ("NeuralRenderingEnabled=1\r\n"
                   "\r\n"
                   "; v1.01 - run DLSS5 Neural Rendering IN SERIES with frame generation.\r\n"
                   "; 0 = mutually exclusive (default; v0.69 behaviour: NR is suppressed while\r\n"
                   ";     frame generation is active).\r\n"
                   "; 1 = NR runs first on the real frame and DLSS-G then interpolates the\r\n"
                   ";     neural-rendered result. The order is already correct in Present()\r\n"
                   ";     (NR writes swapChainBufferWrapped, which is what EvaluateDLSSG reads,\r\n"
                   ";     with the D3D11->D3D12 fence between them).\r\n"
                   "; Start at 0 if the picture flickers; raise NRRenderScale cost awareness\r\n"
                   "; first - full-resolution NR on every frame is the expensive part.\r\n"
                   "NRAllowWithFrameGen=0") if "\r\n" in ini else (
                   "NeuralRenderingEnabled=1\n\n"
                   "; v1.01 - run DLSS5 Neural Rendering IN SERIES with frame generation.\n"
                   "; 0 = mutually exclusive (default; v0.69 behaviour: NR is suppressed while\n"
                   ";     frame generation is active).\n"
                   "; 1 = NR runs first on the real frame and DLSS-G then interpolates the\n"
                   ";     neural-rendered result. The order is already correct in Present()\n"
                   ";     (NR writes swapChainBufferWrapped, which is what EvaluateDLSSG reads,\n"
                   ";     with the D3D11->D3D12 fence between them).\n"
                   "NRAllowWithFrameGen=0")
            if ini.count(anchor) == 1:
                with io.open(INI, "w", encoding="utf-8", newline="") as f:
                    f.write(ini.replace(anchor, add))
                print("INI: documented NRAllowWithFrameGen=0")
            else:
                print("INI: WARNING anchor count %d, not modified" % ini.count(anchor))
    except Exception as e:
        print("INI: skipped (%s)" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
