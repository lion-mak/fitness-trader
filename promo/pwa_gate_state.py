# -*- coding: utf-8 -*-
"""pwa_gate_state.py —— PWA 存档读写闸（冷启动安全闸）

由来：2026-09-25 真事故 —— `loadState()` 走的 `applyCurveUpgrade()` 读了声明在其调用点
**之后**的 `const CURVE_VER`，在 TDZ 里抛 ReferenceError，被 `catch(e) {}` 静默吞掉 ⇒
返回 `defaultState()` 空档 ⇒ `render()` 末尾无条件 `saveState()` 把空档写回
⇒ 用户存档被永久覆盖（症状：数据全清零、头像退回内联 SVG 占位人形、体重 K 线无历史）。
整条链上没有任何一处会报错、没有任何测试会变红 —— 所以要有这道闸。

闸做四件事（前三条是「正向必须绿」，第四条是「负控必须红」，负控见 negctl_pwa_state.py）：
  A 存档存活 冷启动后存储里的存档仍在，且关键字段与预期等价（不是被空档覆盖）
  B 页面真读到了 页面上显示的累计数 / 段位 / 持仓天数与存档一致（防「读进去了但没用上」）
  C 写入通道健康 保护模式没被误触发（改一个值能真的落盘）+ 零 console error
  D 负控 见 negctl_pwa_state.py：把 CURVE_VER 挪回调用点之后 ⇒ 本闸必须变红

用法：python promo/pwa_gate_state.py        # 退出码 0=绿 1=红
"""
import io
import os
import sys
import json
import threading
import functools
import http.server
import socketserver

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KEY = u'jianpan_v2'
OUT = os.path.join(HERE, u'_pwa_gate_state_out.txt')

# ---- 期望值独立现算（⛔不从被测代码里抄，否则闸会跟着代码一起错）----
RANKS = [(u'韭菜', 1), (u'散户', 2), (u'中户', 4), (u'大户', 7), (u'牛散', 10),
         (u'游资', 13), (u'主力', 16), (u'机构', 20), (u'庄家', 24), (u'股神', 30)]


def exp_for_lv(lv):
    return 5 * lv * (lv - 1)


def lv_from_exp(e):
    lv = 1
    while exp_for_lv(lv + 1) <= e:
        lv += 1
    return lv


def rank_of(lv):
    return [n for n, m in RANKS if lv >= m][-1]


def curve_upgraded_exp(e):
    """applyCurveUpgrade 的口径：旧曲线 lv 保底。"""
    lv_old = e // 100 + 1
    return max(e, exp_for_lv(lv_old))


def serve(root):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port


