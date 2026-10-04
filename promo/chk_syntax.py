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


def find_node():
    """定位 node。⛔ **别写死带补丁号的目录** —— 原先写的是 `22.22.2-3`，
    本机升到 `22.22.2-5` 之后这道「每次推送前必跑」的闸**一直在崩**：
    报的是 FileNotFoundError 栈，而不是「语法有问题」⇒ 一道白屏级的自检静默失效了。
    ⭐ 顺序：已知路径 → 扫 versions/*/node.exe 取最大版本 → 退回 PATH。
      全都找不到就返回 None（由调用方**明确报错并 exit 1**，而不是甩一段栈）。"""
    import glob
    cand = [r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-5\node.exe"]
    cand += sorted(glob.glob(
        r"C:\Users\Administrator\.workbuddy\binaries\node\versions\*\node.exe"), reverse=True)
    for c in cand:
        if c and os.path.exists(c):
            return c
    import shutil
    return shutil.which("node")


NODE = find_node()
if not NODE:
    print("⛔ 找不到 node —— 这道闸**没跑起来**，语法检查结果不可信（先修环境，别当通过）")
    sys.exit(1)

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
