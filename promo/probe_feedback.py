# -*- coding: utf-8 -*-
"""probe_feedback.py —— 「操作反馈」的运行时验收（v2.7.66 新增）

为什么需要它：这一轮的改动有两类**静态检查看不出来**：
  ① `saveProfile()` 的 `alert()` → 自建深色结果卡：写出 `showBcCard(...)` 但没显示、
     或显示了关不掉 —— 语法/标签层面全过，`chk_syntax.py` 也是绿的。
  ② 三条浮层的 `top` 改成 `calc(env(safe-area-inset-top, 0px) + Npx)`：
     calc 写错会让整条 `top` 声明失效（退回 `auto`，浮层跑进文档流）—— 静态同样看不出来。

⭐ 顺带解决一个测试基建问题：若 `alert` 还留在路径上，headless 会**挂起**拿不到回传。
   所以脚本先把 `window.alert` 换成记录器 —— 既不会挂起，又把
   「alert 一次都没被调用」直接变成一条断言。

⚠️ 与 e2e_test.py 同款：写一份 `_e2e.html` 副本 + 独立 profile 跑，不碰真实存档。
"""
import base64
import io
import json
import os
import re
import subprocess
import sys

ROOT = r'E:\WorkBuddy\jianpan-ghpages'
SRC = os.path.join(ROOT, 'index.html')
OUT = os.path.join(ROOT, '_probe_feedback.html')
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
# ⚠️ 名字必须落在 .gitignore 的 `promo/_edgeprofile*/` 规则里，否则 headless profile
#    （几十 MB 的缓存）会被 `git add -A` 扫进仓库 —— 用 e2e_test.py 同一前缀。
PROFILE = os.path.join(ROOT, 'promo', '_edgeprofile_fb')

INJECT = r"""
<script>
window.addEventListener('load', function () {
  var out = {};
  try {
    /* 🔴 先把 alert 换成记录器：既防 headless 挂起，又能把「没被调用」变成断言 */
    var alertCalls = [];
    window.alert = function (m) { alertCalls.push(String(m)); };

    /* 成就全置已解锁：把观测隔离到「记录得币 / 体重 / 身体档案」，别混进成就奖励 */
    try { ACHIEVEMENTS.forEach(function (a) { state.ach[a.id] = true; }); } catch (e) {}

    /* ---- ① 记录饮食 ---- */
    state.coinToday = 0; state.coins = 0;
    awardRecordCoins('food');
    var ct = document.getElementById('coin-toast');
    out.coinFood = ct ? ct.textContent : '';
    out.coinFoodShown = !!(ct && ct.classList.contains('show'));

    /* ---- ② 记录运动（另一种 emoji）---- */
    state.coinToday = 0; state.coins = 0;
    awardRecordCoins('ex');
    out.coinEx = ct ? ct.textContent : '';

    /* ---- ③ 已达当日上限 ---- */
    state.coinToday = COIN_DAILY_CAP;
    awardRecordCoins('food');
    out.coinCap = ct ? ct.textContent : '';

    /* ---- ④ 记录体重 → 绿色信息浮层 ---- */
    var kw = document.getElementById('kw-input');
    if (kw) kw.value = '72.8';
    saveQuickWeight();
    var it = document.getElementById('info-toast');
    out.infoWeight = it ? it.textContent : '';

    /* ---- ⑤ 保存身体档案 → 自建深色卡（原来这里是 alert）---- */
    var fw = document.getElementById('f-weight');
    if (fw) fw.value = '70.5';
    saveProfile();
    var mask = document.getElementById('bc-mask');
    out.bcShown = !!(mask && mask.classList.contains('show'));
    var bv = document.getElementById('bc-v');
    var bf = document.getElementById('bc-f');
    out.bcBmr = bv ? bv.textContent : '';
    out.bcFormula = bf ? bf.textContent : '';
    out.bcBtnCount = document.querySelectorAll('#bc-mask .bc-btn').length;
    out.bcBtnTexts = Array.prototype.map.call(
      document.querySelectorAll('#bc-mask .bc-btn'), function (b) { return b.textContent; }).join('|');

    /* 卡片几何要在**隐藏之前**量：display:none 时 computed 全是空 */
    var card = document.querySelector('#bc-mask .bc-card');
    if (card) {
      var cs = getComputedStyle(card);
      out.bcWidth = cs.width;
      out.bcRadius = cs.borderTopLeftRadius;
      out.bcBg = cs.backgroundColor;
    }

    /* ---- ⑥ 关掉卡片 ---- */
    closeBcCard();
    out.bcClosed = !!(mask && !mask.classList.contains('show'));

    /* ---- ⑦ 三条浮层的 top：headless 里 env() 无值 ⇒ 应退化成 18 / 72 / 110 ---- */
    out.tops = {};
    ['coin-toast', 'ach-toast', 'info-toast'].forEach(function (id) {
      var el = document.getElementById(id);
      out.tops[id] = el ? getComputedStyle(el).top : '(无此元素)';
      var p = el ? getComputedStyle(el).position : '';
      out.tops[id + '_pos'] = p;
    });

    out.alertCalls = alertCalls;
  } catch (e) {
    out.ok = false;
    out.err = String((e && e.message) || e);
  }
  document.title = 'RESULT:' + btoa(unescape(encodeURIComponent(JSON.stringify(out))));
});
</script>
"""

ok = True


def chk(name, cond, extra=''):
    global ok
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  -> ' + str(extra)) if extra != '' else ''))
    if not cond:
        ok = False


