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
r = I.install(t, True, True, True, None, log)
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
r = I.install(t, True, True, True, None, log)
ok(I.exe_state(orig) == "patched" and open(exe, "rb").read() == LAUNCHER, "still replaced and patched")

print("-- turning the option off undoes the rename")
r = I.install(t, True, True, False, None, log)
ok(not os.path.exists(orig), "DarkSoulsII_original.exe is gone")
ok(I.exe_state(exe) == "patched" and not I.is_our_launcher(exe), "DarkSoulsII.exe is the real (patched) exe again")
ok(has(g, "launch_ds2.exe", "DarkSoulsII.exe.bak"), "launch_ds2.exe installed, backup name restored")

print("-- uninstall from replace mode")
I.install(t, True, True, True, None, log)
I.uninstall(t, log)
ok(I.sha256(exe) == I.ORIG_SHA256, "original exe restored under its own name")
ok(not has(g, I.ORIG_NAME, "launch_ds2.exe", "ds2_keys.ini", "ds2_fix.ini", "DarkSoulsII.exe.bak", I.ORIG_NAME + ".bak"), "all installed files removed")

print("-- plain mode (no replace) still works")
t, g, exe = fresh()
I.install(t, True, True, False, None, log)
ok(I.exe_state(exe) == "patched" and has(g, "launch_ds2.exe", "ds2_keys.ini"), "patched + launch_ds2.exe")
I.uninstall(t, log)
ok(I.sha256(exe) == I.ORIG_SHA256, "uninstall restores")

print("-- nothing to install: no file is touched, even with replace on")
t, g, exe = fresh()
data = bytearray(open(exe, "rb").read()); data[0x2000] ^= 0xFF
os.chmod(exe, 0o666); open(exe, "wb").write(data)
before = bytes(data)
r = I.install(t, True, False, True, None, log)
ok(r is False and open(exe, "rb").read() == before and not has(g, I.ORIG_NAME), "unsupported build + fix only + replace = untouched")
r = I.install(t, False, True, True, None, log)
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

print("-- key validation")
good = {"run": "7", "jump": "8", "lockon": "9", "back": "0"}
v, e = I.validate_keys(good)
ok(e is None and v == good, "7/8/9/0 accepted")
v, e = I.validate_keys({"run": "num1", "jump": " f6 ", "lockon": "a", "back": "5"})
ok(e is None and v == {"run": "NUM1", "jump": "F6", "lockon": "A", "back": "5"}, "names are trimmed and upper-cased")
ok(I.validate_keys({**good, "jump": "7"})[1] is not None, "duplicate keys rejected")
ok(I.validate_keys({**good, "back": ""})[1] is not None, "empty key rejected")
ok(I.validate_keys({**good, "back": "banana"})[1] is not None, "unknown key name rejected")
ok(I.validate_keys({**good, "lockon": "q"})[1] is not None, "Q rejected as an output key")
ok(I.validate_keys({**good, "run": "space"})[1] is not None, "Space rejected as an output key")

print("-- custom keys in the ini")
t, g, exe = fresh()
I.install(t, False, True, False, {"run": "5", "jump": "6", "lockon": "F6", "back": "NUM2"}, log)
ini = os.path.join(g, "ds2_keys.ini")
txt = open(ini, encoding="utf-8").read()
ok(I.read_keys(g) == {"run": "5", "jump": "6", "lockon": "F6", "back": "NUM2"}, "keys written and read back")
ok("rejump_window = 200" in txt and "; DS2" in txt and "run_jump = SPACE" in txt, "comments, timing and input keys untouched")
cfg = I.ds2_keys.Config(ini)
ok((cfg.run, cfg.jump, cfg.lockon, cfg.back) == (0x35, 0x36, 0x75, 0x62), "launcher's own parser reads the new keys")
txt2 = txt.replace("rejump_window = 200", "rejump_window = 120")
open(ini, "w", encoding="utf-8").write(txt2)
I.install(t, False, True, False, {"run": "1", "jump": "2", "lockon": "3", "back": "4"}, log)
t3 = open(ini, encoding="utf-8").read()
ok(I.read_keys(g)["run"] == "1" and "rejump_window = 120" in t3, "reinstall changes keys but keeps user's timing")
ok("스페이스바" in I.key_help_text(g) and "→  1" in I.key_help_text(g), "help text shows the installed keys")
ok("→  Z" in I.key_help_text(g, {"run": "Z", "jump": "X", "lockon": "C", "back": "V"}), "help text shows keys typed in the boxes")

print("-- GUI builds")
app = I.App(); app.withdraw(); app.update()
ok(app.replace.get() is False, "replace option is off by default")
ok(app.typed_keys() == good, "key boxes start with 7/8/9/0")
app.folder.set(t); app.update()
ok(app.typed_keys() == {"run": "1", "jump": "2", "lockon": "3", "back": "4"}, "choosing a folder fills the boxes from its ds2_keys.ini")
app.destroy()

print("\nFAILED: %d" % len(failed) if failed else "\nall passed")
sys.exit(1 if failed else 0)
