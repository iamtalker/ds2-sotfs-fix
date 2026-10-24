"""Launch DS2 SotFS (3DM build) and keep the "double-click disabled" byte at 1.

At startup the game never applies the saved option, so the runtime byte stays 0
until the options menu is touched. This launcher starts the game, waits for the
object to exist, then keeps the byte at 1 for as long as the game runs.
Requires the patched DarkSoulsII.exe (ds2_nodblclk_patch.py) so later settings
applies also write 1.
"""
import configparser, ctypes, ctypes.wintypes as w, os, struct, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))


def _is_self(path):
    try:
        return getattr(sys, "frozen", False) and os.path.samefile(path, sys.executable)
    except OSError:
        return False


def _find_game_exe():
    # installed as a replacement for DarkSoulsII.exe: the real game is DarkSoulsII_original.exe
    for sub in ("", "Game"):
        for name in ("DarkSoulsII_original.exe", "DarkSoulsII.exe"):
            p = os.path.join(HERE, sub, name)
            if os.path.isfile(p) and not _is_self(p):
                return p
    return os.path.join(HERE, "DarkSoulsII.exe")


EXE = _find_game_exe()
GAME_DIR = os.path.dirname(EXE)
GLOBAL_RVA = 0x166C1D8   # VA 0x14166c1d8
FLAG_OFF = 0x6D
KNOWN_TIMESTAMP = 1429527574  # PE timestamp of the only build the memory offsets were made for


def exe_timestamp(path):
    with open(path, "rb") as f:
        head = f.read(4096)
    pe = struct.unpack_from("<I", head, 0x3C)[0]
    return struct.unpack_from("<I", head, pe + 8)[0]


def speed_lock_enabled():
    """Memory writes are only done on the supported build and only if not disabled in ds2_fix.ini."""
    cp = configparser.ConfigParser()
    cp.read(os.path.join(HERE, "ds2_fix.ini"), encoding="utf-8")
    if not cp.getboolean("features", "speed_lock", fallback=True):
        return False
    try:
        return exe_timestamp(EXE) == KNOWN_TIMESTAMP
    except OSError:
        return False

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
k32.OpenProcess.restype = w.HANDLE
k32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
k32.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
psapi.EnumProcessModules.argtypes = [w.HANDLE, ctypes.POINTER(w.HMODULE), w.DWORD, ctypes.POINTER(w.DWORD)]

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
STILL_ACTIVE = 259


def rd(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)) or got.value != n:
        return None
    return buf.raw


def q(h, addr):
    b = rd(h, addr, 8)
    return int.from_bytes(b, "little") if b else None


def flag_addr(h, base):
    g = q(h, base + GLOBAL_RVA)
    a = q(h, g + 0x60) if g else None
    b = q(h, a) if a else None
    c = q(h, b + 8) if b else None
    return c + FLAG_OFF if c else None


def alive(h):
    code = w.DWORD()
    return k32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value == STILL_ACTIVE


def main():
    if not os.path.exists(EXE):
        sys.exit("game executable not found next to the launcher")
    proc = subprocess.Popen([EXE], cwd=GAME_DIR)
    access = PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE
    h = None
    for _ in range(100):
        h = k32.OpenProcess(access, False, proc.pid)
        if h:
            break
        time.sleep(0.1)
    if not h:
        sys.exit("could not open the game process (error %d)" % ctypes.get_last_error())
    mods = (w.HMODULE * 1)()
    need = w.DWORD()
    base = None
    while alive(h) and base is None:
        if psapi.EnumProcessModules(h, mods, ctypes.sizeof(mods), ctypes.byref(need)) and mods[0]:
            base = mods[0]
        else:
            time.sleep(0.2)
    stop = threading.Event()
    keys = None
    if os.path.exists(os.path.join(HERE, "ds2_keys.ini")):
        try:
            sys.path.insert(0, HERE)
            import ds2_keys

            def keys_main():
                try:
                    ds2_keys.run(stop, proc.pid)
                except Exception as e:
                    print("key layer stopped:", e)

            keys = threading.Thread(target=keys_main, daemon=True)
            keys.start()
            print("key layer on (Space/Q remapped)")
        except Exception as e:
            print("key layer disabled:", e)
    announced = False
    lock = speed_lock_enabled()
    try:
        while alive(h):
            addr = flag_addr(h, base) if lock else None
            if addr:
                cur = rd(h, addr, 1)
                if cur is not None and cur[0] != 1:
                    written = ctypes.c_size_t()
                    k32.WriteProcessMemory(h, ctypes.c_void_p(addr), b"\x01", 1, ctypes.byref(written))
                    if not announced:
                        print("double-click option forced ON")
                        announced = True
            time.sleep(0.5)
    finally:
        stop.set()
        if keys:
            keys.join(3)


if __name__ == "__main__":
    main()
