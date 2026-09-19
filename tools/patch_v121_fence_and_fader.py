"""
patch_v121_fence_and_fader.py -- DynamicShaderFrameGen v1.21

Two mechanisms, both argued from the 2026-09-19 22:54 (frozen) and 23:38 (alive)
runs, plus the menu-writer defect that the 23:39 run exposed.

A. THE INTEROP FENCE (src/DX12SwapChain.cpp, src/FrameGen.h, src/FrameGen.cpp)
   v0.75 withdrew the D3D11->D3D12 wait and left a comment saying the change was
   "a hypothesis to be refuted, not a port from a working reference" and that
   doodlum's ENBFrameGeneration keeps the two-way wait. The evidence against the
   withdrawal is now on disk: in the 22:54 run the DXGI present counter ran away
   from the real-frame counter (watchdog frames=643 lastPr=832, i.e. 4x was
   being presented) while the image did not change. The D3D12 queue reads
   swapChainBufferWrapped / colorOutWrapped, which the engine and NR write
   through D3D11, and after v0.75 nothing orders those two. It is now an INI
   setting (InteropFenceWait, default 1 = restore the ordering) so one rebuild
   covers both behaviours and a wedged run is reverted by editing one line.

B. THE FADER MENU IS NOT A MENU (src/Streamline.cpp)
   GameMenuOpenNow() counts IsMenuOpen("Fader Menu") as "a menu is up". The 23:38
   run logged fade=1 for 40+ s while paused=0, ld=0 and Calendar advanced at
   timescale 20 -- the fader is open the entire time the player is in the world.
   Consequence in the 22:54 run: menuBlock engaged on 571 of 572 frames
   (blocked=571 unblocked=1), SetDLSSGOptions/EvaluateDLSSG were skipped, and
   "presented per real frame" stayed at 1 -- the 4x request was never made, not
   rejected. When the guard released at serial 573 the same log reported 4.
   It still has to hold during start-up: the 22:54 MENU PROBE shows that at
   serial 2 every real menu was closed (IsMenuOpen(is)=false/false/false), so
   the fader term is what held the guard then -- and v0.96 removing it outright
   is recorded as "could not enter the game". So it keeps holding while we cannot
   yet be in the world (Loading Menu open, or the first 90 s of uptime).

C. THE MENU WRITER DROPPED A KEY (src/ImguiMenu.cpp)
   LoadConfig reads NRAllowWithFrameGen; SaveSettingsToIni never wrote it. One
   press of Save therefore reverted NR to "mutually exclusive with frame
   generation" on the next launch -- and it rewrote the 14,559 B commented
   template as 517 B. Both new keys are written too, for the same reason.

Dry run by default. --apply writes. --revert undoes.
"""

import hashlib
import os
import sys

ROOT = r'D:/Modding/DynamicShaderFrameGen/src'

FILES = {
    'h':   os.path.join(ROOT, 'FrameGen.h'),
    'cpp': os.path.join(ROOT, 'FrameGen.cpp'),
    'menu': os.path.join(ROOT, 'ImguiMenu.cpp'),
    'sl':  os.path.join(ROOT, 'Streamline.cpp'),
    'sc':  os.path.join(ROOT, 'DX12SwapChain.cpp'),
}


# ---------------------------------------------------------------- file helpers

def eol_of(data: bytes) -> str:
    crlf = data.count(b'\r\n')
    lf = data.count(b'\n')
    return '\r\n' if crlf * 2 >= lf else '\n'


def read(path):
    data = open(path, 'rb').read()
    return data.decode('utf-8'), eol_of(data)


def write(path, text):
    with open(path, 'wb') as f:
        f.write(text.encode('utf-8'))


# ------------------------------------------------------------------ the edits

# --- A1: the two settings ---------------------------------------------------
H_OLD = '\t\tbool nrAllowWithFrameGen = false;'

