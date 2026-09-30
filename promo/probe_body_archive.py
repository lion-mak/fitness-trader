# -*- coding: utf-8 -*-
"""probe_body_archive.py —— 「身体档案搬进子页」的运行时验收（v2.7.67）

为什么需要它：这一轮是**结构性搬移**，而搬移最典型的错法是「复制」而不是「搬走」：
  把 8 个字段既留在我的页、又加到子页 ⇒ **id 出现两份** ⇒ `getElementById` 只返回第一个
  ⇒ `render()` 灌的是旧那份、`saveProfile()` 读的也是旧那份，子页里那份**永远不回写**。
  而这个错在语法检查、标签配平、肉眼扫源码上**全都看不出来**（页面正常渲染、也不报错）。

所以判据的核心不是「子页有没有字段」，而是 **每个 id 全文档只出现一次** + 子页那份**真的被灌了值**
+ 在子页改的值**真的进了 state**（三条合起来才能排除「两份」）。

⚠️ 与 e2e_test.py / probe_feedback.py 同款：写 `_probe_body_archive.html` 副本 + 独立 profile 跑，
   不碰真实存档。
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
OUT = os.path.join(ROOT, '_probe_body_archive.html')
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
# ⚠️ 名字必须落在 .gitignore 的 `promo/_edgeprofile*/` 规则里（沿用 e2e_test / probe_feedback 前缀）
PROFILE = os.path.join(ROOT, 'promo', '_edgeprofile_body')

# 8 个可编辑字段（值 → 子页里应有的形态：select 用 value，input 用 value）
FIELDS = ['f-gender', 'f-age', 'f-height', 'f-weight', 'f-bf', 'f-rhr', 'f-act', 'f-target']

INJECT = r"""
<script>
window.addEventListener('load', function () {
  var out = {};
  try {
    /* ---- ① 初始：App 启动落在**行情页**（不是我的页）⇒ 先切到我的页，
           否则这条断言测的是「启动页」，而不是「我的页」。
           ⚠️ 第一版就是在这里踩空的：假定了启动在我的页。 */
    switchTab('profile');
    out.profileActive0 = document.getElementById('page-profile').classList.contains('active');
    out.archiveActive0 = document.getElementById('page-body-archive').classList.contains('active');

    /* ---- ② 我的页的只读摘要必须已渲染 ---- */
    var viz = document.getElementById('body-viz');
    out.vizHTML = viz ? viz.innerHTML.length : -1;
    out.vizHasFig = !!(viz && viz.querySelector('img.body-fig'));
    /* ⚠️ 图片 404 时 renderBodyViz() 的 onerror 会换成 bodySilhouette() 的兜底 SVG ——
       那同样是「渲染成功」，所以判据是「img 或 svg」，不是只认 img。 */
    out.vizHasSvg = !!(viz && viz.querySelector('svg'));
    out.vstatCount = document.querySelectorAll('#viz-stats .vstat').length;
    out.vstatTexts = Array.prototype.map.call(
      document.querySelectorAll('#viz-stats .vstat'),
      function (e) { return e.textContent; }).join('|');

    /* ---- ③ 我的页卡片里**不该**再有编辑字段 / BMR 盒 / 上传按钮 ---- */
    var card = document.getElementById('body-card');
    out.cardHasEditFields = !!(card && card.querySelector('.edit-fields'));
    out.cardHasBmrBox = !!(card && card.querySelector('#bmr-box'));
    out.cardBtnTexts = Array.prototype.map.call(card ? card.querySelectorAll('button') : [],
      function (b) { return b.textContent; }).join('|');

    /* ---- ④ 进子页 ---- */
    showBodyArchive();
    out.profileActive1 = document.getElementById('page-profile').classList.contains('active');
    out.archiveActive1 = document.getElementById('page-body-archive').classList.contains('active');
    out.screenScrollTop = document.getElementById('screen').scrollTop;
    var onTab = document.querySelector('.tabbar > div.on');
    out.tabbarOnAfterArchive = onTab ? onTab.getAttribute('data-tab') : '(无高亮项)';

    /* ---- ⑤ 子页里的字段必须真被 render() 灌了值（不是空壳） ---- */
    out.fieldVals = {};
    __FIELDS__.forEach(function (id) {
      var el = document.getElementById(id);
      out.fieldVals[id] = el ? String(el.value) : '(无此元素)';
    });
    out.stateUser = {
      gender: state.user.gender, age: state.user.age, height: state.user.height,
      weight: state.user.weight, bodyFat: state.user.bodyFat,
      restingHr: state.user.restingHr, activity: state.user.activity, target: state.user.target
    };

    /* ---- ⑥ 子页的 BMR/TDEE 盒已渲染 ---- */
    var bb = document.getElementById('bmr-box');
    out.bmrHTML = bb ? bb.innerHTML.length : -1;
    out.bmrText = bb ? bb.textContent : '';
    out.bmrCellCount = bb ? bb.querySelectorAll('.bmr-cell').length : 0;

    /* ---- ⑦ 未上传就返回：字段草稿要保留（backFromBodyArchive 故意不调 render） ---- */
    var fw = document.getElementById('f-weight');
    fw.value = '66.6';
    backFromBodyArchive();
    out.profileActive2 = document.getElementById('page-profile').classList.contains('active');
    out.draftKept = document.getElementById('f-weight').value;   /* 期望 66.6（没被 render 擦回） */
    out.stateWeightAfterDraft = state.user.weight;              /* 期望仍是旧值（草稿没进 state） */
    /* 我的页摘要读的是 state ⇒ 不该被草稿带偏 */
    out.vstatAfterDraft = Array.prototype.map.call(
      document.querySelectorAll('#viz-stats .vstat'),
      function (e) { return e.textContent; }).join('|');

    /* ---- ⑧ 真上传：改值 → saveProfile() ⇒ state 更新 + 结果卡 + 跳行情 ---- */
    showBodyArchive();
    document.getElementById('f-weight').value = '66.6';
    saveProfile();
    out.stateWeightAfterSave = state.user.weight;
    out.curTabAfterSave = (typeof curTab !== 'undefined') ? curTab : '(未知)';
    var mask = document.getElementById('bc-mask');
    out.bcShown = !!(mask && mask.classList.contains('show'));
    out.bcBmr = (document.getElementById('bc-v') || {}).textContent || '';

    /* ---- ⑨ 保存后重进子页，字段应反映**新** state（证明灌的是活值） ---- */
    closeBcCard();
    showBodyArchive();
    out.weightAfterReenter = document.getElementById('f-weight').value;
    out.vstatAfterSave = Array.prototype.map.call(
      document.querySelectorAll('#viz-stats .vstat'),
      function (e) { return e.textContent; }).join('|');
  } catch (e) {
    out.ok = false;
    out.err = String((e && e.message) || e) + ' @ ' + String((e && e.stack) || '').split('\n')[1];
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

    # ---------- A 静态（成本低，先查） ----------
    print('=' * 72)
    print('A 静态 —— 源码层面')
    print('=' * 72)

    # 我的页菜单：文案与入口
    m_menu = re.search(r'<div class="n">([^<]*)</div>\s*<div class="v" id="p-card-count"', html)
    chk('菜单第二项文案 = 藏品图鉴', bool(m_menu) and m_menu.group(1).strip() == '藏品图鉴',
        m_menu.group(1).strip() if m_menu else '(抽不到)')
    chk('「涨停抽卡 · 图鉴」已不在我的页菜单', '涨停抽卡 · 图鉴' not in html)
    chk('菜单第三项 onclick = showBodyArchive()',
        bool(re.search(r'<div class="menu-item" onclick="showBodyArchive\(\)"', html)))
    chk('我的页菜单不再有 scrollToProfile() 调用',
        not re.search(r'onclick="scrollToProfile\(\)"', html))

    # 我的页卡片：该留的留、该走的走
    m_card = re.search(r'<div class="card" id="body-card".*?\n      </div>', html, re.S)
    card = m_card.group(0) if m_card else ''
    chk('#body-card 抽到了（抽不到说明抽法过时）', bool(card), len(card))
    chk('#body-card 仍有人形图 #body-viz', 'id="body-viz"' in card)
    chk('#body-card 仍有四项资料 #viz-stats', 'id="viz-stats"' in card)
    chk('#body-card 已无 .edit-fields', 'edit-fields' not in card)
    chk('#body-card 已无 #bmr-box', 'bmr-box' not in card)
    chk('#body-card 的按钮改为进子页（不再是 saveProfile）',
        'showBodyArchive()' in card and 'saveProfile()' not in card)

    # 子页：该有的有
    m_arc = re.search(r'<section class="page" id="page-body-archive">.*?</section>', html, re.S)
    arc = m_arc.group(0) if m_arc else ''
    chk('#page-body-archive 子页存在', bool(arc), len(arc))
    chk('子页有 .edit-fields', 'edit-fields' in arc)
    chk('子页有 #bmr-box', 'id="bmr-box"' in arc)
    chk('子页有上传按钮（saveProfile）', 'onclick="saveProfile()"' in arc and '上传档案数据' in arc)
    chk('子页有返回（backFromBodyArchive）', 'backFromBodyArchive()' in arc)
    chk('两个切换函数都定义了',
        bool(re.search(r'function showBodyArchive\(\)', html)) and
        bool(re.search(r'function backFromBodyArchive\(\)', html)))

    # 🔴 核心判据：id 全文档唯一（防「复制」而非「搬走」）
    print('')
    print('  -- id 唯一性（搬移类改动的头号坑）--')
    for fid in FIELDS + ['bmr-box', 'body-viz', 'viz-stats', 'body-card']:
        n = len(re.findall(r'id="' + re.escape(fid) + r'"', html))
        chk('id="%s" 全文档出现 1 次' % fid, n == 1, '出现 %d 次' % n)

    # ---------- B 运行时 ----------
    # ⚠️ 用 `__FIELDS__` 占位再替换（不用 % 格式化：INJECT 里有 CSS 的 `%` 会撞车）。
    inject = INJECT.replace('__FIELDS__', json.dumps(FIELDS))
    io.open(OUT, 'w', encoding='utf-8', newline='').write(html.replace('</body>', inject + '</body>'))
    cmd = [EDGE, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
           '--virtual-time-budget=8000', '--user-data-dir=' + PROFILE, '--dump-dom',
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
    print('B 运行时 —— 我的页：只读摘要')
    print('=' * 72)
    chk('初始在我的页（#page-profile active）', r['profileActive0'] is True)
    chk('初始子页不在台前', r['archiveActive0'] is False)
    chk('人形图已渲染（#body-viz 有内容）', r['vizHTML'] > 0, '%d 字符' % r['vizHTML'])
    chk('人形图已渲染（img.body-fig 或兜底 SVG）', r['vizHasFig'] or r['vizHasSvg'],
        'img=%s svg=%s' % (r['vizHasFig'], r['vizHasSvg']))
    chk('四项资料已渲染（4 个 .vstat）', r['vstatCount'] == 4, r['vstatCount'])
    chk('四项资料内容是「值+标签」形态', '岁' in r['vstatTexts'] and 'kg' in r['vstatTexts'],
        r['vstatTexts'][:80])
    chk('我的页卡片里没有 .edit-fields', r['cardHasEditFields'] is False)
    chk('我的页卡片里没有 #bmr-box', r['cardHasBmrBox'] is False)
    chk('我的页卡片按钮 = 编辑详细数据', r['cardBtnTexts'] == '编辑详细数据', r['cardBtnTexts'])

    print('')
    print('=' * 72)
    print('C 运行时 —— 子页：可编辑数据 + BMR')
    print('=' * 72)
    chk('showBodyArchive() 切到子页', r['archiveActive1'] is True)
    chk('切页后我的页不再 active', r['profileActive1'] is False)
    chk('切页会回顶（scrollTop = 0）', r['screenScrollTop'] == 0, r['screenScrollTop'])
    # 子页不在 switchTab() 的 tabs 白名单里 ⇒ 走 else 分支点亮 profile：用户视角「子页仍属于我的」
    chk('进子页后底部栏仍高亮「我的」', r['tabbarOnAfterArchive'] == 'profile', r['tabbarOnAfterArchive'])
    su = r['stateUser']
    fv = r['fieldVals']
    chk('性别字段 = state.user.gender', fv['f-gender'] == str(su['gender']), '%s vs %s' % (fv['f-gender'], su['gender']))
    chk('年龄字段 = state.user.age', fv['f-age'] == str(su['age']), '%s vs %s' % (fv['f-age'], su['age']))
    chk('身高字段 = state.user.height', fv['f-height'] == str(su['height']), '%s vs %s' % (fv['f-height'], su['height']))
    chk('体重字段 = state.user.weight', fv['f-weight'] == str(su['weight']), '%s vs %s' % (fv['f-weight'], su['weight']))
    chk('活动水平字段 = state.user.activity', fv['f-act'] == str(su['activity']),
        '%s vs %s' % (fv['f-act'], su['activity']))
    chk('目标缺口字段 = state.user.target', fv['f-target'] == str(su['target']),
        '%s vs %s' % (fv['f-target'], su['target']))
    chk('体脂率空值 → 字段为空串（不是 "null"/"undefined"）',
        fv['f-bf'] == '' or fv['f-bf'] == str(su['bodyFat']), repr(fv['f-bf']))
    chk('静息心率空值 → 字段为空串（不是 "null"/"undefined"）',
        fv['f-rhr'] == '' or fv['f-rhr'] == str(su['restingHr']), repr(fv['f-rhr']))
    chk('子页 BMR/TDEE 盒已渲染', r['bmrHTML'] > 0, '%d 字符' % r['bmrHTML'])
    chk('盒里两个 cell（BMR + TDEE）', r['bmrCellCount'] == 2, r['bmrCellCount'])
    chk('BMR 数值不是 0/占位', bool(re.search(r'\b[1-9]\d{2,}\b', r['bmrText'])),
        r['bmrText'][:60])

    print('')
    print('=' * 72)
    print('D 运行时 —— 草稿 vs 保存（搬移后最容易出的语义差）')
    print('=' * 72)
    chk('未上传就返回 → 回到我的页', r['profileActive2'] is True)
    chk('⭐ 草稿保留（backFromBodyArchive 没调 render 擦回旧值）',
        r['draftKept'] == '66.6', r['draftKept'])
    chk('草稿没进 state（我的页摘要不受未保存编辑影响）',
        str(r['stateWeightAfterDraft']) != '66.6', r['stateWeightAfterDraft'])
    chk('摘要仍显示旧体重', r['vstatAfterDraft'] == r['vstatTexts'], r['vstatAfterDraft'][:80])
    chk('上传后 state.user.weight = 66.6', str(r['stateWeightAfterSave']) == '66.6',
        r['stateWeightAfterSave'])
    chk('上传后跳到行情页（原行为不变）', r['curTabAfterSave'] == 'market', r['curTabAfterSave'])
    chk('上传后结果卡弹出', r['bcShown'] is True)
    chk('结果卡带 BMR 数值', 'kcal/天' in r['bcBmr'], r['bcBmr'])
    chk('重进子页 → 体重字段 = 新值 66.6（灌的是活 state）',
        r['weightAfterReenter'] == '66.6', r['weightAfterReenter'])
    chk('重进后我的页摘要已更新到 66.6 kg', '66.6 kg' in r['vstatAfterSave'], r['vstatAfterSave'][:80])

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
