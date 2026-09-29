# -*- coding: utf-8 -*-
"""
mp_call_fn.py —— 驱动：arm 9420 → 在模拟器里调云函数 → 打印结果。

用法：<venv>/python.exe promo/mp_call_fn.py <fnName> <start> <count>
例：  promo/mp_call_fn.py uploadRankAssets 0 2      # 先探 2 张
      promo/mp_call_fn.py uploadRankAssets 2 8      # 再补 8 张
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mp_ws                                                     # noqa: E402

NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NM = r"C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules"

args = sys.argv[1:] or ["uploadRankAssets", "0", "2"]

if not mp_ws.ensure_port():
    sys.exit(1)

env = dict(os.environ)
env["NODE_PATH"] = NM
env["PATH"] = os.path.dirname(NODE) + ";" + env.get("PATH", "")
env["MP_WS"] = "ws://127.0.0.1:9420"

r = subprocess.run([NODE, os.path.join(HERE, "mp_call_fn.js")] + args,
                   cwd=os.path.dirname(HERE), capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env, timeout=420)
sys.stdout.write(r.stdout or "")
if r.stderr:
    sys.stdout.write("\n--- stderr ---\n" + r.stderr)
sys.exit(r.returncode)
