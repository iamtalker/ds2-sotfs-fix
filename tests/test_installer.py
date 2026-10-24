"""Installer logic tests.

usage: python tests/test_installer.py <path to an ORIGINAL (unpatched) DarkSoulsII.exe of the supported build>

Everything runs on temporary copies; the given exe is only read.
"""
import os, shutil, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DS2_ORIGINAL_EXE")
if not SRC or not os.path.isfile(SRC):
    sys.exit("give the path of the original DarkSoulsII.exe as argument or DS2_ORIGINAL_EXE")

RES = tempfile.mkdtemp()
shutil.copy(os.path.join(REPO, "src", "ds2_keys.ini"), RES)
LAUNCHER = b"MZ-fake-launcher ds2_keys " + b"\0" * 64   # stands in for the real launcher exe
open(os.path.join(RES, "launch_ds2.exe"), "wb").write(LAUNCHER)
sys._MEIPASS = RES
sys.path.insert(0, os.path.join(REPO, "installer"))
import ds2_installer as I

failed = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failed.append(msg)


def fresh():
    t = tempfile.mkdtemp()
    os.makedirs(os.path.join(t, "Game"))
    exe = os.path.join(t, "Game", "DarkSoulsII.exe")
    shutil.copy(SRC, exe)
    os.chmod(exe, 0o444)  # like the real read-only file
    return t, os.path.join(t, "Game"), exe


def has(g, *names):
    return all(os.path.exists(os.path.join(g, n)) for n in names)


log = lambda m: None

print("-- replace mode: install")
t, g, exe = fresh()
r = I.install(t, True, True, True, log)
orig = os.path.join(g, I.ORIG_NAME)
ok(r == g, "returns the game dir")
ok(I.exe_state(orig) == "patched", "real exe is DarkSoulsII_original.exe and patched")
ok(open(exe, "rb").read() == LAUNCHER, "DarkSoulsII.exe is now the launcher")
ok(os.path.exists(orig + ".bak") and I.sha256(orig + ".bak") == I.ORIG_SHA256, "backup follows the rename")
ok(not has(g, "DarkSoulsII.exe.bak"), "no stray backup under the old name")
ok(I.find_game_exe(t) == orig, "find_game_exe resolves to the real exe")
ok(I.is_our_launcher(exe) and not I.is_our_launcher(orig), "launcher vs game detection")
ok(I.launcher_name(g) == "DarkSoulsII.exe", "launcher name reported correctly")

print("-- replace mode: install again is idempotent")
r = I.install(t, True, True, True, log)
ok(I.exe_state(orig) == "patched" and open(exe, "rb").read() == LAUNCHER, "still replaced and patched")

print("-- turning the option off undoes the rename")
r = I.install(t, True, True, False, log)
ok(not os.path.exists(orig), "DarkSoulsII_original.exe is gone")
ok(I.exe_state(exe) == "patched" and not I.is_our_launcher(exe), "DarkSoulsII.exe is the real (patched) exe again")
ok(has(g, "launch_ds2.exe", "DarkSoulsII.exe.bak"), "launch_ds2.exe installed, backup name restored")

print("-- uninstall from replace mode")
I.install(t, True, True, True, log)
I.uninstall(t, log)
ok(I.sha256(exe) == I.ORIG_SHA256, "original exe restored under its own name")
ok(not has(g, I.ORIG_NAME, "launch_ds2.exe", "ds2_keys.ini", "ds2_fix.ini", "DarkSoulsII.exe.bak", I.ORIG_NAME + ".bak"), "all installed files removed")

print("-- plain mode (no replace) still works")
t, g, exe = fresh()
I.install(t, True, True, False, log)
ok(I.exe_state(exe) == "patched" and has(g, "launch_ds2.exe", "ds2_keys.ini"), "patched + launch_ds2.exe")
I.uninstall(t, log)
ok(I.sha256(exe) == I.ORIG_SHA256, "uninstall restores")

print("-- nothing to install: no file is touched, even with replace on")
t, g, exe = fresh()
data = bytearray(open(exe, "rb").read()); data[0x2000] ^= 0xFF
os.chmod(exe, 0o666); open(exe, "wb").write(data)
before = bytes(data)
r = I.install(t, True, False, True, log)
ok(r is False and open(exe, "rb").read() == before and not has(g, I.ORIG_NAME), "unsupported build + fix only + replace = untouched")
r = I.install(t, False, True, True, log)
ok(r == g and has(g, I.ORIG_NAME) and open(exe, "rb").read() == LAUNCHER, "keys-only + replace works on any build")
ok(open(os.path.join(g, I.ORIG_NAME), "rb").read() == before, "unsupported exe is renamed but not modified")
ok(not os.path.exists(os.path.join(g, I.ORIG_NAME + ".bak")), "no backup/patch for unsupported exe")
I.uninstall(t, log)
ok(open(exe, "rb").read() == before, "unsupported exe returned unchanged")

print("-- safety: never delete a DarkSoulsII.exe that is not our launcher")
t, g, exe = fresh()
shutil.copy(exe, os.path.join(g, I.ORIG_NAME))      # both look like a real game
msgs = []
done = I.undo_replace(g, msgs.append)
ok(done is False and I.sha256(exe) == I.ORIG_SHA256, "refuses and keeps the real exe")

print("-- GUI builds")
app = I.App(); app.withdraw(); app.update()
ok(app.replace.get() is False, "replace option is off by default")
app.destroy()

print("\nFAILED: %d" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
