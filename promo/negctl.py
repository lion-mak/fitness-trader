# -*- coding: utf-8 -*-
"""负控：故意塞一条必败断言，确认 RESULT 真的会变 FAIL（防 e2e 假绿灯复发）。"""
import io
import os
import re
import subprocess

HERE = r'E:\WorkBuddy\jianpan-ghpages\promo'
SRC = os.path.join(HERE, 'e2e_test.py')
TMP = os.path.join(HERE, '_e2e_neg.py')
PY = r'C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe'

s = io.open(SRC, encoding='utf-8', newline='').read()
anchor = "    print('\\nRESULT=' + ('OK' if ok else 'FAIL'))"
assert s.count(anchor) == 1, '锚点命中 %d 次' % s.count(anchor)
s2 = s.replace(anchor, "    chk('负控：这条必须失败', False, 'deliberate')\n" + anchor, 1)
io.open(TMP, 'w', encoding='utf-8', newline='').write(s2)

p = subprocess.run([PY, TMP], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
out = p.stdout or ''
last = [l for l in out.splitlines() if l.startswith('RESULT=')]
fails = [l for l in out.splitlines() if l.startswith('FAIL')]
print('负控运行 RESULT 行:', last[-1] if last else '(无)')
print('FAIL 行数:', len(fails))
print('判定:', 'OK —— 假断言确实把 RESULT 拉成 FAIL' if (last and last[-1] == 'RESULT=FAIL') else '❌ 负控失败，e2e 又是假绿灯')
os.remove(TMP)
