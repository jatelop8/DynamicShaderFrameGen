"""
patch_v121_ini.py -- v1.21 test configuration for DynamicShaderFrameGen.

Edits the INI TEMPLATE in the source tree (SKSE/Plugins/DynamicShaderFrameGen.ini),
which is what CMakeLists' POST_BUILD step copies into the mod folder. Editing the
deployed copy alone is what the 23:39 run proved to be fragile: the in-game menu
wrote it back as 517 bytes with NRAllowWithFrameGen gone, and any rebuild puts the
template back. The template is the durable place.

Four edits:
  1. a header block naming what this run is for
  2. MenuGuardFader=1   (new key, documented)
  3. InteropFenceWait=1 (new key, documented)
  4. NRAllowWithFrameGen 1 -> 0 for this run, so the 4x test carries one variable
     fewer. NR is not the freeze (the 23:22 run had it suppressed and froze, and
     the 23:38 run had it chained and was alive), but full-resolution NR costs
     about half the render rate (v0.69 note: 53 -> 27 fps) and it is a documented
     flicker source when stacked, so it does not belong in the first 4x run.

Dry run by default. --apply writes.
"""

import hashlib
import os
import sys

INI = r'D:/Modding/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini'

HEADER_OLD = '''[FrameGeneration]
; DynamicShaderFrameGen - FrameGen (frame interpolation) for Skyrim (works with ENB)'''

HEADER_NEW = '''[FrameGeneration]
; DynamicShaderFrameGen - FrameGen (frame interpolation) for Skyrim (works with ENB)
; ---------------------------------------------------------------------------
; v1.21 - WHAT THIS FILE IS SET UP TO TEST
;
; Two mechanisms changed, and this configuration isolates them from everything
; the previous runs already ruled out. From the 2026-09-19 logs:
;   22:54  Provider=1, 4x requested   picture completely fixed, game unplayable
;   23:22  Provider=1, NR suppressed  same freeze (so NR is not the cause)
;   23:38  Provider=0 (FSR3)          picture alive, 2x only, flicker
; => the freeze belongs to the DLSSG path, not to frame generation as such.
;
; What was actually wrong in the 22:54 run, read off its own log:
;   [MFG] blocked=571 unblocked=1        the v0.63 menu guard engaged on 571 of
;                                        572 frames, so SetDLSSGOptions and
;                                        EvaluateDLSSG were never called
;   DLSSG presented per real frame = 1   no interpolation was happening at all
;   [XRAY] MENU EDGE open=1 serial=2     and the only menu open at serial 2 was
;                                        the FADER MENU (the MENU PROBE printed
;                                        IsMenuOpen(is)=false/false/false)
; The 4x request was not being rejected by the runtime - it was never being made.
; MenuGuardFader=1 below is what stops the fader from doing that in the world.
;
; The second mechanism is the D3D11 -> D3D12 interop fence that v0.75 withdrew
; (InteropFenceWait below). dlssg 4x presented while the image did not change, and
; the D3D12 queue reads swapChainBufferWrapped, which the engine writes through
; D3D11, with nothing ordering the two. That is a stale-colour-buffer mechanism.
;
; THIS RUN, in one line: DLSSG + 4x + NR out of the way + both mechanisms on.
; ---------------------------------------------------------------------------'''

MENU_OLD = 'MenuDisableFrameGen=1'

MENU_NEW = '''MenuDisableFrameGen=1

; ---------------------------------------------------------------------------
; v1.21 - which menus count as menus. Unit: boolean.
;
; 1 = the Fader Menu counts as a menu only while we cannot yet be in the world
;     (the Loading Menu is open, or we are in the first 90 s of the session).
;     This is the default and it is what the two runs above call for.
; 0 = the Fader Menu never counts.
;
; Why this key exists at all. GameMenuOpenNow() counted IsMenuOpen("Fader Menu")
; as "a menu is up", and the 23:38 log shows the fader is up for the ENTIRE time
; the player is in the world: fade=1 for 40+ consecutive seconds while paused=0,
; ld=0, and Calendar advanced 0.0057 game-hours per real second (timescale 20,
; i.e. the game was simulating normally). With MenuDisableFrameGen=1 that made
; the menu guard permanent, and the 22:54 run's own counter says so:
; blocked=571 unblocked=1.
;
; It still has to hold during start-up. v0.96 removed the fader term outright and
; the game could not be entered, and the 22:54 MENU PROBE explains why: at serial
; 2 every real menu was closed, so the fader was the only thing holding the guard
; during the frames where the swapchain and the pacer are still coming up.
; ---------------------------------------------------------------------------
MenuGuardFader=1'''

FENCE_OLD = '''; Streamline log level: 0=Off 1=Default 2=Verbose (troubleshooting; keep 0 normally)
StreamlineLogLevel=0'''

