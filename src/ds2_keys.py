"""DS3-style key layer for DS2 SotFS.

Only acts while the DS2 window is in the foreground. Real Space and Q are
swallowed and replaced by the keys configured in ds2_keys.ini.
"""
import configparser, ctypes, ctypes.wintypes as w, os, sys, threading, time

HERE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
INI = os.path.join(HERE, "ds2_keys.ini")

_NAMED = {"SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "ESC": 0x1B, "BACKSPACE": 0x08,
          "SHIFT": 0xA0, "CTRL": 0xA2, "ALT": 0xA4, "CAPSLOCK": 0x14,
          "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
          "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28}
_EXTENDED = {0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28}


def vk_of(name):
    n = name.strip().upper()
    if n in _NAMED:
        return _NAMED[n]
    if len(n) == 1 and (n.isalpha() or n.isdigit()):
        return ord(n)
    if n[0] == "F" and n[1:].isdigit() and 1 <= int(n[1:]) <= 24:
        return 0x6F + int(n[1:])
    if n.startswith("NUM") and n[3:].isdigit() and 0 <= int(n[3:]) <= 9:
        return 0x60 + int(n[3:])
    raise ValueError("unknown key name: %r" % name)


class Config:
    def __init__(self, path=INI):
        cp = configparser.ConfigParser(inline_comment_prefixes=(";",))
        cp.read(path, encoding="utf-8")
        o, i, t = cp["output_keys"], cp["input_keys"], cp["timing_ms"]
        self.run, self.jump = vk_of(o["run"]), vk_of(o["jump"])
        self.lockon, self.back = vk_of(o["lockon"]), vk_of(o["back"])
        self.in_run_jump, self.in_lockon_back = vk_of(i["run_jump"]), vk_of(i["lockon_back"])
        self.sprint_hold = t.getint("sprint_hold")
        self.rejump_window = t.getint("rejump_window")
        self.jump_delay = t.getint("jump_delay")
        self.jump_press = t.getint("jump_press")


class Remapper:
    """Pure key logic. `send(vk, down)` and `later(ms, fn)` are injected so it can be tested."""

    def __init__(self, cfg, send, later, clock=time.monotonic):
        self.c, self.send, self.later, self.clock = cfg, send, later, clock
        self.lock = threading.RLock()
        self.reset(send_ups=False)

    def reset(self, send_ups=True):
        with self.lock:
            if send_ups:
                for vk, held in ((self.c.run, getattr(self, "run_down", False)),
                                 (self.c.lockon, getattr(self, "q_held", False)),
                                 (self.c.back, getattr(self, "q_held", False))):
                    if held:
                        self.send(vk, False)
            self.space_held = False
            self.run_down = False
            self.q_held = False
            self.press_t = 0.0
            self.last_hold = 0.0
            self.last_release = -1e9
            self.pending_up = None  # token of a delayed run-key release

    def _release_run(self, token):
        with self.lock:
            if self.pending_up == token and not self.space_held:
                self.pending_up = None
                if self.run_down:
                    self.run_down = False
                    self.send(self.c.run, False)

    def on_key(self, vk, down):
        """Returns True if the physical key event must be swallowed."""
        c = self.c
        with self.lock:
            now = self.clock() * 1000.0
            if vk == c.in_run_jump:
                if down:
                    if self.space_held:
                        return True  # auto-repeat
                    self.space_held = True
                    self.press_t = now
                    # run key is still held during the re-jump window after a sprint
                    jump = self.pending_up is not None
                    self.pending_up = None
                    if not self.run_down:
                        self.run_down = True
                        self.send(c.run, True)
                    if jump:
                        self.later(c.jump_delay, lambda: self.send(c.jump, True))
                        self.later(c.jump_delay + c.jump_press, lambda: self.send(c.jump, False))
                    return True
                if not self.space_held:
                    return False  # press started outside the game
                self.space_held = False
                self.last_hold = now - self.press_t
                self.last_release = now
                if self.run_down:
                    if self.last_hold >= c.sprint_hold:
                        # sprinting: keep run held briefly so a quick re-press can jump
                        token = self.pending_up = object()
                        self.later(c.rejump_window, lambda: self._release_run(token))
                    else:
                        self.run_down = False
                        self.send(c.run, False)
                return True
            if vk == c.in_lockon_back:
                if down:
                    if self.q_held:
                        return True
                    self.q_held = True
                    self.send(c.lockon, True)
                    self.send(c.back, True)
                    return True
                if not self.q_held:
                    return False
                self.q_held = False
                self.send(c.lockon, False)
                self.send(c.back, False)
                return True
        return False


# ---------------------------------------------------------------- Windows glue
user32 = ctypes.WinDLL("user32", use_last_error=True)
ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD), ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _U)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, w.WPARAM, w.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, w.WPARAM, w.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.GetForegroundWindow.restype = w.HWND
user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
user32.PeekMessageW.argtypes = [ctypes.c_void_p, w.HWND, w.UINT, w.UINT, w.UINT]
user32.MsgWaitForMultipleObjects.argtypes = [w.DWORD, ctypes.c_void_p, w.BOOL, w.DWORD, w.DWORD]

KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8
LLKHF_INJECTED = 0x10
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105


def send_key(vk, down):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0) | (0 if down else KEYEVENTF_KEYUP)
    scan = user32.MapVirtualKeyW(vk, 0)
    inp = INPUT(type=1)
    inp.u.ki = KEYBDINPUT(0, scan, flags, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def later(ms, fn):
    t = threading.Timer(ms / 1000.0, fn)
    t.daemon = True
    t.start()


def foreground_pid():
    pid = w.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value


def run(stop_event, game_pid, cfg=None):
    """Install the hook and pump messages until stop_event is set."""
    cfg = cfg or Config()
    rm = Remapper(cfg, send_key, later)
    watched = {cfg.in_run_jump, cfg.in_lockon_back}

    def proc(n, wp, lp):
        if n == 0 and wp in (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP):
            k = KBDLLHOOKSTRUCT.from_address(lp)
            if not (k.flags & LLKHF_INJECTED) and k.vkCode in watched:
                if foreground_pid() == game_pid:
                    if rm.on_key(k.vkCode, wp in (WM_KEYDOWN, WM_SYSKEYDOWN)):
                        return 1
                else:
                    rm.reset()
        return user32.CallNextHookEx(None, n, wp, lp)

    cb = HOOKPROC(proc)  # keep a reference
    hook = user32.SetWindowsHookExW(13, cb, None, 0)
    if not hook:
        raise OSError("SetWindowsHookEx failed (%d)" % ctypes.get_last_error())
    msg = ctypes.create_string_buffer(64)
    try:
        while not stop_event.is_set():
            user32.MsgWaitForMultipleObjects(0, None, False, 20, 0x04FF)
            while user32.PeekMessageW(msg, None, 0, 0, 1):
                pass
            if foreground_pid() != game_pid and (rm.space_held or rm.q_held or rm.run_down):
                rm.reset()
    finally:
        rm.reset()
        user32.UnhookWindowsHookEx(hook)
