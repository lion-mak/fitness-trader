# -*- coding: utf-8 -*-
"""pwa_gate_state.py —— PWA 存档读写闸（冷启动安全闸）

由来：2026-09-25 真事故 —— `loadState()` 走的 `applyCurveUpgrade()` 读了声明在其调用点
**之后**的 `const CURVE_VER`，在 TDZ 里抛 ReferenceError，被 `catch(e) {}` 静默吞掉 ⇒
返回 `defaultState()` 空档 ⇒ `render()` 末尾无条件 `saveState()` 把空档写回
⇒ 用户存档被永久覆盖（症状：数据全清零、头像退回内联 SVG 占位人形、体重 K 线无历史）。
整条链上没有任何一处会报错、没有任何测试会变红 —— 所以要有这道闸。

闸做五件事（A–C 是「正向必须绿」，S 是「静态必须绿」，D 是「负控必须红」，见 negctl_pwa_state.py）：
  S 静态闸（不开浏览器，3 秒内出结果）
    S1 TDZ 静态扫描：`let state = loadState()` 之后声明的顶层 const/let，若被 load 链路
       （loadState / applyCurveUpgrade / defaultState / seedBodyLog）引用 ⇒ 必然 TDZ ⇒ FAIL。
       这条就是本次事故的机器化版本（⛔比人眼可靠）。
    S2 空 `catch` 计数棘轮：空 catch = 静默失败通道。基线值钉死，**新增即 FAIL**，逼你写一句日志。
    S3 注释提前闭合：`*/` 同一行后面还有非空白内容 ⇒ 注释被提前关掉、后面的字被当代码解析
       （2026-09-24 WXSS 整包白屏就是这个）。HTML/JS 同源风险，一并拦。
    S4 存档安全网存在性：四道防线（保护模式 / 快照环 / 缩水闸 / 空档哨兵 + 告警条）
       的关键符号一个都不能少 —— 防止后来者「顺手清理」把它删掉。
  A 存档存活 冷启动后存储里的存档仍在，且关键字段与预期等价（不是被空档覆盖）+ 快照已生成
  B 页面真读到了 页面上显示的累计数 / 段位 / 持仓天数与存档一致（防「读进去了但没用上」）
  C 写入通道健康 保护模式没被误触发（改一个值能真的落盘）+ 空档哨兵真的能拦 + 零 console error
  D 负控 见 negctl_pwa_state.py：把 CURVE_VER 挪回调用点之后 ⇒ 本闸必须变红

用法：python promo/pwa_gate_state.py        # 退出码 0=绿 1=红
"""
import io
import os
import re
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


LOAD_PATH_FNS = (u'loadState', u'applyCurveUpgrade', u'defaultState', u'seedBodyLog')

# 空 `catch` 计数棘轮：静默失败通道的总数。只许减不许增 ——
# 确实需要忽略异常时必须写一句日志/注释说明理由，而不是留个空壳。
EMPTY_CATCH_BASELINE = 22         # 2026-09-25 实测值。只许减不许增 —— 新增空 catch 会让闸变红。

# 存档安全网的「一个都不能少」清单（少一个就直接红：这些都是拿真数据换来的）
SAFETY_SYMBOLS = (
    (u'__loadFailed', u'读失败保护模式（loadState/saveState）'),
    (u'SNAP_PREFIX', u'自动快照环'),
    (u'function takeSnapshot', u'快照写入'),
    (u'function restoreLatestSnapshot', u'从快照恢复'),
    (u'function showSaveGuard', u'可见告警条'),
    (u'function downloadRescue', u'原始存档下载（自救出口）'),
    (u'缩水闸拦截', u'启动期缩水闸'),
    (u'空档哨兵拦截', u'永久空档哨兵'),
)


