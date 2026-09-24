# -*- coding: utf-8 -*-
"""
mp_integration_smoke.py —— ⑦ 跨页联调冒烟测试（端到端，需开发者工具 + 9420）。

自 arm 端口 → 拉起小程序 → 遍历 5 个 tab 验证渲染 → market→body-detail→back 导航闭环 →
在 trade tab 触发涨停验证 #celeb 组件送达 → 全程扫描 console 错误。

机制复用 mp_ws.ensure_port()（端口没起就 cli auto，再轮询就绪），与 ⑥b/⑥c 同款。
用法：python promo/mp_integration_smoke.py
报告落盘：promo/_integ_out.txt
"""
import os
import sys
import re
import json
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mp_ws import ensure_port, NODE, NM  # noqa: E402

OUT = os.path.join(HERE, '_integ_out.txt')


def run():
    if not ensure_port():
        msg = ('[integ] ✗ 9420 未就绪：开发者工具没开，或自动端口拉不起。\n'
               '         ⇒ 跨页联调需要先打开微信开发者工具并加载 E:\\WeChatProjects\\jianpan 工程。')
        print(msg)
        return 1

    env = dict(os.environ)
    env['NODE_PATH'] = NM
    env['PATH'] = os.path.dirname(NODE) + ';' + env.get('PATH', '')

    print('[integ] 跑探针 _integ_mp.js ...')
    try:
        r = subprocess.run([NODE, os.path.join(HERE, '_integ_mp.js')],
                           cwd=HERE, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', env=env, timeout=180)
    except subprocess.TimeoutExpired:
        print('[integ] ✗ 探针 180s 超时')
        return 1

    out = (r.stdout or '') + (r.stderr or '')
    m = re.search(r'INTEG_JSON=(\{.*\})', out)
    lines = []
    if not m:
        lines.append('[integ] ✗ 探针无 INTEG_JSON 输出：')
        lines.append(out[-2000:])
        _dump(lines)
        print('\n'.join(lines))
        return 1

    rep = json.loads(m.group(1))
    all_ok = True

    lines.append('=== 跨页联调冒烟（⑦） ===')
    for t in rep.get('tabs', []):
        flag = '✅' if t.get('ok') else '❌'
        if not t.get('ok'):
            all_ok = False
        lines.append('  %s tab %-9s route=%-30s %dx%d' % (
            flag, t.get('key'), t.get('route'), t.get('w', 0), t.get('h', 0)))

    nav = rep.get('nav', {})
    nav_ok = bool(nav.get('ok'))
    all_ok = all_ok and nav_ok
    lines.append('  %s nav market→body-detail→back  to=%s(%dpx) back=%s' % (
        '✅' if nav_ok else '❌', nav.get('to'), nav.get('toH', 0), nav.get('backTo')))

    cel = rep.get('celeb', {})
    cel_ok = bool(cel.get('ok'))
    all_ok = all_ok and cel_ok
    lines.append('  %s celeb 送达 fire=%s visible=%s' % (
        '✅' if cel_ok else '❌', cel.get('fire'), cel.get('visible')))

    errs = rep.get('consoleErrors', [])
    if errs:
        all_ok = False
        lines.append('  ❌ console 错误 %d 条：' % len(errs))
        for e in errs[:25]:
            lines.append('     ' + e[:200])
    else:
        lines.append('  ✅ 全程无 console 错误')

    lines.append('RESULT=' + ('OK' if all_ok else 'FAIL'))
    _dump(lines)
    print('\n'.join(lines))
    return 0 if all_ok else 1


def _dump(lines):
    try:
        with open(OUT, 'w', encoding='utf-8', newline='') as f:
            f.write('\n'.join(lines) + '\n')
    except Exception:
        pass


if __name__ == '__main__':
    sys.exit(run())
