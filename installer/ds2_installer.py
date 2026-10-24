"""DS2 SotFS fix installer.

Features (chosen on screen):
  1. double-click / slow-start fix  : patches DarkSoulsII.exe (supported build only) + speed lock in the launcher
  2. key merge                      : Space = run/roll/jump, Q = lock-on + menu back (works on any DS2 build)
"""
import configparser, hashlib, os, shutil, stat, sys, threading, tkinter as tk
from tkinter import filedialog, messagebox, ttk

ORIG_SHA256 = "d83922bb1a27b2860e3e2f593333ec2d1db2bddf2a51eb39d141ecbab0652334"
PATCH_OFFSET = 0x199597
PATCH_ORIGINAL = bytes.fromhex("0fb6412688426d")
PATCH_PATCHED = bytes.fromhex("31c0ffc088426d")
GAME_EXE = "DarkSoulsII.exe"
OWN_FILES = ("launch_ds2.exe", "ds2_keys.ini", "ds2_fix.ini")


def res(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


ORIG_NAME = "DarkSoulsII_original.exe"  # the real game exe while DarkSoulsII.exe is replaced by the launcher


def is_our_launcher(path):
    """True if `path` is our launcher (small PyInstaller exe that contains our module), not the game."""
    try:
        if os.path.getsize(path) > 20 * 1024 * 1024:
            return False
        with open(path, "rb") as f:
            return b"ds2_keys" in f.read()
    except OSError:
        return False


def find_game_exe(folder):
    """The real game executable (DarkSoulsII_original.exe if the launcher replaced DarkSoulsII.exe)."""
    for sub in ("", "Game"):
        d = os.path.join(folder, sub)
        o = os.path.join(d, ORIG_NAME)
        if os.path.isfile(o):
            return o
        p = os.path.join(d, GAME_EXE)
        if os.path.isfile(p) and not is_our_launcher(p):
            return p
    return None


def undo_replace(gdir, log):
    """Put the real exe back under its original name. Returns True if nothing is left replaced."""
    orig = os.path.join(gdir, ORIG_NAME)
    cur = os.path.join(gdir, GAME_EXE)
    if not os.path.isfile(orig):
        return True
    if os.path.exists(cur):
        if not is_our_launcher(cur):
            log("※ DarkSoulsII.exe가 우리 실행기가 아니라서 이름을 되돌리지 않았습니다.")
            return False
        make_writable(cur)
        os.remove(cur)
    os.replace(orig, cur)
    if os.path.exists(orig + ".bak"):
        os.replace(orig + ".bak", cur + ".bak")
    log("DarkSoulsII.exe 이름을 원래대로 되돌렸습니다.")
    return True


def exe_state(exe):
    """'original' | 'patched' | 'unknown'"""
    with open(exe, "rb") as f:
        f.seek(PATCH_OFFSET)
        cur = f.read(len(PATCH_ORIGINAL))
    if cur == PATCH_PATCHED:
        return "patched"
    if cur == PATCH_ORIGINAL and sha256(exe) == ORIG_SHA256:
        return "original"
    return "unknown"


def make_writable(path):
    os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE)


