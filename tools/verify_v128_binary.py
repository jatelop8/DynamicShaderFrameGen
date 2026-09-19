import pathlib
import hashlib

b = pathlib.Path('build/NINJA/DynamicShaderFrameGen.dll').read_bytes()
d = pathlib.Path('E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.dll').read_bytes()
print('build  md5', hashlib.md5(b).hexdigest(), len(b), 'B')
print('deploy md5', hashlib.md5(d).hexdigest(), len(d), 'B')
print('IDENTICAL' if b == d else 'MISMATCH')
print()

must = [b'shape=[{}] rev={}', b'cpuD=%llums', b'world clock started',
        b'dlssgOk={}', b'came back', b'RETURNED to a state']
for s in must:
    print(('FOUND   ' if s in b else 'MISSING '), s.decode())
print()
gone = [b'switches >= 3u', b'menuBlock=0 frames=', b'-> 5', b'(\xf0\x9f\x98\x80)']
for s in gone:
    print(('STILL THERE' if s in b else 'gone        '), s.decode('utf-8', 'replace'))
print()
print('UI-only strings (must be in the dll, they are compile-time literals):')
for s in [b'KEEP PLAYING, hold W for 10 s', b'enough - you can exit now']:
    print(('FOUND   ' if s in b else 'MISSING '), s.decode())
