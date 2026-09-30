# -*- coding: utf-8 -*-
r"""chk_syntax.py —— 把 index.html 的主 <script> 抽出来做语法检查（node --check）。
   白屏级事故里最便宜的一道自检：能在写完后 3 秒内发现语法错。

   用法：python promo/chk_syntax.py
   ⚠️ 文件名**不带**下划线是刻意的：`.gitignore` 的 `promo/_*.py` 只挡一次性脚本，
      而这是**每次推送前必跑的常规闸**，必须入库（2026-09-30 从 `_chk_syntax.py` 改名）。
      同理：⛔ 别改回下划线，也别加 `!promo/_chk_syntax.py` 白名单（那是跟约定打架）。"""
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"

html = io.open(os.path.join(REPO, "index.html"), encoding="utf-8").read()
blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
print("内联 script 块数 = %d" % len(blocks))
tot = 0
bad = 0
for i, b in enumerate(blocks):
    if len(b.strip()) < 60:
        continue
    tmp = os.path.join(HERE, "_chk_block.js")
    io.open(tmp, "w", encoding="utf-8", newline="").write(b)
    r = subprocess.run([NODE, "--check", tmp], capture_output=True)
    tot += 1
    if r.returncode == 0:
        print("  [ OK ] block #%d (%d 字符)" % (i, len(b)))
    else:
        bad += 1
        print("  [FAIL] block #%d" % i)
        print((r.stderr or b"").decode("utf-8", "replace")[:1500])
os.remove(tmp)
print("-" * 60)
print("语法检查：%d 块，失败 %d" % (tot, bad))
print("RESULT=%s" % ("OK" if bad == 0 else "FAIL"))
sys.exit(0 if bad == 0 else 1)
