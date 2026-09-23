# -*- coding: utf-8 -*-
"""
mp_gates.py —— 六道闸的统一驱动器。

为什么要有它：
  闸门有 10+ 条、分属 py / node / venv 三种解释器，还得逐条用 subprocess 起
  （本沙箱 bash 是坏的，不能写管道）。每次手搓既慢又容易漏跑、漏看退出码。

用法：
  python promo/mp_gates.py all                 # 全跑（不含需要 IDE 的 ⑥b/⑥c）
  python promo/mp_gates.py wxss lint smoke     # 只跑指定几道
  python promo/mp_gates.py --list              # 看名字

每道闸都单独打印退出码 + 尾部若干行；末尾给出汇总表。
⚠️ IDE 相关的闸（rectmp / rect / b2 像素差分）不放在这里的默认集合里：
   它们要求 9420 已 arm，且每次会话结束端口就被 IDE 收回（见 mp_ws.py）。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
PY = r"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"
VENV = r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NM = r"C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules"

# 名字 → (解释器, 脚本, 参数, 尾部行数)
GATES = {
    "build":     (PY,   "mp_build.py",          [], 14),
    "wxss":      (PY,   "mp_wxss_check.py",     [], 14),
    "lint":      (PY,   "mp_lint.py",           [], 22),
    "calc":      (NODE, "mp_calc_test.js",      [], 10),
    "food":      (NODE, "mp_food_test.js",      [], 10),
    "migrate":   (NODE, "mp_migrate_test.js",   [], 10),
    "market":    (NODE, "mp_market_test.js",    [], 16),
    "trade":     (NODE, "mp_trade_test.js",     [], 12),
    "board":     (NODE, "mp_board_test.js",     [], 12),
    "me":        (NODE, "mp_me_test.js",        [], 12),
    "ach":       (NODE, "mp_ach_test.js",       [], 12),
    "gacha":     (NODE, "mp_gacha_test.js",     [], 12),
    "smoke":     (NODE, "mp_smoke.js",          [], 14),
    "kline":     (VENV, "mp_kline_compare.py",  [], 14),
    "rectmp":    (VENV, "mp_rect_market.py",    [], 30),
    # ⑥b/⑥c 需要开发者工具已拉起（9420），不在默认集合里
    "recttrade": (VENV, "mp_rect_trade.py",     [], 30),
    "rectboard": (VENV, "mp_rect_board.py",     [], 30),
    "rectme":    (VENV, "mp_rect_me.py",        [], 30),
    "rectach":   (VENV, "mp_rect_ach_gacha.py", [], 30),
    "negwxss":   (PY,   "negctl_wxss.py",       [], 14),
    "negfoods":  (PY,   "negctl_foods.py",      [], 14),
    "negach":    (PY,   "negctl_ach_gacha.py",  [], 18),
}
# ⚠️ 新页面/新套件上线后**必须往这里加**：默认集合漏了某套 = 那套再没人跑。
DEFAULT = ["wxss", "lint", "calc", "food", "migrate", "market", "trade", "board", "me", "ach", "gacha", "smoke"]


def run(name):
    if name not in GATES:
        print("  未知闸：" + name)
        return None
    exe, script, args, tail = GATES[name]
    if not os.path.exists(exe):
        print("  解释器不存在：" + exe)
        return False
    env = dict(os.environ)
    env["NODE_PATH"] = NM
    env["PATH"] = os.path.dirname(exe) + ";" + env.get("PATH", "")
    p = subprocess.run([exe, os.path.join(HERE, script)] + args, cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    out = ((p.stdout or "") + (p.stderr or "")).splitlines()
    print("-" * 88)
    print("[%s] %s  exit=%s" % (name, script, p.returncode))
    for l in out[-tail:]:
        if l.strip():
            print("   " + l[:180])
    return p.returncode == 0


if __name__ == "__main__":
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--list" in sys.argv or not names:
        print("可用闸：" + " / ".join(GATES))
        print("默认集合：" + " ".join(DEFAULT))
        if not names:
            sys.exit(0)
    if names == ["all"]:
        names = DEFAULT
    res = []
    for n in names:
        print("")
        print("=" * 88)
        print("跑闸：" + n)
        print("=" * 88)
        res.append((n, run(n)))
    print("")
    print("=" * 88)
    print("汇总")
    print("=" * 88)
    bad = [n for n, r in res if not r]
    for n, r in res:
        print("   %-10s %s" % (n, "✅" if r else "❌"))
    print("RESULT=" + ("OK 全过" if not bad else "FAIL → " + ", ".join(bad)))
    sys.exit(0 if not bad else 1)
