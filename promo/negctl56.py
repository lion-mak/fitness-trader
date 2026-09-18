# -*- coding: utf-8 -*-
"""v2.7.56 专属负控：把已删除的 trading-floor-full.png 塞回 sw.js 预缓存清单，
确认新断言真的会红；随后还原并确认回到全绿。

只动 sw.js 一个文件，用 sha256 前后比对保证还原无损。
"""
import hashlib
import io
import os
import subprocess
import sys

D = r'E:\WorkBuddy\jianpan-ghpages'
SW = os.path.join(D, 'sw.js')
E2E = os.path.join(D, 'promo', 'e2e_test.py')
PY = r'C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe'

orig_bytes = open(SW, 'rb').read()
orig_sha = hashlib.sha256(orig_bytes).hexdigest()
s = orig_bytes.decode('utf-8')
anchor = "  './assets/icon-192.png',"
assert s.count(anchor) == 1, '锚点命中 %d 次' % s.count(anchor)


def run_e2e(tag):
    p = subprocess.run([PY, E2E], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=400)
    out = (p.stdout or '').splitlines()
    fails = [l for l in out if l.startswith('FAIL')]
    last = [l for l in out if l.startswith('RESULT=')]
    print('\n--- %s ---' % tag)
    print('FAIL 行数:', len(fails))
    for l in fails:
        print('   ', l[:190])
    print('RESULT:', last[-1] if last else '(无)')
    return fails, (last[-1] if last else '')


try:
    io.open(SW, 'w', encoding='utf-8', newline='').write(
        s.replace(anchor, "  './assets/trading-floor-full.png',\n" + anchor, 1))
    print('已注入死资源到预缓存清单 ->', SW)
    fails_a, res_a = run_e2e('注入后（期望：相关断言 FAIL）')
finally:
    io.open(SW, 'wb').write(orig_bytes)
    now_sha = hashlib.sha256(open(SW, 'rb').read()).hexdigest()
    print('\n还原 sw.js:', 'OK 无损' if now_sha == orig_sha else '❌ 还原不一致！')
    assert now_sha == orig_sha, 'sw.js 还原失败'

fails_b, res_b = run_e2e('还原后（期望：全绿）')

hit = [l for l in fails_a if ('交易大厅底图' in l or '真实存在' in l or '无死资源' in l)]
print('\n=== 负控判定 ===')
ok1 = res_a == 'RESULT=FAIL' and len(hit) >= 2
ok2 = len(fails_b) == 0 and res_b == 'RESULT=OK'
print('注入后确实红了且命中 %d 条针对性断言：%s' % (len(hit), 'OK' if ok1 else '❌'))
print('还原后回到全绿：%s' % ('OK' if ok2 else '❌'))
print('总结论:', 'PASS —— 新断言非恒真' if (ok1 and ok2) else 'FAIL')
sys.exit(0 if (ok1 and ok2) else 1)