def main():
    global ok
    html = io.open(SRC, encoding='utf-8').read()

    # ---------- 静态部分（先查，成本低）----------
    print('=' * 72)
    print('A 静态 —— 源码层面')
    print('=' * 72)
    m_sp = re.search(r'function saveProfile\(\)\s*\{(.*?)\n\}', html, re.S)
    body = m_sp.group(1) if m_sp else ''
    chk('saveProfile 函数体抽到了（抽不到说明抽法过时）', bool(body), len(body))
    chk('saveProfile 里不再有 alert(', 'alert(' not in body,
        [l.strip()[:70] for l in body.splitlines() if 'alert(' in l])
    chk('saveProfile 改调 showBcCard(', 'showBcCard(' in body)
    chk('.bc-card 样式已在源文件中（PWA 侧）', bool(re.search(r'\.bc-card\s*\{', html)))
    for tid, n in (('coin-toast', 18), ('ach-toast', 72), ('info-toast', 110)):
        m = re.search(r'#' + tid + r'\s*\{[^}]*?top:calc\(env\(safe-area-inset-top[^)]*\)\s*\+\s*' + str(n) + r'px\)', html)
        chk('#%s 的 top 带 env(safe-area-inset-top) + %dpx' % (tid, n), bool(m))
    chk('coin 文案含 emoji + 今日进度（源文件）',
        bool(re.search(r"emi \+ ' \+' \+ granted \+ ' 健康币 · 今日 '", html)))
    chk('emoji 变量按 kind 分饮食/运动', bool(re.search(r"var emi = isFood \? '🍚' : '🏃'", html)))
    chk('体重文案为 ⚖️ 今日体重（不再是 ✓ 已记录）',
        "toastInfo('⚖️ 今日体重 '" in html and "✓ 已记录今日体重" not in html)

    # ---------- 运行时部分 ----------
    io.open(OUT, 'w', encoding='utf-8', newline='').write(html.replace('</body>', INJECT + '</body>'))
    cmd = [EDGE, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
           '--virtual-time-budget=6000', '--user-data-dir=' + PROFILE, '--dump-dom',
           'file:///' + OUT.replace('\\', '/')]
    p = subprocess.run(cmd, capture_output=True, timeout=180)
    dom = p.stdout.decode('utf-8', 'replace')
    m = re.search(r'RESULT:([A-Za-z0-9+/=]+)', dom)
    if not m:
        print('FAIL  未取到页面回传（DOM 长度 %d，stderr 尾部：%s）'
              % (len(dom), p.stderr.decode('utf-8', 'replace')[-300:]))
        return 1
    r = json.loads(base64.b64decode(m.group(1)).decode('utf-8'))
    if not r.get('ok', True):
        print('FAIL  页面内断言抛错：' + str(r.get('err')))
        return 1

    print('')
    print('=' * 72)
    print('B 运行时 —— 记录饮食/运动/体重')
    print('=' * 72)
    chk('记录饮食：🍚 +N 健康币 · 今日 x/y', '🍚' in r['coinFood'] and '健康币 · 今日' in r['coinFood'],
        r['coinFood'])
    chk('记录饮食：浮层带 show（真的显示出来）', r['coinFoodShown'])
    chk('记录运动：🏃 前缀', '🏃' in r['coinEx'], r['coinEx'])
    chk('达上限：🍚 已记录 · 今日奖励已达上限', '已达上限' in r['coinCap'], r['coinCap'])
    chk('记录体重：⚖️ 今日体重 72.8 kg', r['infoWeight'] == '⚖️ 今日体重 72.8 kg', r['infoWeight'])

    print('')
    print('=' * 72)
    print('C 运行时 —— 身体档案结果卡（替代 alert）')
    print('=' * 72)
    chk('saveProfile 后 #bc-mask 带 show（卡片真的弹出来）', r['bcShown'])
    chk('BMR 数值已写入且单位正确', 'kcal/天' in r['bcBmr'] and re.search(r'\d', r['bcBmr']), r['bcBmr'])
    chk('BMR 数值不是占位 0', bool(re.search(r'\b[1-9]\d{2,}\b', r['bcBmr'])), r['bcBmr'])
    chk('公式文案已写入', r['bcFormula'].startswith('公式：'), r['bcFormula'])
    chk('两个按钮（留在本页 / 去行情看）', r['bcBtnCount'] == 2, r['bcBtnTexts'])
    chk('按钮文案正确', r['bcBtnTexts'] == '留在本页|去行情看', r['bcBtnTexts'])
    chk('卡片尺寸 272px 宽（与小程序 1:1）', r['bcWidth'] == '272px', r['bcWidth'])
    chk('卡片圆角 16px', r['bcRadius'] == '16px', r['bcRadius'])
    chk('卡片底色 = --panel #141b2d', r['bcBg'] == 'rgb(20, 27, 45)', r['bcBg'])
    chk('closeBcCard() 能关掉', r['bcClosed'])
    chk('⭐ 全程 alert 一次都没被调用', len(r['alertCalls']) == 0, r['alertCalls'])

    print('')
    print('=' * 72)
    print('D 运行时 —— 三条浮层的 top（安全区项在 headless 里退化为 0）')
    print('=' * 72)
    for tid, n in (('coin-toast', '18px'), ('ach-toast', '72px'), ('info-toast', '110px')):
        got = r['tops'].get(tid, '')
        chk('#%s top = %s（calc 没写坏）' % (tid, n), got == n, got)
        chk('#%s 仍是 position:fixed' % tid, r['tops'].get(tid + '_pos') == 'fixed',
            r['tops'].get(tid + '_pos'))

    print('')
    print('=' * 72)
    print('RESULT=' + ('OK' if ok else 'FAIL'))
    print('=' * 72)
    try:
        os.remove(OUT)
    except OSError:
        pass
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