def install(folder, want_fix, want_keys, want_replace, log):
    exe = find_game_exe(folder)
    if not exe:
        raise RuntimeError("선택한 폴더에서 DarkSoulsII.exe를 찾을 수 없습니다.\nDarkSoulsII.exe가 있는 폴더(또는 그 상위 폴더)를 선택하세요.")
    gdir = os.path.dirname(exe)
    log("게임 폴더: " + gdir)
    state = exe_state(exe)
    can_fix = want_fix and state in ("original", "patched")
    if want_fix and not can_fix:
        log("※ 지원하지 않는 게임 버전이라 더블클릭 수정은 건너뜁니다.")
        log("   (분석한 빌드: 3DM 2015년 4월판 SotFS 한 가지뿐입니다.)")
    if not (can_fix or want_keys):
        return False  # nothing to install: do not touch any file

    replaced = os.path.basename(exe).lower() == ORIG_NAME.lower()
    if want_replace and not replaced:
        orig = os.path.join(gdir, ORIG_NAME)
        os.replace(exe, orig)
        if os.path.exists(exe + ".bak"):
            os.replace(exe + ".bak", orig + ".bak")
        exe = orig
        log("원래 실행 파일을 DarkSoulsII_original.exe 로 바꿨습니다.")
    elif not want_replace and replaced:
        if undo_replace(gdir, log):
            exe = os.path.join(gdir, GAME_EXE)

    if can_fix:
        bak = exe + ".bak"
        if state == "original":
            if not os.path.exists(bak):
                shutil.copy2(exe, bak)
                log("원본 백업을 만들었습니다: " + os.path.basename(bak))
            make_writable(exe)
            with open(exe, "r+b") as f:
                f.seek(PATCH_OFFSET)
                f.write(PATCH_PATCHED)
            log("exe 패치를 적용했습니다.")
        else:
            log("exe 패치가 이미 적용되어 있습니다.")

    launcher = GAME_EXE if os.path.basename(exe).lower() == ORIG_NAME.lower() else "launch_ds2.exe"
    shutil.copyfile(res("launch_ds2.exe"), os.path.join(gdir, launcher))
    log(launcher + " 를 설치했습니다.")
    with open(os.path.join(gdir, "ds2_fix.ini"), "w", encoding="utf-8") as f:
        f.write("[features]\nspeed_lock = %d\n" % (1 if can_fix else 0))
    if want_keys:
        ini = os.path.join(gdir, "ds2_keys.ini")
        if os.path.exists(ini):
            log("ds2_keys.ini가 이미 있어 기존 설정을 유지합니다.")
        else:
            shutil.copyfile(res("ds2_keys.ini"), ini)
            log("ds2_keys.ini를 설치했습니다.")
    log("완료! 앞으로 게임은 %s 로 실행하세요." % launcher)
    if want_keys:
        log("※ 키 합치기를 쓰려면 DS2 키 설정에서 키를 지정해야 합니다. (아래 안내 참고)")
    return gdir


def launcher_name(gdir):
    return GAME_EXE if os.path.isfile(os.path.join(gdir, ORIG_NAME)) else "launch_ds2.exe"


def key_help_text(gdir=None):
    """Guide text; the keys are read from the installed ds2_keys.ini if there is one."""
    keys = {"run": "7", "jump": "8", "lockon": "9", "back": "0"}
    cp = configparser.ConfigParser(inline_comment_prefixes=(";",))
    candidates = [os.path.join(gdir, "ds2_keys.ini")] if gdir else []
    candidates.append(res("ds2_keys.ini"))
    for path in candidates:
        if os.path.isfile(path):
            cp.read(path, encoding="utf-8")
            if cp.has_section("output_keys"):
                keys.update({k: cp["output_keys"][k].upper() for k in keys if k in cp["output_keys"]})
                break
    replaced = bool(gdir) and os.path.isfile(os.path.join(gdir, ORIG_NAME))
    keys["launcher"] = GAME_EXE if replaced else "launch_ds2.exe"
    return (
        "■ 키 합치기 사용법\n\n"
        "1. 게임은 반드시 %(launcher)s 로 실행하세요.\n"
        + ("   (DarkSoulsII.exe가 실행기로 바뀌어 있어서 평소처럼 실행하면 됩니다.)\n\n" if replaced else
           "   (DarkSoulsII.exe를 직접 실행하면 적용되지 않습니다.)\n\n") +
        "2. 게임의 키 설정 화면에서 아래처럼 지정하세요.\n"
        "   (키보드 윗줄의 숫자키입니다. 숫자패드가 아닙니다.)\n\n"
        "      달리기 / 구르기   →  %(run)s\n"
        "      점프                   →  %(jump)s\n"
        "      락온                   →  %(lockon)s\n"
        "      메뉴 뒤로가기     →  %(back)s\n\n"
        "   위 키들이 다른 동작에 이미 지정되어 있으면 겹치므로 그 동작을 다른 키로 바꾸세요.\n\n"
        "3. 이제 이렇게 조작합니다.\n"
        "   · 스페이스바 짧게: 구르기    · 길게 누름: 대시\n"
        "   · 대시하다가 스페이스바를 뗐다가 바로 다시 누름: 점프\n"
        "   · Q: 락온 (메뉴에서는 뒤로가기)\n\n"
        "※ 이 기능이 켜져 있는 동안 게임은 진짜 스페이스바와 Q를 받지 못합니다.\n"
        "   (게임 창이 맨 앞일 때만 동작하고, 게임을 끄면 같이 꺼집니다.)\n"
        "※ 키나 점프 타이밍은 게임 폴더의 ds2_keys.ini 에서 바꿀 수 있습니다.\n"
        "   바꾼 뒤에는 게임을 껐다가 %(launcher)s 로 다시 실행하세요."
    ) % keys