def _blank_js(src):
    """把注释与字符串**按字节长度原样打白**（保留换行）⇒ 括号配平与标识符匹配都不受注释/字符串干扰，
    且返回串与原串**等长**，偏移可直接互查。"""
    out = []
    i = 0
    n = len(src)
    st = 0                      # 0=代码 1=行注释 2=块注释 3=' 4=" 5=`
    while i < n:
        c = src[i]
        nx = src[i + 1] if i + 1 < n else u''
        if st == 0:
            if c == u'/' and nx == u'/':
                st = 1; out.append(u'  '); i += 2; continue
            if c == u'/' and nx == u'*':
                st = 2; out.append(u'  '); i += 2; continue
            if c == u"'":
                st = 3; out.append(u' '); i += 1; continue
            if c == u'"':
                st = 4; out.append(u' '); i += 1; continue
            if c == u'`':
                st = 5; out.append(u' '); i += 1; continue
            out.append(c); i += 1; continue
        if st == 1:
            out.append(u'\n' if c == u'\n' else u' ')
            if c == u'\n':
                st = 0
            i += 1; continue
        if st == 2:
            if c == u'*' and nx == u'/':
                st = 0; out.append(u'  '); i += 2; continue
            out.append(u'\n' if c == u'\n' else u' ')
            i += 1; continue
        if c == u'\\':
            out.append(u'  '); i += 2; continue
        if (st == 3 and c == u"'") or (st == 4 and c == u'"') or (st == 5 and c == u'`'):
            st = 0; out.append(u' '); i += 1; continue
        out.append(u'\n' if c == u'\n' else u' ')
        i += 1
    return u''.join(out)


def _fn_body(cleaned, name):
    """从 `function NAME(` 起按大括号配平取出函数体（cleaned 已打白注释/字符串）。"""
    m = re.search(r'function\s+' + re.escape(name) + r'\s*\(', cleaned)
    if not m:
        return None
    i = cleaned.find(u'{', m.end())
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(cleaned)):
        if cleaned[j] == u'{':
            depth += 1
        elif cleaned[j] == u'}':
            depth -= 1
            if depth == 0:
                return cleaned[i:j + 1]
    return None


