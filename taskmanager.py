import ctypes
from ctypes import wintypes

# --- Win32 API Constants ---
TH32CS_SNAPPROCESS = 0x00000002
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


# --- Win32 Structures ---
class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


# --- DLL Bindings ---
kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
psapi = ctypes.windll.psapi

# Setup proper 64-bit pointer return types
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.OpenProcess.restype = wintypes.HANDLE
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def get_app_pids() -> set[int]:
    """Identifies PIDs with visible taskbar/Alt-Tab windows (Task Manager 'Apps')."""
    app_pids = set()

    def enum_cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            ex_style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            # Exclude floating toolbars/overlays; require non-empty window title
            if not (ex_style & WS_EX_TOOLWINDOW) and user32.GetWindowTextLengthW(
                hwnd
            ) > 0:
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                app_pids.add(pid.value)
        return True

    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return app_pids


def get_memory_mb(pid: int) -> float:
    """Fetches Working Set memory in MB with minimal access rights."""
    h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h_proc:
        return 0.0
    try:
        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if psapi.GetProcessMemoryInfo(h_proc, ctypes.byref(pmc), pmc.cb):
            return pmc.WorkingSetSize / (1024 * 1024)
        return 0.0
    finally:
        kernel32.CloseHandle(h_proc)


def main():
    app_pids = get_app_pids()

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise ctypes.WinError()

    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)

    apps = []
    background = []

    try:
        if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                pid = entry.th32ProcessID
                name = entry.szExeFile
                mem_mb = get_memory_mb(pid)

                record = (pid, name, mem_mb)
                if pid in app_pids:
                    apps.append(record)
                else:
                    background.append(record)

                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)

    # Sort alphabetically like Task Manager
    apps.sort(key=lambda x: x[1].lower())
    background.sort(key=lambda x: x[1].lower())

    print(f"=== APPS ({len(apps)}) ===")
    print(f"{'PID':<8} {'Memory (MB)':<14} {'Name'}")
    for pid, name, mem in apps:
        print(f"{pid:<8} {mem:<14.1f} {name}")

    print(f"\n=== BACKGROUND PROCESSES ({len(background)}) ===")
    print(f"{'PID':<8} {'Memory (MB)':<14} {'Name'}")
    for pid, name, mem in background:
        print(f"{pid:<8} {mem:<14.1f} {name}")


if __name__ == "__main__":
    main()