def uninstall(folder, log):
    exe = find_game_exe(folder)
    if not exe:
        raise RuntimeError("선택한 폴더에서 DarkSoulsII.exe를 찾을 수 없습니다.")
    gdir = os.path.dirname(exe)
    if os.path.basename(exe).lower() == ORIG_NAME.lower():
        if not undo_replace(gdir, log):
            return
        exe = os.path.join(gdir, GAME_EXE)
    bak = exe + ".bak"
    if os.path.exists(bak):
        if sha256(bak) == ORIG_SHA256:
            make_writable(exe)
            shutil.copyfile(bak, exe)
            make_writable(bak)
            os.remove(bak)
            log("원본 DarkSoulsII.exe를 복원했습니다.")
        else:
            log("백업 파일의 해시가 달라 복원하지 않았습니다.")
    elif exe_state(exe) == "patched":
        log("※ 백업이 없어 exe 패치를 되돌릴 수 없습니다.")
    for name in OWN_FILES:
        p = os.path.join(gdir, name)
        if os.path.exists(p):
            make_writable(p)
            os.remove(p)
            log("삭제: " + name)
    log("제거를 마쳤습니다.")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("다크소울 2 SotFS 수정 설치")
        self.geometry("580x760")
        self.minsize(540, 700)
        pad = {"padx": 14}
        ttk.Label(self, text="다크소울 2 SotFS 수정 설치", font=("Malgun Gothic", 14, "bold")).pack(anchor="w", pady=(14, 2), **pad)
        ttk.Label(self, text="게임 폴더를 고르고 설치할 기능을 선택하세요.").pack(anchor="w", **pad)

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(12, 4), **pad)
        self.folder = tk.StringVar()
        guess = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
        if find_game_exe(guess):
            self.folder.set(guess)
        ttk.Entry(row, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="찾아보기", command=self.browse).pack(side="left", padx=(6, 0))

        self.fix = tk.BooleanVar(value=True)
        self.keys = tk.BooleanVar(value=True)
        self.replace = tk.BooleanVar(value=False)
        box = ttk.LabelFrame(self, text="설치할 기능")
        box.pack(fill="x", pady=8, **pad)
        ttk.Checkbutton(box, text="더블클릭 문제 수정 (시작할 때 느린 입력 문제)", variable=self.fix).pack(anchor="w", padx=8, pady=(6, 0))
        ttk.Label(box, text="게임 exe를 패치하고 실행기가 설정을 고정합니다.\n지원 버전: 3DM 2015년 4월판 SotFS(자동으로 검사). 다른 버전은 건너뜁니다.",
                  foreground="#555").pack(anchor="w", padx=30, pady=(0, 6))
        ttk.Checkbutton(box, text="키 합치기 (DS3 방식 조작)", variable=self.keys).pack(anchor="w", padx=8)
        ttk.Label(box, text="스페이스바: 달리기/구르기 + 대시 중 다시 누르면 점프\nQ: 락온 + 메뉴 뒤로가기   (어느 DS2 버전에서든 설치 가능)",
                  foreground="#555").pack(anchor="w", padx=30)
        hint = ttk.Frame(box)
        hint.pack(fill="x", padx=30, pady=(2, 8))
        ttk.Label(hint, text="※ 설치 후 게임 키 설정에서 키 4개를 지정해야 합니다.", foreground="#a33").pack(side="left")
        ttk.Button(hint, text="키 설정 도움말", command=self.show_key_help).pack(side="left", padx=8)

        opt = ttk.LabelFrame(self, text="고급 옵션")
        opt.pack(fill="x", pady=(0, 8), **pad)
        ttk.Checkbutton(opt, text="DarkSoulsII.exe 를 실행기로 대체", variable=self.replace).pack(anchor="w", padx=8, pady=(6, 0))
        ttk.Label(opt, wraplength=500, foreground="#555",
                  text="원래 exe 이름을 DarkSoulsII_original.exe 로 바꾸고, 실행기가 DarkSoulsII.exe 이름을 씁니다. "
                       "그러면 평소처럼 DarkSoulsII.exe 를 실행해도 적용됩니다. 이름을 바꾼 뒤에도 게임이 "
                       "실행되는지는 확인되지 않았으니, 문제가 생기면 '제거(원복)'을 누르세요."
                  ).pack(anchor="w", padx=30, pady=(0, 8))

        ttk.Label(self, wraplength=520, foreground="#a33",
                  text="주의: 온라인 플레이에서는 사용하지 마세요. 게임 파일과 메모리를 수정하므로 "
                       "계정 제재 위험이 있을 수 있습니다. 설치 전에 원본이 자동으로 백업됩니다.").pack(anchor="w", **pad)

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=8, **pad)
        ttk.Button(btns, text="설치", command=self.on_install).pack(side="left")
        ttk.Button(btns, text="제거(원복)", command=self.on_uninstall).pack(side="left", padx=6)
        ttk.Button(btns, text="닫기", command=self.destroy).pack(side="right")

        self.out = tk.Text(self, height=9, state="disabled", wrap="word")
        self.out.pack(fill="both", expand=True, pady=(0, 14), **pad)

    def log(self, msg):
        self.out.configure(state="normal")
        self.out.insert("end", msg + "\n")
        self.out.see("end")
        self.out.configure(state="disabled")
        self.update_idletasks()

    def browse(self):
        d = filedialog.askdirectory(title="DarkSoulsII.exe가 있는 폴더를 선택하세요")
        if d:
            self.folder.set(os.path.normpath(d))

    def run(self, fn, *args):
        folder = self.folder.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("폴더 선택", "게임 폴더를 먼저 선택하세요.")
            return
        try:
            return fn(folder, *args, self.log)
        except PermissionError:
            messagebox.showerror("오류", "파일을 쓸 수 없습니다.\n게임이 실행 중이면 종료한 뒤 다시 시도하세요.")
        except Exception as e:
            messagebox.showerror("오류", str(e))

    def show_key_help(self):
        gdir = None
        exe = find_game_exe(self.folder.get().strip()) if self.folder.get().strip() else None
        if exe:
            gdir = os.path.dirname(exe)
        messagebox.showinfo("키 설정 도움말", key_help_text(gdir))

    def on_install(self):
        if not (self.fix.get() or self.keys.get()):
            messagebox.showinfo("기능 선택", "설치할 기능을 하나 이상 선택하세요.")
            return
        gdir = self.run(install, self.fix.get(), self.keys.get(), self.replace.get())
        if gdir and self.keys.get():
            messagebox.showinfo("설치 완료 - 키 설정 안내", key_help_text(gdir))
        elif gdir:
            messagebox.showinfo("설치 완료", "설치가 끝났습니다.\n앞으로 게임은 %s 로 실행하세요." % launcher_name(gdir))

    def on_uninstall(self):
        if messagebox.askyesno("제거", "설치한 파일을 삭제하고 원본 exe로 되돌릴까요?"):
            self.run(uninstall)


if __name__ == "__main__":
    App().mainloop()