def static_checks(g, p, src):
    """S 段：不需要浏览器。写完代码 3 秒内就能知道有没有踩这两个白屏级坑。"""
    cleaned = _blank_js(src)
    lines = src.split(u'\n')
    clines = cleaned.split(u'\n')

    # ---- S1 TDZ 静态扫描 ----
    call_ln = None
    for i, l in enumerate(clines):
        if u'let state = loadState();' in l:
            call_ln = i + 1
            break
    g.ok(call_ln is not None, u'S0 找到 `let state = loadState();`', call_ln)
    later = []                        # 调用点之后声明的顶层 const/let：(name, line)
    if call_ln:
        for i in range(call_ln, len(clines)):
            m = re.match(r'^(?:const|let)\s+([A-Za-z_$][\w$]*)', clines[i])
            if m:
                later.append((m.group(1), i + 1))
    hits = []
    for name, ln in later:
        for fn in LOAD_PATH_FNS:
            body = _fn_body(cleaned, fn)
            if not body:
                continue
            if not re.search(r'\b' + re.escape(name) + r'\b', body):
                continue
            # 函数体自己声明的同名局部变量 ⇒ 不是 TDZ，跳过（降误报）
            if re.search(r'(?:const|let|var|function)\s+' + re.escape(name) + r'\b', body):
                continue
            if re.search(r'(?:\(|,)\s*' + re.escape(name) + r'\s*(?:[,)]|=[^=])', body):
                continue
            hits.append(u'%s（声明在 L%d，被 %s() 引用）' % (name, ln, fn))
    g.ok(not hits, u'S1 TDZ 静态扫描：load 链路没有引用「后置声明」的 const/let',
         u'；'.join(hits[:5]) if hits else u'%d 个后置声明已扫' % len(later))
    if hits:
        for h in hits[:8]:
            p(u'        ⛔ %s' % h)

    # ---- S2 空 catch 棘轮 ----
    n_empty = len(re.findall(r'catch\s*\(\s*[\w$]*\s*\)\s*\{\s*\}', cleaned))
    if EMPTY_CATCH_BASELINE is None:
        g.ok(True, u'S2 空 catch 实测 %d 处（基线未设，请把该值填进 EMPTY_CATCH_BASELINE）' % n_empty)
    else:
        g.ok(n_empty <= EMPTY_CATCH_BASELINE,
             u'S2 空 catch 未新增（%d ≤ 基线 %d）' % (n_empty, EMPTY_CATCH_BASELINE),
             u'实测 %d' % n_empty)

    # ---- S3 注释提前闭合 ----
    bad_c = []
    for i, l in enumerate(lines, 1):
        for m in re.finditer(re.escape(u'*/'), l):
            if l[m.end():].strip():
                bad_c.append(u'L%d' % i)
                break
    g.ok(not bad_c, u'S3 无「星号紧跟斜杠后还有内容」的注释提前闭合', u'、'.join(bad_c[:8]))

    # ---- S4 安全网符号齐全 ----
    miss = [d for sym, d in SAFETY_SYMBOLS if sym not in src]
    g.ok(not miss, u'S4 存档安全网 %d 项齐全（保护模式/快照/缩水闸/空档哨兵/告警条）' % len(SAFETY_SYMBOLS),
         u'缺少：' + u'、'.join(miss))
    p()


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

    # ---- S 段：静态闸（不开浏览器）----
    src = io.open(os.path.join(ROOT, u'index.html'), encoding=u'utf-8').read()
    p(u'## S 静态闸')
    static_checks(g, p, src)

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
                ver: (document.querySelector('meta[name=app-version]') || {}).content,
                /* 新增防线（v2.7.62）的三项可观测状态 */
                snaps: (function () {
                    const out = [];
                    for (let i = 0; i < localStorage.length; i++) {
                        const k = localStorage.key(i);
                        if (k && k.indexOf('jianpan_v2_snap_') === 0) {
                            const v = localStorage.getItem(k) || '';
                            let d = -1;
                            try { d = (JSON.parse(v).diet || []).length; } catch (e) { d = -1; }
                            out.push({ key: k, len: v.length, diet: d });
                        }
                    }
                    return out;
                })(),
                guardBanner: !!document.getElementById('save-guard'),
                loadFailed: (typeof __loadFailed !== 'undefined') ? __loadFailed : null,
                guardTripped: (typeof __guardTripped !== 'undefined') ? __guardTripped : null,
                snapStatus: g('snap-status')
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
        # A7-A9 自动快照环（新防线）：被写坏了要有回滚源
        snaps = snap['snaps']
        g.ok(1 <= len(snaps) <= 5, u'A7 自动快照已生成且 ≤5 份', u'%d 份' % len(snaps))
        g.ok(bool(snaps) and all(s['len'] > 10000 for s in snaps),
             u'A8 每份快照都不是空档（>10KB）',
             u'最小 %d 字符' % (min([s['len'] for s in snaps]) if snaps else 0))
        g.ok(any(s['diet'] == want_diet for s in snaps),
             u'A9 至少一份快照含 %d 条饮食记录（可用来回滚）' % want_diet,
             u'%s' % [s['diet'] for s in snaps])
        g.ok(u'自动快照' in (snap['snapStatus'] or u''),
             u'A10「我的」页显示快照状态行', snap['snapStatus'])

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

        # ---- D 段：体重 K 线均线 MA7/MA14/MA30（MA14 = v2.7.62 从小程序侧回灌）----
        # ⛔ 期望值独立现算（载荷里最后 N 根收盘均值），不从页面代码里抄。
        page.evaluate(u"switchTab('market')")
        page.wait_for_timeout(900)
        kl = page.evaluate("""() => {
            const g = (id) => { const el = document.getElementById(id); return el ? el.textContent : null; };
            const chart = document.getElementById('kline');
            let tipHTML = '';
            if (chart) {
                const r = chart.getBoundingClientRect();
                const ev = new PointerEvent('pointermove', {
                    clientX: r.left + r.width * 0.6, clientY: r.top + r.height * 0.5, bubbles: true });
                chart.dispatchEvent(ev);
                const t = document.getElementById('kline-tip');
                tipHTML = t ? t.innerHTML : '';
            }
            return { ma7: g('ma7-lab'), ma14: g('ma14-lab'), ma30: g('ma30-lab'),
                     hasMa14Path: !!chart && chart.innerHTML.indexOf('#a78bfa') >= 0,
                     hasMa7Path: !!chart && chart.innerHTML.indexOf('#ffb800') >= 0,
                     tipHTML: tipHTML };
        }""")
        closes = [round(float(p[u'weight']), 1) for p in (seed.get(u'weightLog') or [])]
        p(u'  体重 K 线：%s / %s / %s（%d 根收盘）' % (kl['ma7'], kl['ma14'], kl['ma30'], len(closes)))

        def ma_expect(period, arr):
            if len(arr) < period:
                return u'--'
            d = arr[-period:] if len(arr) >= period else arr
            return u'%.2f' % (sum(d) / len(d))

        g.ok(kl['ma14'] == u'● MA14 ' + ma_expect(14, closes),
             u'D1 MA14 图例 = %s（独立现算：末 14 根收盘均值）' % ma_expect(14, closes), kl['ma14'])
        g.ok(kl['ma7'] == u'● MA7 ' + ma_expect(7, closes),
             u'D2 MA7 图例 = %s（顺带钉住原有均线没被改坏）' % ma_expect(7, closes), kl['ma7'])
        g.ok(kl['ma30'] == u'● MA30 ' + ma_expect(30, closes),
             u'D3 MA30 图例 = %s' % ma_expect(30, closes), kl['ma30'])
        g.ok(kl['hasMa14Path'], u'D4 MA14 真的画上了（SVG 里有 #a78bfa 的 path）')
        g.ok(kl['hasMa7Path'], u'D5 MA7 仍画着（没被 MA14 顶掉）')
        g.ok(u'MA14' in (kl['tipHTML'] or u''),
             u'D6 悬浮标签里有 MA14 行', (kl['tipHTML'] or u'')[:60])

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
        g.ok(snap['loadFailed'] is False, u'C3 保护模式未触发（__loadFailed=false）', snap['loadFailed'])
        g.ok(snap['guardTripped'] is False and not snap['guardBanner'],
             u'C4 正常冷启动不弹告警条', u'tripped=%s banner=%s' % (snap['guardTripped'], snap['guardBanner']))

        # C5-C7 空档哨兵**真的能拦** —— 这是「防复发」的核心证据，不是装饰：
        # 把内存里的 diet 清空再存（= 模拟 state 被重置成空档），存储必须逐字节不动 + 弹告警条。
        trip = page.evaluate("""() => {
            const before = localStorage.getItem('jianpan_v2');
            const bak = state.diet;
            state.diet = [];
            saveState();
            const after = localStorage.getItem('jianpan_v2');
            const banner = !!document.getElementById('save-guard');
            const tripped = (typeof __guardTripped !== 'undefined') ? __guardTripped : null;
            let kept = -1;
            try { kept = (JSON.parse(after || '{}').diet || []).length; } catch (e) { kept = -1; }
            state.diet = bak;                  // 复原内存，别污染后面的断言
            __guardTripped = false;
            hideSaveGuard();
            return { same: before === after, banner: banner, tripped: tripped, kept: kept };
        }""")
        g.ok(trip['same'], u'C5 空档哨兵：记录被清零时拒绝落盘（存储逐字节未变）', trip['same'])
        g.ok(trip['kept'] == want_diet, u'C6 拦下之后磁盘上仍是 %d 条饮食记录' % want_diet, trip['kept'])
        g.ok(trip['banner'] and trip['tripped'],
             u'C7 拦截时页面弹出告警条（用户看得见，不是只打日志）',
             u'banner=%s tripped=%s' % (trip['banner'], trip['tripped']))

        # C8 零 console error（loadState 的 [存档] 报错会落在这里）。
        # ⛔ 只放行 C5-C7 故意触发的哨兵/告警条那两条，其它一律算失败。
        real_errs = [e for e in console_errs if u'favicon' not in e.lower()
                     and u'空档哨兵拦截' not in e and u'告警条已弹出' not in e]
        g.ok(not real_errs, u'C8 控制台零错误（含存档层）', u'%d 条' % len(real_errs))
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