H_NEW = '''\t\tbool nrAllowWithFrameGen = false;
\t\t// v1.21 -- INTEROP FENCE. v0.75 withdrew the D3D11 -> D3D12 wait
\t\t// ("kD3D12WaitsOnD3D11 = false") on the argument that the fence value
\t\t// had sat at its initial 1 for 50 s. A fence nobody signals looks
\t\t// exactly like that. What the withdrawal costs: the D3D12 queue then
\t\t// reads swapChainBufferWrapped / colorOutWrapped -- which the engine and
\t\t// NR write through D3D11 -- with no ordering at all, while the note at
\t\t// DX12SwapChain's "fence before" comment still says the design relies on
\t\t// that ordering. 1 = restore it (default), 0 = the v0.75 behaviour.
\t\tbool interopFenceWait = true;   // INI InteropFenceWait
\t\t// v1.21 -- THE FADER MENU IS NOT A MENU. IsMenuOpen("Fader Menu") is true
\t\t// the whole time the player is in the world (23:38 run: fade=1 for 40+ s
\t\t// with paused=0, ld=0 and the clock at timescale 20), so counting it as
\t\t// one engages the v0.63 guard on essentially every frame and DLSS-G is
\t\t// never handed a frame. 1 = the fader counts only while we cannot yet be
\t\t// in the world (start-up + loads), 0 = never counts. See GameMenuOpenNow.
\t\tbool menuGuardFader = true;     // INI MenuGuardFader'''

# --- A2: the two readers ----------------------------------------------------
CPP_OLD = '''\t\t\telse if (key == "MenuDisableFrameGen")
\t\t\t\tsettings.menuDisableFrameGen = readBool(line, true);'''

CPP_NEW = CPP_OLD + '''
\t\t\t// v1.21: switchable so one rebuild covers both behaviours of the
\t\t\t// interop fence, and so a run that wedges on it is reverted by editing
\t\t\t// one INI line instead of rebuilding.
\t\t\telse if (key == "InteropFenceWait")
\t\t\t\tsettings.interopFenceWait = readBool(line, true);
\t\t\telse if (key == "MenuGuardFader")
\t\t\t\tsettings.menuGuardFader = readBool(line, true);'''

# --- C1: the key that was read but never written ----------------------------
MENU_OLD1 = '\t\t\t<< "NeuralRenderingEnabled=" << (s.neuralRenderingEnabled ? 1 : 0) << "\\n"'

MENU_NEW1 = MENU_OLD1 + '''
\t\t\t// v1.21: this key is READ by LoadConfig and was never WRITTEN here, so
\t\t\t// one press of Save silently reverted NR to "mutually exclusive with
\t\t\t// frame generation" on the next launch -- and rewrote the 14,559 B
\t\t\t// commented template as 517 B. Every key LoadConfig understands has to
\t\t\t// come out of this function, or the menu is a settings shredder.
\t\t\t<< "NRAllowWithFrameGen=" << (s.nrAllowWithFrameGen ? 1 : 0) << "\\n"'''

# --- C2: the two new keys ---------------------------------------------------
MENU_OLD2 = '\t\t\t<< "MenuDisableFrameGen=" << (s.menuDisableFrameGen ? 1 : 0) << "\\n"'

MENU_NEW2 = MENU_OLD2 + '''
\t\t\t<< "InteropFenceWait=" << (s.interopFenceWait ? 1 : 0) << "\\n"
\t\t\t<< "MenuGuardFader=" << (s.menuGuardFader ? 1 : 0) << "\\n"'''

# --- B: the fader term ------------------------------------------------------
SL_OLD = '''\t\t\treturn ui->IsMenuOpen("Main Menu") || ui->IsMenuOpen("Loading Menu") ||
\t\t\t\tui->IsMenuOpen("Journal Menu") || ui->IsMenuOpen("Pause Menu") ||
\t\t\t\tui->IsMenuOpen("RaceSex Menu") || ui->IsMenuOpen("Fader Menu");'''

