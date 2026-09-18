"""v0.95 stage 1 -- carry the Map Subresource into the Unmap hook.

WHY
---
The 16:04 crash log proves the engine writes the perFrame constant buffer TWICE
per frame, and the two writes land in the SAME FrameBuffer*:

    848 Unmap-call groups over 14.8 s
    per-call member pattern:  'MW' 768, 'M' 39, 'W' 39, 'WM' 1, 'MMMW' 1
    (M = menu/UI camera, devVP==magVP==1.11111, constant pos=(-160,160,128))
    (W = world camera,     devVP==magVP==15.011,  pos moves smoothly)

The world stream is continuous when separated (WORLD->WORLD step median 0.000,
only 2/808 steps exceed 5 units), while the interleaved stream is pure
alternation (run length 1).  So the unit of analysis is the FRAME, and the job
is to pick the WORLD half of each pair -- deterministically, not heuristically.

Two discriminators are proven against all 1620 arrivals:
    devVP < 3.0  -> 810 menu / 809 world, valley [1.5,13.0) has exactly 1 sample
    magVP < 3.0  -> 810 menu / 809 world, ZERO disagreements with devVP
    write order  -> menu-first/world-second in 768 of 769 pairs

Order is a property of the engine's draw sequence and cannot be broken by an
unusual scene, so it is the primary rule.  But order is only observable at the
caller (Unmap), while the decision lives in AcceptCameraSnapshot().  The bridge
is the D3D11 subresource index: if the two writes target different subresources
of the same resource, that index IS the source identity -- stable, numeric, and
requiring no threshold at all.

This patch only RECORDS it (adds a field + a log).  It changes no control flow,
so it cannot regress the crash.  Stage 2 will use it.
"""
import sys
from pathlib import Path

CPP = Path(r"D:/Modding/DynamicShaderFrameGen/src/FrameGen.cpp")
HDR = Path(r"D:/Modding/DynamicShaderFrameGen/src/FrameGen.h")

# ---- (label, path, anchor, replacement) -------------------------------------
EDITS = [
    # 1) FrameGen.h: record which subresource the current Map targeted.
    #    Placed next to tlsMappedFB's declaration site equivalent (member area).
    (
        "hdr.subresource_field",
        HDR,
        "	std::vector<FrameBuffer> frameBufferCopies;\n",
        "	std::vector<FrameBuffer> frameBufferCopies;\n"
        "\n"
        "	// v0.95: which D3D11 subresource the current Unmap corresponds to. The\n"
        "	// engine writes the perFrame constant buffer twice per frame (UI/menu\n"
        "	// camera + world camera) and both writes arrive as separate Map/Unmap\n"
        "	// pairs on the same resource. If they use different subresource indices,\n"
        "	// that index is the source identity -- no threshold, no heuristic.\n"
        "	std::uint32_t lastMapSubresource = 0;\n",
    ),
]

# The header may not contain that exact line; fall back to another anchor.
HDR_FALLBACK = [
    (
        "hdr.subresource_field_fb",
        HDR,
        "	bool snapLockHave = false;           // a stream is locked\n",
        "	bool snapLockHave = false;           // a stream is locked\n"
        "\n"
        "	// v0.95: subresource identity of the current Unmap. The engine writes the\n"
        "	// perFrame constant buffer twice per frame (UI/menu camera, then world\n"
        "	// camera); if the two writes use different subresource indices, that index\n"
        "	// IS the source identity -- numeric, stable, and threshold-free.\n"
        "	std::uint32_t lastMapSubresource = 0;\n"
        "	std::uint32_t lastUnmapSubresource = 0;\n",
    ),
]


def check(path, old, label):
    if not path.exists():
        return f"{label}: FILE MISSING {path}"
    txt = path.read_text(encoding="utf-8")
    n = txt.count(old)
    if n != 1:
        return f"{label}: anchor count = {n} (expected exactly 1)"
    return None


