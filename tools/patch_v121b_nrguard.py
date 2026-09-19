"""
patch_v121b_nrguard.py -- v1.21 follow-up: NRAllowWithFrameGen is ignored on FSR3.

DX12SwapChain.cpp:

    const bool fgGeneratingNow =
        dlssgMode && fg.settings.frameGeneration && fg.fgActive.load();

nrSuppressed can only be non-zero when dlssgMode is true, so with Provider=0
(FSR3) nrAllowWithFrameGen is never consulted and DLSS5 NR stacks with FSR3 frame
generation no matter what the INI says. That is exactly the shape of the 23:38
run, whose INI had NRAllowWithFrameGen=0:

    [W] [DLSSNR] D3D12 command contexts saturated; applying CPU backpressure
    [FrameGen] DLSSNR: ... frames=179 -> 359 -> 539 -> ...  (a full-resolution
               4K NR evaluation on every real frame)
    real fps 27.7-45.7 (v0.69 recorded 53 -> 27 the instant FG engaged)

and the run's own complaint was flicker, which is the documented consequence of
two temporal processors writing history for the same frame. The INI carried the
exhaustive comment "Start at 0 if the picture flickers" for that key, and it was
being ignored.

This cannot change the DLSSG path: on that path dlssgMode is already true, so
dropping the term from the conjunction leaves the expression identical there. The
next run is Provider=1, so this edit cannot confound it by construction.

Dry run by default. --apply writes.
"""

import hashlib
import os
import sys

SC = r'D:/Modding/DynamicShaderFrameGen/src/DX12SwapChain.cpp'

OLD = '''\t\tconst bool fgGeneratingNow =
\t\t\tdlssgMode && fg.settings.frameGeneration && fg.fgActive.load();'''

NEW = '''\t\t// v1.21: the dlssgMode term is gone. With it, nrSuppressed could only ever
\t\t// be true on the DLSSG path, so on Provider=0 (FSR3) NRAllowWithFrameGen=0
\t\t// was silently ignored and DLSS5 NR stacked with FSR3 frame generation
\t\t// regardless -- the 23:38 run's INI asked for no stacking, the log shows
\t\t// "D3D12 command contexts saturated" plus a full-resolution NR pass on
\t\t// every real frame, and the complaint was flicker, which is what two
\t\t// temporal processors writing history for the same frame produce.
\t\t// On the DLSSG path dlssgMode is already true, so removing the term leaves
\t\t// this expression identical there.
\t\tconst bool fgGeneratingNow =
\t\t\tfg.settings.frameGeneration && fg.fgActive.load();'''

POST = ['v1.21: the dlssgMode term is gone',
        'fg.settings.frameGeneration && fg.fgActive.load();']
POST_GONE = ['dlssgMode && fg.settings.frameGeneration && fg.fgActive.load();']


def main():
    apply = '--apply' in sys.argv
    data = open(SC, 'rb').read()
    eol = '\r\n' if data.count(b'\r\n') * 2 >= data.count(b'\n') else '\n'
    text = data.decode('utf-8')

    print('=== v1.21b: NR guard on the FSR3 path ===')
    print('file :', SC)
    print('mode :', 'APPLY' if apply else 'DRY RUN')
    print('size :', len(data), ' eol:', 'CRLF' if eol == '\r\n' else 'LF')
    print('md5  :', hashlib.md5(data).hexdigest())
    print()

    if 'v1.21: the dlssgMode term is gone' in text:
        print('REFUSED: already applied (marker present)')
        return 1

    o = OLD.replace('\n', eol)
    n = NEW.replace('\n', eol)
    c = text.count(o)
    print('anchor count(old) = %d' % c)
    if c != 1:
        print()
        print('REFUSED, nothing written: anchor matched %d times (must be 1).' % c)
        return 1

    print()
    if not apply:
        print('DRY RUN ok - anchor unique. Re-run with --apply to write.')
        return 0

    text = text.replace(o, n)
    out = text.encode('utf-8')
    with open(SC, 'wb') as f:
        f.write(out)
    print('applied: NR guard')

    print()
    print('=== post-conditions on the RESULT text ===')
    bad = 0
    for s in POST:
        c = text.count(s)
        print('%-46s count=%d %s' % (s[:46], c, 'OK' if c == 1 else 'FAIL'))
        if c != 1:
            bad += 1
    for s in POST_GONE:
        c = text.count(s)
        print('%-46s count=%d %s' % ('GONE ' + s[:41], c, 'OK' if c == 0 else 'FAIL'))
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
