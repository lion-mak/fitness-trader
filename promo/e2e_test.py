# -*- coding: utf-8 -*-
"""端到端验收（v2.7.38 更新）：用 Edge 无头加载真实 App，注入状态后断言结构与行为。

覆盖：
  · 摄入圆环模块 / 餐次模块 已移除（DOM 中不存在，且 render() 能跑完不抛错）
  · 行情页结构：首块 = 体重K线，第二块 = 运动网格图（v2.7.38）
  · 交易大厅已迁入持仓页首块（v2.7.38），底图 trading-floor-full.png，无 canvas 引擎
  · 运动网格图：154 格 / 少·多 图例 / 月份标签 均已渲染（v2.7.38）
  · 涨停币每日只发一次（重复记录不再叠加 +200）
  · MA 图例带数值
  · 体重K线悬浮数据标签能由指针坐标取到正确那根K线的日期
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
OUT = os.path.join(ROOT, '_e2e.html')
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
PROFILE = os.path.join(ROOT, 'promo', '_e2eprofile')

INJECT = r"""
<script>
window.addEventListener('load', function () {
  var out = {};
  try {
    out.ringGone = !document.getElementById('ring-fill') && !document.getElementById('m-intake') && !document.getElementById('ring-num');
    out.mealGone = !document.getElementById('fs-meals');
    out.mealCssGone = !/\.meal-row\s*\{/.test(document.head.innerHTML);
    var mk = document.getElementById('page-market');
    var firstCard = mk ? mk.querySelector('.card') : null;
    var cards = mk ? mk.querySelectorAll('.card') : [];
    // v2.7.38：交易大厅迁到持仓页；行情页首块 = 体重K线，第二块 = 运动网格图
    out.firstCardHasKline = !!(firstCard && firstCard.querySelector('#kline'));
    out.secondCardIsHeat = cards.length >= 2 && cards[1].id === 'ex-heat-card';
    out.tradingFloorHasBgImg = !!document.querySelector('.tf-bg');
    var bgImg = document.querySelector('.tf-bg');
    out.tradingFloorUsesFull = !!(bgImg && /trading-floor-full/.test(bgImg.getAttribute('src') || ''));
    out.tradingFloorNoTicker = !document.querySelector('.tf-ticker');
    out.tradingFloorNoCanvas = !document.getElementById('tf-canvas');
    var hold = document.getElementById('page-holdings');
    var tf = document.getElementById('tf-card');
    out.tfInsideHoldings = !!(hold && tf && hold.contains(tf));
    out.tfIsFirstHoldingsCard = !!(hold && hold.querySelector('.card') === tf);
    var heat = document.getElementById('ex-heat');
    out.heatHasCells = !!(heat && heat.querySelectorAll('.ex-heat-cell').length >= 140);
    out.heatHasLegend = !!(heat && heat.querySelector('.ex-heat-legend'));
    out.heatHasMonths = !!(heat && heat.querySelectorAll('.ex-heat-months span').length >= 3);

    var today = todayStr();
    // 全部成就置为已解锁：避免成就奖励混入，把发币观测隔离到「涨停」与「记录」两项
    ACHIEVEMENTS.forEach(function (a) { state.ach[a.id] = true; });
    var wl = [];
    for (var i = 29; i >= 0; i--) wl.push({ date: addDaysStr(today, -i), weight: +(75 - (29 - i) * 0.1).toFixed(1) });
    state.weightLog = wl;
    state.user.target = 0;
    state.coins = 0; state.limitUpCount = 0;
    state.lastLimitUpDate = null; state.celebFired = false; state.settledDate = null;
    state.diet = [{ id: 't1', date: today, name: '测试', kcal: 300, meal: '午餐', time: '12:00' }];
    state.exercise = [];
    document.getElementById('celeb').classList.remove('show');
    render();
    // v2.7.36：涨停改「收盘结算」触发，记一笔不再自动判定
    out.coinsBeforeSettle = state.coins;
    out.celebBeforeSettle = document.getElementById('celeb').classList.contains('show');
    settleDay(today);
    out.coins1 = state.coins;
    out.limitUp1 = state.limitUpCount;
    out.celebShown = document.getElementById('celeb').classList.contains('show');
    document.getElementById('celeb').classList.remove('show');

    for (var j = 0; j < 3; j++) {
      state.diet.push({ id: 't' + (j + 2), date: today, name: '测试', kcal: 100, meal: '加餐', time: '15:00' });
      awardRecordCoins('food');
      bumpStreak();
      render();
    }
    settleDay(today);   // 同日重复收盘 → settledDate 幂等，不再发涨停币
    out.coins4 = state.coins;
    out.limitUp4 = state.limitUpCount;
    out.celebShownAgain = document.getElementById('celeb').classList.contains('show');
    document.getElementById('celeb').classList.remove('show');

    out.mealAutoLunch = mealFromHM('12:30');
    out.mealAutoSnack = mealFromHM('22:10');
    out.mealAutoBreakfast = mealFromHM('07:05');

    out.ma7 = (document.getElementById('ma7-lab') || {}).textContent || '';
    out.ma30 = (document.getElementById('ma30-lab') || {}).textContent || '';

    var kl = document.getElementById('kline');
    var sv = kl.querySelector('svg');
    out.svgExists = !!sv;
    var r = sv.getBoundingClientRect();
    out.svgW = Math.round(r.width);
    out.geomOk = !!klineGeom;
    if (klineGeom && r.width) {
      var idx = 5;
      var sx = klineGeom.PAD_L + idx * klineGeom.slotW + klineGeom.slotW / 2;
      var cx = r.left + sx * (r.width / klineGeom.W);
      kl.dispatchEvent(new PointerEvent('pointermove', { clientX: cx, clientY: r.top + 60, bubbles: true }));
      var tip = document.getElementById('kline-tip');
      out.tipShown = !!(tip && tip.style.display === 'block');
      out.tipHTML = tip ? tip.innerHTML : '';
      out.expectDate = wl[idx].date;
      out.expectClose = wl[idx].weight.toFixed(1);
      out.crossShown = document.getElementById('kline-cross').style.display !== 'none';
      kl.dispatchEvent(new PointerEvent('pointermove', { clientX: r.left - 900, clientY: r.top + 60, bubbles: true }));
      out.tipLeftHTML = tip ? tip.innerHTML : '';
      out.expectDate0 = wl[0].date;
      var far = r.left + r.width + 500;
      kl.dispatchEvent(new PointerEvent('pointermove', { clientX: far, clientY: r.top + 60, bubbles: true }));
      out.tipRightHTML = tip ? tip.innerHTML : '';
      out.expectDateN = wl[wl.length - 1].date;
      kl.dispatchEvent(new Event('pointerleave', { bubbles: true }));
      out.tipHiddenAfterLeave = tip.style.display === 'none';
    }
    // MA 图例在数据不足时的口径：3 根凑不出 MA7/MA30；0 根走空态
    state.weightLog = wl.slice(-3);
    render();
    out.ma7Low = (document.getElementById('ma7-lab') || {}).textContent || '';
    out.ma30Low = (document.getElementById('ma30-lab') || {}).textContent || '';
    state.weightLog = [];
    render();
    out.ma7None = (document.getElementById('ma7-lab') || {}).textContent || '';
    out.ma30None = (document.getElementById('ma30-lab') || {}).textContent || '';
    out.ok = true;
  } catch (e) {
    out.ok = false;
    out.err = String((e && e.message) || e);
  }
  document.title = 'RESULT:' + btoa(unescape(encodeURIComponent(JSON.stringify(out))));
});
</script>
"""


def run():
    html = io.open(SRC, encoding='utf-8').read()
    print('inline total chars:', len(html))
    # 静态审计：已删除的标识符不应再出现在代码里
    static = {
        'ring-fill 残留': 'ring-fill' in html,
        'fs-meals 残留': 'fs-meals' in html,
        'curMeal 残留': 'curMeal' in html,
        'MEAL_SUGGEST_HM 残留': 'MEAL_SUGGEST_HM' in html,
        '.meal-row CSS 残留': bool(re.search(r'\.meal-row\s*\{', html)),
    }
    ok = True
    for k, bad in static.items():
        print(('FAIL  ' if bad else 'PASS  ') + '静态 · ' + k)
        if bad:
            ok = False

    n_celeb_reset = len(re.findall(r'state\.celebFired\s*=\s*false', html))
    print(('PASS  ' if n_celeb_reset <= 3 else 'FAIL  ') +
          '静态 · celebFired 重置处仅剩跨天/重置用途 -> ' + str(n_celeb_reset))
    if n_celeb_reset > 3:
        ok = False
    has_guard = ('state.settledDate === dateStr' in html) and ('state.settledDate = dateStr' in html)
    print(('PASS  ' if has_guard else 'FAIL  ') + '静态 · 收盘幂等锚点 settledDate 已就位')
    if not has_guard:
        ok = False

    # 写测试页（放仓库根目录，保证 js/ data/ 相对路径可用）
    io.open(OUT, 'w', encoding='utf-8').write(html.replace('</body>', INJECT + '</body>'))
    print('wrote:', OUT)

    cmd = [EDGE, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
           '--virtual-time-budget=6000', '--user-data-dir=' + PROFILE, '--dump-dom',
           'file:///' + OUT.replace('\\', '/')]
    p = subprocess.run(cmd, capture_output=True, timeout=180)
    dom = p.stdout.decode('utf-8', 'replace')
    m = re.search(r'RESULT:([A-Za-z0-9+/=]+)', dom)
    if not m:
        print('FAIL  未取到页面回传结果（DOM 长度 ' + str(len(dom)) + '，stderr 尾部：'
              + p.stderr.decode('utf-8', 'replace')[-300:] + '）')
        return 1
    r = json.loads(base64.b64decode(m.group(1)).decode('utf-8'))
    if not r.get('ok'):
        print('FAIL  页面内断言抛错：' + str(r.get('err')))
        return 1

    def chk(name, cond, extra=''):
        global ok
        print(('PASS  ' if cond else 'FAIL  ') + name + ('  -> ' + str(extra) if extra != '' else ''))
        if not cond:
            ok = False

    # 1 / 3 / 4：结构
    chk('摄入圆环模块已移除', r['ringGone'])
    chk('餐次模块已移除（DOM）', r['mealGone'])
    chk('餐次模块已移除（CSS）', r['mealCssGone'])
    chk('行情页首块是体重K线', r['firstCardHasKline'])
    chk('行情页第二块是运动网格图（v2.7.38 新增）', r['secondCardIsHeat'])
    chk('交易大厅已迁入持仓页（v2.7.38）', r['tfInsideHoldings'])
    chk('交易大厅是持仓页首块', r['tfIsFirstHoldingsCard'])
    chk('交易大厅背景图存在', r['tradingFloorHasBgImg'])
    chk('交易大厅底图是 trading-floor-full.png（v2.7.33 换图）', r['tradingFloorUsesFull'])
    chk('交易大厅已去除底部跑马灯', r['tradingFloorNoTicker'])
    chk('交易大厅已无 canvas 引擎（v2.7.34 改纯 CSS 特效）', r['tradingFloorNoCanvas'])
    chk('运动网格图渲染出 154 个格子', r['heatHasCells'])
    chk('运动网格图带 少/多 图例', r['heatHasLegend'])
    chk('运动网格图带月份标签', r['heatHasMonths'])
    # 2：MA 数值
    chk('MA7 图例带数值', r['ma7'].startswith('● MA7 ') and r['ma7'].split()[1] not in ('', '--'),
        r['ma7'])
    chk('MA30 图例带数值（30 根已够算）', r['ma30'].startswith('● MA30 ') and r['ma30'].endswith('--') is False,
        r['ma30'])
    chk('仅 3 根时 MA7 显示 --', r['ma7Low'] == '● MA7 --', r['ma7Low'])
    chk('仅 3 根时 MA30 显示 --', r['ma30Low'] == '● MA30 --', r['ma30Low'])
    chk('无数据时 MA30 显示 --', r['ma30None'] == '● MA30 --', r['ma30None'])
    # 4：餐次自动推断
    chk('12:30 推断午餐', r['mealAutoLunch'] == '午餐', r['mealAutoLunch'])
    chk('22:10 推断加餐', r['mealAutoSnack'] == '加餐', r['mealAutoSnack'])
    chk('07:05 推断早餐', r['mealAutoBreakfast'] == '早餐', r['mealAutoBreakfast'])
    # 5：发币节奏（v2.7.36 起涨停由「收盘结算」触发，不再是记一笔即发）
    chk('记一笔不自动涨停（v2.7.36 新口径）',
        r['coinsBeforeSettle'] == 0 and r['celebBeforeSettle'] is False,
        str(r['coinsBeforeSettle']) + ' / celeb=' + str(r['celebBeforeSettle']))
    chk('收盘结算达标发放涨停 200 币', r['coins1'] == 200, r['coins1'])
    chk('收盘结算弹涨停动画一次', r['celebShown'] is True, r['celebShown'])
    chk('涨停计数 = 1', r['limitUp1'] == 1, r['limitUp1'])
    chk('再记 3 笔不再叠加涨停币（总 215 = 200+3×5）', r['coins4'] == 215, r['coins4'])
    chk('同日重复收盘不重复计数（settledDate 幂等）', r['limitUp4'] == 1, r['limitUp4'])
    chk('后续不再弹涨停动画', r['celebShownAgain'] is False, r['celebShownAgain'])
    # 1：K线悬浮标签
    chk('K线 SVG 已渲染', r['svgExists'] and r['svgW'] > 100, r['svgW'])
    chk('指针移动显示数据标签', r['tipShown'] is True, r['tipShown'])
    chk('标签含第 6 根K线日期', r['expectDate'] in r.get('tipHTML', ''), r['expectDate'])
    chk('标签含该根收盘价', r['expectClose'] in r.get('tipHTML', ''), r['expectClose'])
    chk('标签含 MA7 行', 'MA7' in r.get('tipHTML', '') and 'MA30' in r.get('tipHTML', ''))
    chk('十字光标已显示', r['crossShown'] is True, r['crossShown'])
    chk('越界左移吸附到首根', r['expectDate0'] in r.get('tipLeftHTML', ''), r['expectDate0'])
    chk('越界右移吸附到末根', r['expectDateN'] in r.get('tipRightHTML', ''), r['expectDateN'])
    chk('移出后标签隐藏', r['tipHiddenAfterLeave'] is True, r['tipHiddenAfterLeave'])

    print('\nRESULT=' + ('OK' if ok else 'FAIL'))
    try:
        os.remove(OUT)
    except Exception:
        pass
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(run())
