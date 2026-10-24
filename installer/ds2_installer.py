"""DS2 SotFS fix installer.

Features (chosen on screen):
  1. double-click / slow-start fix  : patches DarkSoulsII.exe (supported build only) + speed lock in the launcher
  2. key merge                      : Space = run/roll/jump, Q = lock-on + menu back (works on any DS2 build)
"""
import hashlib, os, shutil, stat, sys, threading, tkinter as tk
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


def find_game_exe(folder):
    for sub in ("", "Game"):
        p = os.path.join(folder, sub, GAME_EXE)
        if os.path.isfile(p):
            return p
    return None


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


def install(folder, want_fix, want_keys, log):
    exe = find_game_exe(folder)
    if not exe:
        raise RuntimeError("선택한 폴더에서 DarkSoulsII.exe를 찾을 수 없습니다.\nDarkSoulsII.exe가 있는 폴더(또는 그 상위 폴더)를 선택하세요.")
    gdir = os.path.dirname(exe)
    log("게임 폴더: " + gdir)
    state = exe_state(exe)
    fix_ok = False

    if want_fix:
        bak = exe + ".bak"
        if state == "original":
            if not os.path.exists(bak):
                shutil.copy2(exe, bak)
                log("원본 백업을 만들었습니다: DarkSoulsII.exe.bak")
            make_writable(exe)
            with open(exe, "r+b") as f:
                f.seek(PATCH_OFFSET)
                f.write(PATCH_PATCHED)
            log("exe 패치를 적용했습니다.")
            fix_ok = True
        elif state == "patched":
            log("exe 패치가 이미 적용되어 있습니다.")
            fix_ok = True
        else:
            log("※ 지원하지 않는 게임 버전이라 더블클릭 수정은 건너뜁니다.")
            log("   (분석한 빌드: 3DM 2015년 4월판 SotFS 한 가지뿐입니다.)")

    if not (fix_ok or want_keys):
        return False

    shutil.copyfile(res("launch_ds2.exe"), os.path.join(gdir, "launch_ds2.exe"))
    log("launch_ds2.exe를 설치했습니다.")
    with open(os.path.join(gdir, "ds2_fix.ini"), "w", encoding="utf-8") as f:
        f.write("[features]\nspeed_lock = %d\n" % (1 if fix_ok else 0))
    if want_keys:
        ini = os.path.join(gdir, "ds2_keys.ini")
        if os.path.exists(ini):
            log("ds2_keys.ini가 이미 있어 기존 설정을 유지합니다.")
        else:
            shutil.copyfile(res("ds2_keys.ini"), ini)
            log("ds2_keys.ini를 설치했습니다.")
    log("완료! 앞으로 게임은 launch_ds2.exe로 실행하세요.")
    return True


def uninstall(folder, log):
    exe = find_game_exe(folder)
    if not exe:
        raise RuntimeError("선택한 폴더에서 DarkSoulsII.exe를 찾을 수 없습니다.")
    gdir = os.path.dirname(exe)
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
        self.geometry("560x520")
        self.minsize(520, 480)
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
        box = ttk.LabelFrame(self, text="설치할 기능")
        box.pack(fill="x", pady=8, **pad)
        ttk.Checkbutton(box, text="더블클릭 문제 수정 (시작할 때 느린 입력 문제)", variable=self.fix).pack(anchor="w", padx=8, pady=(6, 0))
        ttk.Label(box, text="게임 exe를 패치하고 실행기가 설정을 고정합니다.\n지원 버전: 3DM 2015년 4월판 SotFS(자동으로 검사). 다른 버전은 건너뜁니다.",
                  foreground="#555").pack(anchor="w", padx=30, pady=(0, 6))
        ttk.Checkbutton(box, text="키 합치기 (DS3 방식 조작)", variable=self.keys).pack(anchor="w", padx=8)
        ttk.Label(box, text="스페이스바: 달리기/구르기 + 대시 중 다시 누르면 점프\nQ: 락온 + 메뉴 뒤로가기   (어느 DS2 버전에서든 설치 가능)",
                  foreground="#555").pack(anchor="w", padx=30, pady=(0, 6))

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
            fn(folder, *args, self.log)
        except PermissionError:
            messagebox.showerror("오류", "파일을 쓸 수 없습니다.\n게임이 실행 중이면 종료한 뒤 다시 시도하세요.")
        except Exception as e:
            messagebox.showerror("오류", str(e))

    def on_install(self):
        if not (self.fix.get() or self.keys.get()):
            messagebox.showinfo("기능 선택", "설치할 기능을 하나 이상 선택하세요.")
            return
        self.run(install, self.fix.get(), self.keys.get())

    def on_uninstall(self):
        if messagebox.askyesno("제거", "설치한 파일을 삭제하고 원본 exe로 되돌릴까요?"):
            self.run(uninstall)


if __name__ == "__main__":
    App().mainloop()
