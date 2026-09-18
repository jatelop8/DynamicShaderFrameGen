"""Who wrote a log last?

Reads the tail of every .log/.txt in the SKSE log directory and reports the
last line that carries a clock stamp, so the freeze second can be attributed.
Written as a file rather than a python -c one-liner because the regex kept
coming back empty through the shell quoting.
"""
import os
import re
import time

D = r"C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE"
STAMP = re.compile(r"(\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)")
FULL = re.compile(r"(\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}:\d{2}(?:\.\d+)?)")

rows = []
for n in sorted(os.listdir(D)):
    if not n.lower().endswith((".log", ".txt")):
        continue
    p = os.path.join(D, n)
    try:
        st = os.stat(p)
        with open(p, "rb") as f:
            b = f.read()
    except OSError:
        continue
    tail = b[-8000:].decode("utf-8", "replace")
    last = None
    for line in reversed(tail.splitlines()):
        m = FULL.search(line) or STAMP.search(line)
        if m:
            last = (m.group(1), line.strip()[:100])
            break
    rows.append(
        (
            last[0] if last else "(none)",
            n,
            st.st_size,
            last[1] if last else "",
            time.strftime("%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
        )
    )

rows.sort()
print("%-22s %-36s %10s  %-19s %s" % ("last-stamp", "file", "size", "mtime", "last line"))
for stamp, n, size, line, mt in rows:
    print("%-22s %-36s %10d  %-19s %s" % (stamp, n[:36], size, mt, line))

print()
print("=== files whose mtime lands in 06:48:40..06:48:48 ===")
for stamp, n, size, line, mt in rows:
    hh = mt[6:]
    if "06:48:40" <= hh <= "06:48:48":
        print("  %-36s mtime=%s  last-stamp=%s  %s" % (n[:36], hh, stamp, line))

print()
print("=== any log written AFTER 06:48:48 (would prove the process was alive) ===")
late = [r for r in rows if r[4][6:] > "06:48:48" and r[4].startswith("09-18")]
if not late:
    print("  none")
for r in late:
    print("  %-36s mtime=%s  %s" % (r[1][:36], r[4], r[3]))