SL_NEW = '''\t\t\tif (ui->IsMenuOpen("Main Menu") || ui->IsMenuOpen("Loading Menu") ||
\t\t\t\tui->IsMenuOpen("Journal Menu") || ui->IsMenuOpen("Pause Menu") ||
\t\t\t\tui->IsMenuOpen("RaceSex Menu")) {
\t\t\t\treturn true;
\t\t\t}
\t\t\t// v1.21 -- the fader is NOT evidence of a menu. Evidence: the 23:38 run
\t\t\t// logged fade=1 (IsMenuOpen("Fader Menu")) for 40+ seconds while
\t\t\t// paused=0, ld=0 and Calendar advanced at timescale 20 -- i.e. the
\t\t\t// fader is open for the entire time the player is in the world.
\t\t\t// Counting it as a menu engaged the v0.63 guard on 571 of 572 frames
\t\t\t// of the 22:54 run (blocked=571 unblocked=1), so SetDLSSGOptions and
\t\t\t// EvaluateDLSSG were never called and "presented per real frame" stayed
\t\t\t// at 1: the 4x request was not being rejected by the runtime, it was
\t\t\t// never being made. The moment the guard released (serial 573) the same
\t\t\t// log reported 4.
\t\t\t//
\t\t\t// It must still hold during start-up and during loads. v0.96 removed the
\t\t\t// fader term outright and the game could not be entered, and the 22:54
\t\t\t// MENU PROBE shows why the term exists: at serial 2 every real menu was
\t\t\t// closed (IsMenuOpen(is)=false/false/false), so the fader was the only
\t\t\t// thing holding the guard -- it IS the start-up protection.
\t\t\tif (!Get().settings.menuGuardFader)
\t\t\t\treturn false;
\t\t\tif (ui->IsMenuOpen("Loading Menu"))
\t\t\t\treturn true;
\t\t\tstatic const auto s_faderT0 = std::chrono::steady_clock::now();
\t\t\tconst auto faderUpSec = std::chrono::duration_cast<std::chrono::seconds>(
\t\t\t\tstd::chrono::steady_clock::now() - s_faderT0).count();
\t\t\treturn ui->IsMenuOpen("Fader Menu") && faderUpSec < 90;'''

# --- A3: the fence itself ---------------------------------------------------
SC_OLD = '\t\tstatic constexpr bool kD3D12WaitsOnD3D11 = false;'

SC_NEW = '''\t\t// v1.21: the withdrawal is a SETTING rather than a constant now, so the
\t\t// two behaviours can be compared without a rebuild and a run that wedges
\t\t// on it is reverted by editing one INI line. What the withdrawal costs
\t\t// is written up in FrameGen.h next to InteropFenceWait.
\t\tconst bool kD3D12WaitsOnD3D11 = Get().settings.interopFenceWait;'''


EDITS = [
    ('FrameGen.h   : A1 two settings',            'h',    H_OLD,     H_NEW),
    ('FrameGen.cpp : A2 two readers',             'cpp',  CPP_OLD,   CPP_NEW),
    ('ImguiMenu.cpp: C1 write the missing key',   'menu', MENU_OLD1, MENU_NEW1),
    ('ImguiMenu.cpp: C2 write the new keys',      'menu', MENU_OLD2, MENU_NEW2),
    ('Streamline.cpp: B fader is not a menu',     'sl',   SL_OLD,    SL_NEW),
    ('DX12SwapChain: A3 fence reads the INI',     'sc',   SC_OLD,    SC_NEW),
]

