# -*- coding: utf-8 -*-
"""把 mock 数据注入真实 index.html，生成可直接截图的 demo.html"""
import json, os, io

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

with open(os.path.join(ROOT, 'index.html'), encoding='utf-8') as f:
    html = f.read()
with open(os.path.join(HERE, 'mock.json'), encoding='utf-8') as f:
    mock = json.load(f)['state']

SCALARS = ['limitUpCount', 'limitUpStreak', 'lastLimitUpDate', 'streakDays', 'maxStreak',
           'lastRecordDate', 'everBroke', 'maxOverage', 'coins', 'exp', 'coinsEarnedTotal',
           'totalDraws', 'cards', 'collectRewards', 'ach', 'foodFreq', 'usuals',
           'usualsHidden', 'usualsGuideSeen', 'celebFired', 'gapToday', 'coinToday',
           'coinDate', 'lastDate']

payload = {
    'user': mock['user'], 'body': mock['body'],
    'diet': mock['diet'], 'exercise': mock['exercise'], 'weightLog': mock['weightLog'],
    'scalars': {k: mock[k] for k in SCALARS if k in mock}
}

# 完整 state：让 App 从启动那一刻起就是案例数据（避免与 App 自身初始化抢写）
full_state = {}
for k, v in mock.items():
    full_state[k] = v
js_obj = json.dumps(payload, ensure_ascii=False)
js_state = json.dumps(full_state, ensure_ascii=False)

inject = """
<script>
/* ==== DEMO INJECTOR（宣传图专用，不进生产） ==== */
(function () {
  var MOCK = __PAYLOAD__;
  function fail(e) {
    var d = document.createElement('pre');
    d.style.cssText = 'color:#ff5c5c;background:#000;padding:16px;position:absolute;z-index:99999;top:0;left:0;font-size:12px;white-space:pre-wrap;max-width:430px';
    d.textContent = 'INJECT FAIL: ' + e.message + '\\n' + (e.stack || '');
    document.body.appendChild(d);
  }
  try {
    /* state 是主脚本顶层的 let，同一全局词法作用域，这里能直接赋值 */
    state.user = Object.assign(state.user || {}, MOCK.user);
    state.body = Object.assign(state.body || {}, MOCK.body);
    state.diet = MOCK.diet || [];
    state.exercise = MOCK.exercise || [];
    state.weightLog = MOCK.weightLog || [];
    Object.keys(MOCK.scalars || {}).forEach(function (k) { state[k] = MOCK.scalars[k]; });

    /* 把案例数据固化进 localStorage：App 之后任何一次 loadState 都只会读到这个版本
       （file:// 域残留的旧存档会盖掉 defaultState，这是图鉴显示 0 的根因） */
    try { localStorage.setItem('jianpan_v2', JSON.stringify(state)); } catch (e) {}

    /* 解除 100vh / fixed 限制，方便 headless 截整页 */
    var app = document.querySelector('.app');
    if (app) { app.style.height = 'auto'; app.style.maxWidth = '430px'; }
    var scr = document.querySelector('.screen');
    if (scr) { scr.style.overflow = 'visible'; scr.style.flex = 'none'; }
    document.querySelectorAll('*').forEach(function (el) {
      try { if (getComputedStyle(el).position === 'fixed') el.style.position = 'static'; } catch (e) {}
    });
    document.documentElement.style.background = '#0a0e1a';
    document.body.style.background = '#0a0e1a';

    /* 宣传图清场：隐藏「重置」入口，替换默认用户名 */
    document.querySelectorAll('*').forEach(function (el) {
      var t = (el.textContent || '').trim();
      if (t === '重置' && el.children.length <= 2) { el.style.display = 'none'; return; }
      if (t === '调试' && el.children.length <= 2) { el.style.display = 'none'; return; }
      if (!el.children.length && /Workout\d*/.test(t)) el.textContent = '健交所 · 坚持 96 天';
    });

    var m = (location.search || '').match(/p=([a-z]+)/);
    var page = m ? m[1] : 'market';
    if (typeof switchTab === 'function') switchTab(page);
    if (typeof render === 'function') render();
    if (typeof switchTab === 'function') switchTab(page);
  } catch (e) { fail(e); }
})();
</script>
</body>"""

inject = inject.replace('__PAYLOAD__', js_obj)
if '</body>' not in html:
    raise SystemExit('index.html 里找不到 </body>')
out = html.replace('</body>', inject, 1)

# 把 defaultState() 换成案例数据 —— 这是让 coins / cards 等字段生效的关键
import re
pattern = re.compile(r'function defaultState\(\)\s*\{[\s\S]*?\n\}')
new_fn = 'function defaultState() { return Object.assign({}, ' + js_state + '); }'
out, nsub = pattern.subn(new_fn, out, count=1)
print('defaultState 替换:', nsub)
if nsub != 1:
    raise SystemExit('defaultState 替换失败，请检查 index.html')

dst = os.path.join(ROOT, '_demo.html')
with open(dst, 'w', encoding='utf-8') as f:
    f.write(out)
print('demo.html ok  %.1f KB  -> %s' % (os.path.getsize(dst) / 1024.0, dst))
print('（必须放在仓库根目录：js/ 与 data/ 是相对路径，放子目录会 404 导致 BMR 退回默认值 1500）')
print('diet=%d ex=%d weightLog=%d' % (len(mock['diet']), len(mock['exercise']), len(mock['weightLog'])))
