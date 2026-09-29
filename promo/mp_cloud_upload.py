# -*- coding: utf-8 -*-
"""
mp_cloud_upload.py —— 段位卡云存储上传（客户端 wx.cloud.uploadFile 路线）的驱动。

与 mp_rect_*.py 同机制：先 mp_ws.ensure_port() arm 9420 自动化端口（并轮询到会话真就绪），
再把活交给 promo/mp_cloud_upload.js 在模拟器里执行。

为什么要这一层：9420 每次会话结束都会被 IDE 关掉，且刚 `cli auto` 完不能立刻连
（IDE 还在编译 ⇒ currentPage 报 rawPath null）。ensure_port 把盲等换成精确等待。

用法：<venv>/python.exe promo/mp_cloud_upload.py
输出：stdout 的 UPLOAD_JSON / SUMMARY（另有 PROBE 诊断行）
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mp_ws                                                     # noqa: E402

NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NM = r"C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules"

if not mp_ws.ensure_port():
    sys.exit(1)

env = dict(os.environ)
env["NODE_PATH"] = NM
env["PATH"] = os.path.dirname(NODE) + ";" + env.get("PATH", "")
env["MP_WS"] = "ws://127.0.0.1:9420"

r = subprocess.run([NODE, os.path.join(HERE, "mp_cloud_upload.js")],
                   cwd=os.path.dirname(HERE), capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env, timeout=300)
sys.stdout.write(r.stdout or "")
if r.stderr:
    sys.stdout.write("\n--- stderr ---\n" + r.stderr)
sys.exit(r.returncode)