# Strings that must exist exactly once AFTER applying, per file.
POST = {
    'h':    ['bool interopFenceWait = true;', 'bool menuGuardFader = true;', 'v1.21 -- INTEROP FENCE'],
    'cpp':  ['key == "InteropFenceWait"', 'key == "MenuGuardFader"'],
    'menu': ['"NRAllowWithFrameGen="', '"InteropFenceWait="', '"MenuGuardFader="'],
    'sl':   ['the fader is NOT evidence of a menu', 'faderUpSec < 90'],
    'sc':   ['kD3D12WaitsOnD3D11 = Get().settings.interopFenceWait'],
}
# Strings that must be GONE after applying. Note: the anchors of the
# append-style edits (H_OLD, CPP_OLD, MENU_OLD1/2) are meant to SURVIVE, so
# they cannot appear here -- only text that is genuinely consumed can.
POST_GONE = {
    'sl': ['ui->IsMenuOpen("RaceSex Menu") || ui->IsMenuOpen("Fader Menu");'],
}


def main():
    apply = '--apply' in sys.argv
    revert = '--revert' in sys.argv

    print('=== v1.21: interop fence + fader guard + the dropped INI key ===')
    print('mode:', 'REVERT' if revert else ('APPLY' if apply else 'DRY RUN'))
    print()

    loaded = {}
    for k, path in FILES.items():
        if not os.path.exists(path):
            print('REFUSED: missing', path)
            return 1
        text, eol = read(path)
        loaded[k] = [text, eol, path]
        print('%-6s %-22s bytes=%-7d eol=%s' % (k, os.path.basename(path), len(text.encode('utf-8')),
                                                'CRLF' if eol == '\r\n' else 'LF'))
    print()

    marker = 'v1.21'
    already = [k for k, v in loaded.items() if 'faderUpSec' in v[0] or 'interopFenceWait' in v[0]]
    if not revert and already:
        print('REFUSED: already applied (marker present in: %s)' % ','.join(already))
        return 1
    if revert and not already:
        print('REFUSED: nothing to revert (no v1.21 marker found)')
        return 1

    # ---- pass 1: assert every anchor is unique ------------------------------
    plan = []
    for label, key, old, new in EDITS:
        text, eol, path = loaded[key]
        o = old.replace('\n', eol)
        n = new.replace('\n', eol)
        if revert:
            o, n = n, o
        c = text.count(o)
        print('%-42s count(old)=%d' % (label, c))
        if c != 1:
            print()
            print('REFUSED, nothing written: anchor for "%s" matched %d times (must be 1).'
                  % (label, c))
            return 1
        plan.append((label, key, o, n))

    print()
    if not apply and not revert:
        print('DRY RUN ok - all %d anchors unique. Re-run with --apply to write.' % len(plan))
        return 0

    # ---- pass 2: apply, one file at a time ---------------------------------
    for label, key, o, n in plan:
        text, eol, path = loaded[key]
        loaded[key][0] = text.replace(o, n)
        print('applied: %s' % label)

    for key, (text, eol, path) in loaded.items():
        write(path, text)

    print()
    print('=== post-conditions on the RESULT text ===')
    bad = 0
    for key, (text, eol, path) in loaded.items():
        for s in POST.get(key, []):
            c = text.count(s)
            ok = (c == 1) if not revert else (c == 0)
            print('%-6s %-46s count=%d %s' % (key, s[:46], c, 'OK' if ok else 'FAIL'))
            if not ok:
                bad += 1
    for key, items in POST_GONE.items():
        text = loaded[key][0]
        for s in items:
            c = text.count(s)
            ok = (c == 0) if not revert else (c >= 1)
            print('%-6s GONE %-41s count=%d %s' % (key, s[:41], c, 'OK' if ok else 'FAIL'))
            if not ok:
                bad += 1

    print()
    for key, (text, eol, path) in loaded.items():
        data = text.encode('utf-8')
        cr = data.count(b'\r\n')
        lfs = data.count(b'\n')
        stray = lfs - cr
        print('%-6s bytes=%-7d CRLF=%-5d bareLF=%d md5=%s'
              % (key, len(data), cr, stray, hashlib.md5(data).hexdigest()))

    if bad:
        print()
        print('POST-CONDITIONS FAILED (%d) - the files are written, inspect before building.' % bad)
        return 1
    print()
    print('ALL POST-CONDITIONS OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