FENCE_NEW = '''; ---------------------------------------------------------------------------
; v1.21 - the D3D11 -> D3D12 interop fence. Unit: boolean.
;
; 1 = the render thread signals the shared fence on the D3D11 side and the D3D12
;     queue waits on it before this frame's D3D12 work (default).
; 0 = the v0.75 behaviour: that wait is withdrawn.
;
; v0.75 withdrew it on the argument that the fence had "held its initial value 1
; for 50 s". A fence nobody signals looks exactly like that. What the withdrawal
; costs: the D3D12 queue reads swapChainBufferWrapped / colorOutWrapped - both
; written by the engine and by DLSS5 NR through D3D11 - with no ordering at all,
; while the comment at the "fence before" site still says the design relies on
; that ordering. The reference implementation this project ports from
; (doodlum/ENBFrameGeneration) keeps the two-way wait, and the v0.75 note itself
; says the change was "a hypothesis to be refuted, not a port from a working
; reference".
;
; The symptom that put it back on the table: the 22:54 watchdog shows the DXGI
; present counter running away from the real-frame counter (frames=643
; lastPr=832 - 4x really was being presented) while the image did not change.
;
; It is a key rather than a constant so that both behaviours can be compared
; without a rebuild, and so that a run which wedges on the wait is reverted by
; editing this one line. If the picture freezes again, set this to 0 first: that
; tells us the withdrawal was load-bearing, which is itself a result.
; ---------------------------------------------------------------------------
InteropFenceWait=1

; Streamline log level: 0=Off 1=Default 2=Verbose (troubleshooting; keep 0 normally)
StreamlineLogLevel=0'''

NR_OLD = '''; first - full-resolution NR on every frame is the expensive part.
NRAllowWithFrameGen=1'''

NR_NEW = '''; first - full-resolution NR on every frame is the expensive part.
; v1.21: set to 0 for the 4x run. NR is not what froze the picture (23:22 ran
; with NR suppressed and froze anyway) but it costs about half the render rate
; (v0.69: 53 -> 27 fps with full-resolution NR live) and two temporal processors
; writing history for the same frame is a documented flicker source. Once 4x is
; stable, set this back to 1 to get DLSS5 and multi-frame generation together.
NRAllowWithFrameGen=0'''

EDITS = [
    ('header block',              HEADER_OLD, HEADER_NEW),
    ('MenuGuardFader',            MENU_OLD,   MENU_NEW),
    ('InteropFenceWait',          FENCE_OLD,  FENCE_NEW),
    ('NRAllowWithFrameGen 1 -> 0', NR_OLD,    NR_NEW),
]

# Post-conditions pin the VALUE LINES, not the prose. An earlier revision of this
# script checked for the bare string "InteropFenceWait=1" and passed on a header
# sentence that merely mentioned it, while the assignment line itself had never
# been inserted -- the file documented a key it did not set. Anchoring on the
# surrounding newlines is what makes prose unable to satisfy the check.
POST = [('MenuGuardFader value line', '\nMenuGuardFader=1\n'),
        ('InteropFenceWait value line', '\nInteropFenceWait=1\n'),
        ('NRAllowWithFrameGen value line', '\nNRAllowWithFrameGen=0\n'),
        ('header marker', 'v1.21 - WHAT THIS FILE IS SET UP TO TEST')]
POST_GONE = ['\nNRAllowWithFrameGen=1\n']


def main():
    apply = '--apply' in sys.argv
    data = open(INI, 'rb').read()
    eol = '\r\n' if data.count(b'\r\n') * 2 >= data.count(b'\n') else '\n'
    text = data.decode('utf-8')

    print('=== v1.21 INI ===')
    print('file :', INI)
    print('mode :', 'APPLY' if apply else 'DRY RUN')
    print('size :', len(data), ' eol:', 'CRLF' if eol == '\r\n' else 'LF')
    print('md5  :', hashlib.md5(data).hexdigest())
    print()

    if 'v1.21 - WHAT THIS FILE IS SET UP TO TEST' in text:
        print('REFUSED: already applied (marker present)')
        return 1

    plan = []
    for label, old, new in EDITS:
        o = old.replace('\n', eol)
        n = new.replace('\n', eol)
        c = text.count(o)
        print('%-28s count(old)=%d' % (label, c))
        if c != 1:
            print()
            print('REFUSED, nothing written: anchor "%s" matched %d times (must be 1).'
                  % (label, c))
            return 1
        plan.append((label, o, n))

    print()
    if not apply:
        print('DRY RUN ok - all %d anchors unique. Re-run with --apply to write.' % len(plan))
        return 0

    for label, o, n in plan:
        text = text.replace(o, n)
        print('applied:', label)

    out = text.encode('utf-8')
    with open(INI, 'wb') as f:
        f.write(out)

    print()
    print('=== post-conditions on the RESULT text ===')
    bad = 0
    for label, s in POST:
        c = text.count(s.replace('\n', eol))
        print('%-34s count=%d %s' % (label, c, 'OK' if c == 1 else 'FAIL'))
        if c != 1:
            bad += 1
    for s in POST_GONE:
        c = text.count(s.replace('\n', eol))
        print('%-34s count=%d %s' % ('GONE ' + s.strip(), c, 'OK' if c == 0 else 'FAIL'))
        if c != 0:
            bad += 1

    cr = out.count(b'\r\n')
    lf = out.count(b'\n')
    print()
    print('bytes=%d CRLF=%d bareLF=%d md5=%s' % (len(out), cr, lf - cr, hashlib.md5(out).hexdigest()))
    if bad:
        print('POST-CONDITIONS FAILED (%d)' % bad)
        return 1
    print('ALL POST-CONDITIONS OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