def launch_browser(pw):
    last = None
    for kw in ({"channel": "msedge"},
               {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"}):
        try:
            return pw.chromium.launch(**kw)
        except Exception as e:      # noqa: BLE001
            last = e
    raise SystemExit(u'找不到可用浏览器内核：%s' % last)


class Gate(object):
    def __init__(self):
        self.total = 0
        self.failed = []

    def ok(self, cond, label, got=u''):
        self.total += 1
        if cond:
            print(u'  [OK  ] %s' % label)
        else:
            self.failed.append(label)
            print(u'  [FAIL] %s' % label + (u'   got=%s' % got if got != u'' else u''))

    def report(self):
        print()
        print(u'共 %d 项，失败 %d' % (self.total, len(self.failed)))
        for f in self.failed:
            print(u'  ✗ %s' % f)
        return 1 if self.failed else 0


def main():
    log = []

    def p(s=u''):
        log.append(s)
        print(s)

    mock_path = os.path.join(HERE, u'mock.json')
    if not os.path.exists(mock_path):
        print(u'⛔ 缺少 promo/mock.json（闸的载荷来源），无法运行')
        return 1
    seed = json.load(io.open(mock_path, encoding=u'utf-8'))[u'state']
    seed.setdefault(u'user', {})
    if not seed[u'user'].get(u'avatar'):
        seed[u'user'][u'avatar'] = u'data:image/jpeg;base64,' + (u'A' * 4000)
    payload = json.dumps(seed, ensure_ascii=False)

    want_diet = len(seed.get(u'diet') or [])
    want_ex = len(seed.get(u'exercise') or [])
    want_exp = curve_upgraded_exp(int(seed.get(u'exp') or 0))
    want_lv = lv_from_exp(want_exp)
    want_rank = rank_of(want_lv)
    want_limitup = int(seed.get(u'limitUpCount') or 0)

    p(u'# PWA 存档读写闸（冷启动安全）')
    p(u'  载荷 %s：%d 字符  diet=%d ex=%d exp=%d→(补偿后)%d lv=%d %s'
      % (os.path.basename(mock_path), len(payload), want_diet, want_ex,
         int(seed.get(u'exp') or 0), want_exp, want_lv, want_rank))
    p()

    g = Gate()
    srv, port = serve(ROOT)
    url = u'http://127.0.0.1:%d/index.html' % port
    console_errs = []

    with sync_playwright() as pw:
        b = launch_browser(pw)
        ctx = b.new_context(viewport={'width': 430, 'height': 932})
        # 页面脚本执行前就写入存档 —— 这样 loadState() 在**冷启动路径**上必须读到它。
        # （⛔不能「先 goto 再 evaluate 写」：那样测的是热路径，恰好绕过了当初出事的时机。）
        ctx.add_init_script(u"try{localStorage.setItem('jianpan_v2',"
                            + json.dumps(payload) + u");}catch(e){}")
        page = ctx.new_page()
        page.on(u'pageerror', lambda e: console_errs.append(u'pageerror: %s' % e))
        page.on(u'console', lambda m: console_errs.append(
            u'console.%s: %s' % (m.type, m.text)) if m.type == u'error' else None)

        page.goto(url, wait_until=u'load')
        page.wait_for_timeout(3200)      # 等 SW 接管 + ver.txt 的异步回调跑完
        page.reload(wait_until=u'load')  # 二次冷启动：走「存储里已有存档」的分支
        page.wait_for_timeout(3200)

        snap = page.evaluate("""() => {
            const raw = localStorage.getItem('jianpan_v2');
            let st = null;
            try { st = raw ? JSON.parse(raw) : null; } catch (e) { st = null; }
            const g = (id) => { const el = document.getElementById(id); return el ? el.textContent : null; };
            return {
                storeLen: raw ? raw.length : 0,
                diet: st && Array.isArray(st.diet) ? st.diet.length : null,
                ex: st && Array.isArray(st.exercise) ? st.exercise.length : null,
                exp: st ? st.exp : null,
                avLen: st && st.user && st.user.avatar ? st.user.avatar.length : 0,
                curve: st ? st.curve : null,
                memDiet: state && Array.isArray(state.diet) ? state.diet.length : null,
                domDiet: g('p-diet'), domEx: g('p-ex'), domLvl: g('p-lvl'),
                domTitle: g('p-title'), railKids: (function(){
                    const t = document.getElementById('rail-track'); return t ? t.children.length : -1; })(),
                ver: (document.querySelector('meta[name=app-version]') || {}).content
            };
        }""")
        p(u'  冷启动后：存储 %d 字符  diet=%s ex=%s exp=%s avatar=%s字符 curve=%s'
          % (snap['storeLen'], snap['diet'], snap['ex'], snap['exp'], snap['avLen'], snap['curve']))
        p(u'  页面显示：%s · lv %s · 累计饮食 %s / 运动 %s'
          % (snap['domTitle'], snap['domLvl'], snap['domDiet'], snap['domEx']))
        p()

        # A 存档存活（核心：不许被空档覆盖）
        g.ok(snap['storeLen'] > 50000, u'A1 存档没被空档覆盖（存储 >50KB）', snap['storeLen'])
        g.ok(snap['diet'] == want_diet, u'A2 diet 条数 = %d' % want_diet, snap['diet'])
        g.ok(snap['ex'] == want_ex, u'A3 exercise 条数 = %d' % want_ex, snap['ex'])
        g.ok(snap['exp'] == want_exp, u'A4 exp = %d（含曲线补偿）' % want_exp, snap['exp'])
        g.ok(snap['avLen'] > 1000, u'A5 avatar 字段存活（>1000 字符）', snap['avLen'])
        g.ok(snap['curve'] == 2, u'A6 curve 幂等锚 = 2', snap['curve'])

        # B 页面真读到了
        g.ok(snap['memDiet'] == want_diet, u'B1 内存 state.diet = %d' % want_diet, snap['memDiet'])
        g.ok(snap['domDiet'] == str(want_diet), u'B2 页面「累计饮食」= %d' % want_diet, snap['domDiet'])
        g.ok(snap['domEx'] == str(want_ex), u'B3 页面「累计运动」= %d' % want_ex, snap['domEx'])
        g.ok(snap['domLvl'] == u'lv %d' % want_lv, u'B4 页面段位 = lv %d' % want_lv, snap['domLvl'])
        g.ok(bool(snap['domTitle']) and want_rank in (snap['domTitle'] or u''),
             u'B5 页头段位名 = %s' % want_rank, snap['domTitle'])
        g.ok(u'持仓 %d 天' % want_limitup in (snap['domTitle'] or u''),
             u'B6 页头持仓天数 = %d（import 来的 limitUpCount）' % want_limitup, snap['domTitle'])

        # B7+ 卡廊要在**切到「我的」页之后**才验：卡廊的定位依赖可见尺寸（隐藏页 clientWidth=0，
        # 故 renderRail 会先跳过建卡），用户实际看到的路径就是切页后这一帧；
        # 这样顺带覆盖 switchTab → renderRail 这条通路（⛔别在隐藏页断言，那是假失败）。
        page.evaluate(u"switchTab('profile')")
        page.wait_for_timeout(1200)
        rail = page.evaluate("""() => {
            const t = document.getElementById('rail-track');
            const pg = document.getElementById('page-profile');
            const mid = t ? t.scrollLeft + t.clientWidth / 2 : 0;
            let focus = -1, midOff = null;
            if (t) for (let i = 0; i < t.children.length; i++) {
              if (/focus/.test(t.children[i].className)) {
                focus = i;
                midOff = Math.round(t.children[i].offsetLeft + t.children[i].offsetWidth / 2 - mid);
              }
            }
            return { kids: t ? t.children.length : -1,
                     active: /active/.test(pg ? pg.className : ''),
                     focus: focus, midOff: midOff,
                     tip: (document.getElementById('rail-tip') || {}).textContent };
        }""")
        want_focus = [i for i, (n, _m) in enumerate(RANKS) if n == want_rank][0]
        g.ok(rail['active'], u'B7 「我的」页已激活', rail['active'])
        g.ok(rail['kids'] == 10, u'B8 段位卡廊 10 张（切到我的页后）', rail['kids'])
        g.ok(rail['midOff'] is not None and abs(rail['midOff']) <= 1,
             u'B9 当前段位卡精确居中（离中线 |Δ| ≤ 1）', rail['midOff'])
        g.ok(rail['focus'] == want_focus,
             u'B10 居中卡索引 = %d（%s）' % (want_focus, want_rank), rail['focus'])
        g.ok(bool(rail['tip']) and u'当前段位' in (rail['tip'] or u''),
             u'B11 卡廊 tip 标注当前段位', rail['tip'])

        # C 写入通道健康（保护模式没被误触发 —— 否则所有记录都会静默不落盘）
        wrote = page.evaluate("""() => {
            const before = JSON.parse(localStorage.getItem('jianpan_v2') || '{}');
            state.coins = (before.coins || 0) + 777;
            saveState();
            const after = JSON.parse(localStorage.getItem('jianpan_v2') || '{}');
            return { before: before.coins, after: after.coins,
                     diet: (after.diet || []).length, avLen: after.user && after.user.avatar ? after.user.avatar.length : 0 };
        }""")
        g.ok(wrote['after'] == (wrote['before'] or 0) + 777,
             u'C1 改一个值能真的落盘（保护模式未误触发）',
             u'%s→%s' % (wrote['before'], wrote['after']))
        g.ok(wrote['diet'] == want_diet and wrote['avLen'] > 1000,
             u'C2 落盘时归档字段未被连带破坏', u'diet=%s av=%s' % (wrote['diet'], wrote['avLen']))

        # C3 零 console error（loadState 的 [存档] 报错会落在这里）
        real_errs = [e for e in console_errs if u'favicon' not in e.lower()]
        g.ok(not real_errs, u'C3 控制台零错误（含存档层）', u'%d 条' % len(real_errs))
        for e in real_errs[:8]:
            p(u'        %s' % e[:200])

        ctx.close()
        b.close()
    srv.shutdown()

    rc = g.report()
    p(u'')
    p(u'RESULT=%s' % (u'OK' if rc == 0 else u'FAIL'))
    io.open(OUT, u'w', encoding=u'utf-8', newline=u'').write(u'\n'.join(log))
    return rc


if __name__ == u'__main__':
    sys.exit(main())