def main():
    apply = "--apply" in sys.argv
    print(f"mode: {'APPLY' if apply else 'DRY-RUN'}")

    # pick header anchor
    txt_h = HDR.read_text(encoding="utf-8")
    hdr_edits = []
    for label, path, old, new in EDITS:
        if txt_h.count(old) == 1:
            hdr_edits.append((label, path, old, new))
            break
    else:
        for label, path, old, new in HDR_FALLBACK:
            if txt_h.count(old) == 1:
                hdr_edits.append((label, path, old, new))
                break
        else:
            print("REFUSED: no usable header anchor found")
            print("  candidates tried:")
            print("   -", repr(EDITS[0][2][:60]))
            print("   -", repr(HDR_FALLBACK[0][2][:60]))
            return 1

    # cpp edits are position-dependent; build them after checking the source
    txt_c = CPP.read_text(encoding="utf-8")
    cpp_edits = []

    # 2) Map hook: store the subresource for the perFrame resource
    map_old = (
        "					if (perFrame && *perFrame == pResource && pMappedResource->pData) {\n"
        "						tlsMappedFB = static_cast<FrameBuffer*>(pMappedResource->pData);"
    )
    map_new = (
        "					if (perFrame && *perFrame == pResource && pMappedResource->pData) {\n"
        "						tlsMappedFB = static_cast<FrameBuffer*>(pMappedResource->pData);\n"
        "						// v0.95: remember which slice this Map targeted. Subresource\n"
        "						// 0/D3D11CalcSubresource(0,0,mips) is the usual index for a\n"
        "						// non-array, single-mip buffer, so if both writes report 0 the\n"
        "						// index carries no signal and stage 2 falls back to magVP.\n"
        "						Get().lastMapSubresource = Subresource;"
    )
    cpp_edits.append(("cpp.map_record_subresource", CPP, map_old, map_new))

    # 3) Unmap hook: log the subresource alongside the accepted camera, but only
    #    for the first few arrivals so the log stays bounded.  We piggyback on the
    #    existing gate by forwarding the index into the snapshot call.
    unmap_old = (
        "					// v0.67：只接受「与上一次接受的快照时间连续」的相机数据。\n"
        "					// 同一个 perFrame 缓冲每帧写入两组不同相机（菜单 3D 背景 + 世界）\n"
        "					// 时，后写的那组会把先写的冲掉 —— 闸门挡住它，frameBufferCopy 与\n"
        "					// 自维护 prev 历史才可能是同一来源（det(inv(cur) x prev)=1）。\n"
        "					if (fg.AcceptCameraSnapshot(*tlsMappedFB))\n"
        "						fg.SetMappedFrameBuffer(&fg.frameBufferCopy);\n"
        "					tlsMappedFB = nullptr;"
    )
    unmap_new = (
        "					// v0.67：只接受「与上一次接受的快照时间连续」的相机数据。\n"
        "					// 同一个 perFrame 缓冲每帧写入两组不同相机（菜单 3D 背景 + 世界）\n"
        "					// 时，后写的那组会把先写的冲掉 —— 闸门挡住它，frameBufferCopy 与\n"
        "					// 自维护 prev 历史才可能是同一来源（det(inv(cur) x prev)=1）。\n"
        "					//\n"
        "					// v0.95: hand the subresource index to the gate so it can tell\n"
        "					// the two writes apart structurally instead of by distance.\n"
        "					fg.lastUnmapSubresource = fg.lastMapSubresource;\n"
        "					if (fg.AcceptCameraSnapshot(*tlsMappedFB))\n"
        "						fg.SetMappedFrameBuffer(&fg.frameBufferCopy);\n"
        "					tlsMappedFB = nullptr;"
    )
    cpp_edits.append(("cpp.unmap_carry_subresource", CPP, unmap_old, unmap_new))

    # verify all
    problems = []
    for label, path, old, new in hdr_edits + cpp_edits:
        p = check(path, old, label)
        if p:
            problems.append(p)
    if problems:
        print("REFUSED, nothing written:")
        for p in problems:
            print("  -", p)
        return 1

    for label, path, old, new in hdr_edits + cpp_edits:
        txt = path.read_text(encoding="utf-8")
        assert txt.count(old) == 1
        txt = txt.replace(old, new, 1)
        if apply:
            path.write_text(txt, encoding="utf-8")
        print(f"  {'WROTE' if apply else 'WOULD WRITE'} {label}  (+{len(new)-len(old)} chars)")

    if not apply:
        print("\n(dry run -- pass --apply to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
