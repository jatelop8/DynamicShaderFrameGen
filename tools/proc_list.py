import ctypes
import ctypes.wintypes as wt

TH32CS_SNAPPROCESS = 0x2
k = ctypes.WinDLL('kernel32', use_last_error=True)


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_char * 260)]


k.CreateToolhelp32Snapshot.restype = wt.HANDLE
snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
e = PROCESSENTRY32()
e.dwSize = ctypes.sizeof(PROCESSENTRY32)

PAT = ('cl.exe', 'ninja.exe', 'mspdbsrv.exe', 'link.exe', 'vctip.exe', 'msbuild.exe',
       'skyrimse.exe', 'skse64_loader.exe', 'modorganizer.exe', 'explorer.exe')

out = []
if k.Process32First(snap, ctypes.byref(e)):
    while True:
        nm = e.szExeFile.decode('latin-1')
        if nm.lower() in PAT:
            out.append((nm, e.th32ProcessID, e.th32ParentProcessID))
        if not k.Process32Next(snap, ctypes.byref(e)):
            break
k.CloseHandle(snap)

for nm, pid, ppid in sorted(out):
    print(f"{nm:24s} pid={pid:<8d} ppid={ppid}")
print(f"total matched={len(out)}")
