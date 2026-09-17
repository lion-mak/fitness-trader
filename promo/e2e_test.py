# -*- coding: utf-8 -*-
"""端到端验收（v2.7.52 更新）：用 Edge 无头加载真实 App，注入状态后断言结构与行为。

覆盖：
  · 摄入圆环模块 / 餐次模块 已移除（DOM 中不存在，且 render() 能跑完不抛错）
  · 行情页结构：首块 = 体重K线，第二块 = 运动网格图（v2.7.38）
  · 交易大厅已整块删除（v2.7.49）：CSS/HTML/JS 全清，账户总览上位首块
  · 运动网格图：近 1 年 371 格 / 横向可滚动 / 少·多 图例 / 月份标签（v2.7.39）
  · 涨停币每日只发一次（重复记录不再叠加 +200）
  · MA 图例带数值
  · 体重K线悬浮数据标签能由指针坐标取到正确那根K线的日期
  · 持仓页 Hero：无网格纹 / 收窄 275→200px / 数字与说明同行；「持仓明细」已删；调目标按钮在 Hero 右上（v2.7.51）
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
    // 行情页首块 = 体重K线，第二块 = 运动网格图（v2.7.38）
    out.firstCardHasKline = !!(firstCard && firstCard.querySelector('#kline'));
    out.secondCardIsHeat = cards.length >= 2 && cards[1].id === 'ex-heat-card';
    // v2.7.49：交易大厅整块删除；账户总览自动上位成持仓页首块
    var hold = document.getElementById('page-holdings');
    out.tfCardGone = !document.getElementById('tf-card');
    out.tfBgGone = !document.querySelector('.tf-bg');
    out.tfCssGone = !/\.tf-stage\s*\{/.test(document.head.innerHTML);
    out.tfFnGone = (typeof tfFlash === 'undefined' && typeof tfCelebrate === 'undefined'
                    && typeof tfToggle === 'undefined');
    // 注意：正则用拼接写法，否则本注入脚本自身的字面量会被 innerHTML 读回来（自匹配）
    out.tfKeyGone = !new RegExp('jianpan_tf_' + 'collapsed').test(document.documentElement.innerHTML);
    var hpt = hold ? hold.querySelector('.pagetitle') : null;
    out.holdingsFirstCardIsAcct = !!(hpt && hpt.nextElementSibling
                                     && hpt.nextElementSibling.id === 'acct-card');
    var heat = document.getElementById('ex-heat');
    out.heatHasCells = !!(heat && heat.querySelectorAll('.ex-heat-cell').length >= 365);
    out.heatHasLegend = !!(heat && heat.querySelector('.ex-heat-legend'));
    out.heatHasMonths = !!(heat && heat.querySelectorAll('.ex-heat-months span').length >= 3);
    var hsc = heat ? heat.querySelector('.ex-heat-scroll') : null;
    var hinner = heat ? heat.querySelector('.ex-heat-inner') : null;
    out.heatScrollable = !!hsc;
    out.heatInnerWide = !!(hinner && parseFloat(hinner.style.width) > 500);
    out.heatFootHint = !!(heat && /左右滑动/.test(heat.textContent || ''));
    out.heatStickyLabels = !!(heat && getComputedStyle(heat.querySelector('.ex-heat-days')).position === 'sticky');
    // v2.7.41：平滑色阶 —— 亮度随消耗单调不增（不会相近值跨档）
    var mono = true, prevLum = null;
    try {
      for (var vv = 20; vv <= 1500; vv += 20) {
        var col = exHeatColor(vv, [300, 450, 600], 1500);
        var lum;
        if (col.charAt(0) === '#') { var n1 = parseInt(col.slice(1), 16); lum = 0.299 * ((n1 >> 16) & 255) + 0.587 * ((n1 >> 8) & 255) + 0.114 * (n1 & 255); }
        else { var ps = col.replace('rgb(', '').replace(')', '').split(','); lum = 0.299 * (+ps[0]) + 0.587 * (+ps[1]) + 0.114 * (+ps[2]); }
        if (prevLum !== null && lum > prevLum + 0.5) mono = false;
        prevLum = lum;
      }
    } catch (e) { mono = false; }
    out.heatColorMonotonic = mono;
    out.heatLevelGone = (typeof exHeatLevel === 'undefined');
    var lgi = heat ? heat.querySelector('.ex-heat-legend i') : null;
    out.heatLegendGradient = !!(lgi && (lgi.getAttribute('style') || '').indexOf('linear-gradient') >= 0);
    // v2.7.43：周视图仅前两张；月视图四张且标题为 x月、明细 xx号(周x)
    // 注入本月数据（state 在后续涨停测试才赋值，此处先造数验证月榜明细格式）
    var lbToday = todayStr();
    state.diet = [{ id: 'lb-d', date: lbToday, name: '炸鸡', kcal: 1200, meal: '晚餐', time: '20:00' }];
    state.exercise = [
      { id: 'lb-e1', date: lbToday, name: '跑步', kcal: 400, time: '07:00' },
      { id: 'lb-e2', date: lbToday, name: '游泳', kcal: 650, time: '18:00' },
      { id: 'lb-e3', date: lbToday, name: '骑车', kcal: 300, time: '12:00' }
    ];
    out.lbWeekCardCount = -1; out.lbMonthCardCount = -1;
    out.lbWeekThree = false; out.lbMonthFive = false; out.lbKeepsBurn = false; out.lbBurnTop = ''; out.lbDayFormat = false; out.lbNoRemoved = true;
    if (typeof setLbRange === 'function') {
      setLbRange('week');
      var cw = document.getElementById('lb-content');
      out.lbWeekCardCount = cw ? cw.children.length : -1;
      var wm = function(c, i){ var el = c && c.children[i] && c.children[i].querySelector('.m'); return el ? el.textContent : ''; };
      out.lbWeekThree = (cw.children.length === 3 && wm(cw,0)==='本周' && wm(cw,1)==='本周' && wm(cw,2)==='本周' && !/大胃王日/.test(cw.textContent) && !/燃脂日/.test(cw.textContent));
      var burnCard = cw.children[2];
      out.lbBurnTop = burnCard ? (burnCard.querySelector('.lb-item .n') || {}).textContent || '' : '';
      out.lbNoRemoved = !/主力净流入|连板|板块龙虎榜|个人战绩墙/.test(cw.textContent || '');
      setLbRange('month');
      var cm = document.getElementById('lb-content');
      out.lbMonthCardCount = cm ? cm.children.length : -1;
      var curMonth = (new Date().getMonth() + 1) + '月';
      out.lbMonthFive = (out.lbMonthCardCount === 5 && wm(cm,0)===curMonth && wm(cm,1)===curMonth && wm(cm,2)===curMonth && wm(cm,3)===curMonth && wm(cm,4)===curMonth);
      out.lbKeepsBurn = /热菜榜/.test(cm.textContent) && /劳模榜/.test(cm.textContent) && /暴汗榜/.test(cm.textContent) && /大胃王日/.test(cm.textContent) && /燃脂日/.test(cm.textContent);
      out.lbNoRemoved = out.lbNoRemoved && !/主力净流入|连板|板块龙虎榜|个人战绩墙/.test(cm.textContent || '');
      var dayTxt = cm.children[3] ? (cm.children[3].textContent || '') : '';
      out.lbDayFormat = /号（周[一二三四五六日]）/.test(dayTxt);
    }
    // v2.7.46：持仓评级定位点改为 emoji
    try {
      var hrSvg = document.getElementById('holdings-rating');      out.hrHasEmoji = !!(hrSvg && hrSvg.querySelector('.hr-marker'));
    } catch (e) { out.hrHasEmoji = false; }

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
    // v2.7.44：身体成分趋势图 —— 日期少不铺满 + 颜色分区标注数字
    try {
      state.body = { bmi: 22, bodyFat: 20, muscleRate: 55, waterRate: 60, bodyAge: 30, visceralFat: 8 };
      state.bodyLog = [
        { date: '2026-09-01', bodyFat: 24 },
        { date: '2026-09-10', bodyFat: 21 },
        { date: '2026-09-20', bodyFat: 20 }
      ];
      openBodyDetail(1); // 体脂率
      var td = document.getElementById('bd-trend');
      var pl = td ? td.querySelector('polyline') : null;
      out.btHasSvg = !!pl;
      if (pl) {
        var pts = pl.getAttribute('points').trim().split(' ').map(function (p) { return p.split(',').map(parseFloat); });
        var xs = pts.map(function (q) { return q[0]; });
        var xmin = Math.min.apply(null, xs), xmax = Math.max.apply(null, xs);
        out.btFewExtent = Math.round(xmax - xmin);
        // 3 个点（少）→ 折线不应铺满整宽（plot 宽 ≈ 320-34-30=256）
        out.btFewNotFill = (xmax - xmin) < 256 * 0.9;
        // v2.7.45：Y 轴自适应数据范围，折线纵向应明显铺开（全量程下仅约 14px）
        var ys = pts.map(function (q) { return q[1]; });
        out.btLineYSpread = Math.round(Math.max.apply(null, ys) - Math.min.apply(null, ys));
      }
      // v2.7.45：身体成分子页第一个模块（bd-card）定位点真正定位
      var bdDot = document.querySelector('#bd-card .dot');
      out.bdDotPos = bdDot ? getComputedStyle(bdDot).position : 'none';
      // Y 轴：每个颜色分区带自身颜色的数字标注（非灰）
      var colored = 0;
      td.querySelectorAll('svg text').forEach(function (t) {
        var f = (t.getAttribute('fill') || '');
        if (f && f !== '#6b7690' && f.charAt(0) === '#') colored++;
      });
      out.btColoredLabels = colored;
      out.btHasBandNames = !!(td && /偏低|正常|偏胖|肥胖|标准/.test(td.textContent));
    } catch (e) { out.btErr = String((e && e.message) || e); }
    // v2.7.45：持仓「较起点」已删 / 目标仓位评价逻辑 / 缺口评级右上小字已删
    out.hChangeGone = !document.getElementById('h-change');
    out.gapSideGone = !document.getElementById('gap-side');
    try {
      state.user.startWeight = 80; state.user.weight = 78; state.user.targetWeight = 70;
      render();
      var rem = document.getElementById('acct-remain');
      out.remainUnmet = rem.textContent; out.remainUnmetColor = rem.style.color;
      state.user.weight = 69; render();
      rem = document.getElementById('acct-remain');
      out.remainMet = rem.textContent; out.remainMetColor = rem.style.color;
      state.user.weight = 78;
    } catch (e) { out.remainErr = String((e && e.message) || e); }

    // ================= v2.7.47：账户总览 / 复盘周报月报 / 数据迁移口 =================
    try {
      state.user.startWeight = 80; state.user.weight = 76; state.user.targetWeight = 70;
      var wl2 = [];
      for (var i2 = 9; i2 >= 0; i2--) wl2.push({ date: addDaysStr(today, -i2), weight: +(78.5 - (9 - i2) * 0.25).toFixed(1) });
      state.weightLog = wl2;
      state.diet = [
        { id: 'rv1', date: today, name: '炸鸡', kcal: 1200, meal: '晚餐', time: '20:00' },
        { id: 'rv2', date: addDaysStr(today, -1), name: '沙拉', kcal: 300, meal: '午餐', time: '12:00' }
      ];
      state.exercise = [{ id: 'rve1', date: today, name: '游泳', kcal: 650, time: '07:00' }];
      render();
      var rate = document.getElementById('acct-rate');
      var bar = document.getElementById('acct-bar');
      var g = function (id) { var e = document.getElementById(id); return e ? e.textContent : ''; };
      out.acctExists = !!document.getElementById('acct-card');
      out.acctRate = rate ? rate.textContent : '';
      out.acctRateClass = rate ? rate.className : '';
      out.acctCap = g('acct-cap');
      out.acctBarW = bar ? (bar.style.width || '') : '';
      out.acctCells = ['acct-cost', 'acct-now', 'acct-target'].map(function (id) {
        var e = document.getElementById(id); return e ? e.textContent : '';
      }).join('|');
      out.acctState = g('acct-state');
      // v2.7.48：盈利有上限——抵达止盈价封顶 100%
      state.user.weight = 69.5; render();
      out.acctRateDone = g('acct-rate'); out.acctStateDone = g('acct-state');
      // 跌穿止盈价很远，也绝不允许 >100%（体重不能无限降，盈利不可能无限赚）
      state.user.weight = 60; render();
      out.acctRateOver = g('acct-rate');
      state.user.weight = 76; render();
    } catch (e) { out.acctErr = String((e && e.message) || e); }

    try {
      setLbRange('week');
      var rv = document.getElementById('lb-review');
      out.rvWeekExists = !!rv;
      out.rvAfterLb = !!(rv && rv.previousElementSibling && rv.previousElementSibling.id === 'lb-content');
      out.rvWeekTitle = !!(rv && /复盘周报/.test(rv.textContent));
      out.rvWeekCells = !!(rv && /做多最狠/.test(rv.textContent) && /做空之王/.test(rv.textContent) && /缺口达标/.test(rv.textContent));
      out.rvWeekHit = !!(rv && /\d+ \/ \d+/.test(rv.textContent));
      out.rvWeekSvg = !!(rv && rv.querySelector('svg'));
      out.rvHasCopy = !!document.querySelector('[onclick="copyReview()"]');
      setLbRange('month');
      var rv2 = document.getElementById('lb-review');
      out.rvMonthTitle = !!(rv2 && /复盘月报/.test(rv2.textContent));
      setLbRange('week');
    } catch (e) { out.rvErr = String((e && e.message) || e); }

    try {
      out.migBtn1 = !!document.querySelector('[onclick="copyMigrateCode()"]');
      out.migBtn2 = !!document.querySelector('[onclick="openPasteImport()"]');
      out.migSheet = !!document.getElementById('paste-sheet') && !!document.getElementById('paste-json');
      var pl = buildExportPayload();
      out.migApp = pl.__app; out.migSchema = pl.__schema;
      out.migHasState = !!(pl.state && pl.state.diet);
      out.migNew = !!migratePayload({ __app: 'fitness-trader', __schema: 1, state: { diet: [1, 2] } });
      var oldOk = false;
      try { var dd = migratePayload({ diet: [1] }); oldOk = !!(dd && dd.diet.length === 1); } catch (e2) { }
      out.migOld = oldOk;
      var rejOk = false;
      try { migratePayload({ __app: 'fitness-trader', __schema: 99, state: {} }); } catch (e3) { rejOk = true; }
      out.migReject = rejOk;
      out.rvText = reviewText().indexOf('健身交易员') >= 0;
    } catch (e) { out.migErr = String((e && e.message) || e); }
    // ================= v2.7.50：持仓页视觉体系（Hero / Primary / Data + 账本母题）=================
    try {
      state.user.startWeight = 80; state.user.weight = 78; state.user.targetWeight = 70;
      render();
      var hold2 = document.getElementById('page-holdings');
      var hero = document.getElementById('acct-card');
      out.uiHeroIsBlock = !!(hold2 && hero && hero.className.indexOf('hero') >= 0);
      var hpt2 = hold2 ? hold2.querySelector('.pagetitle') : null;
      out.uiHeroRightAfterTitle = !!(hpt2 && hpt2.nextElementSibling === hero);
      out.uiHeroHasBigNum = !!(hero && hero.querySelector('.hero-num#acct-rate'));
      out.uiHeroHasTrack = !!(hero && hero.querySelector('.hero-track i#acct-bar'));
      out.uiLedgerRows = hero ? hero.querySelectorAll('.ledger .lrow').length : -1;
      out.uiNoUpperCap = g('acct-cap').indexOf('上限') < 0;   // 用户：上限 xx kg 不需要，删掉
      out.uiHeroBadgeGone = !document.getElementById('acct-hold');
      out.uiIdline = !!document.querySelector('#page-holdings .pagetitle .idline');
      // 三级层级：Primary 卡改左色条，Data 区无卡片
      out.uiPrimaryGreen = !!document.querySelector('#page-holdings .pcard--green');
      out.uiPrimaryRed = !!document.querySelector('#page-holdings .pcard--red');
      out.uiNoDSection50 = !document.querySelector('#page-holdings .dsection');
      out.uiNoMetricGrid = !document.querySelector('#page-holdings .metric-grid');
      var pcardAccent = document.querySelector('#page-holdings .pcard--red');
      out.uiPcardNoBorder = !!pcardAccent && getComputedStyle(pcardAccent).borderTopWidth === '0px';
      // 「ⓘ 口径」折叠：默认收起，点开才显示
      var note = document.getElementById('gap-note');
      out.uiNoteFolded = !!note && getComputedStyle(note).display === 'none';
      toggleGapNote();
      out.uiNoteOpen = !!note && getComputedStyle(note).display !== 'none';
      toggleGapNote();
      out.uiNoteReFolded = !!note && getComputedStyle(note).display === 'none';
      // 【用户反馈】目标仓位调整按钮在哪？→ 固定在持仓明细标题行，永远可点
      var twBtn = document.getElementById('tw-open-btn');
      out.uiTwBtn = !!(twBtn && twBtn.closest('.hero-top')
                       && twBtn.getAttribute('onclick') === 'toggleTargetW()');
      toggleTargetW();
      var trow = document.getElementById('tw-row');
      out.uiTwRowOpens = !!trow && trow.style.display === 'flex';
      closeTargetW();
      out.uiTwRowCloses = !!trow && trow.style.display === 'none';

      // 「跑赢 X% 的交易日」必须真算：7 个清淡历史日 + 今日极低摄入 → 跑赢 100%
      var uik, uih = [];
      for (uik = 7; uik >= 1; uik--) uih.push({ id: 'ui' + uik, date: addDaysStr(today, -uik), name: '饭', kcal: 2000, meal: '午餐', time: '12:00' });
      state.diet = uih.concat([{ id: 'uit', date: today, name: '沙拉', kcal: 200, meal: '午餐', time: '12:00' }]);
      state.exercise = []; state.weightLog = [];
      render();
      var rk = document.getElementById('gap-rank');
      out.uiRankShown = !!rk && rk.style.display !== 'none' && /跑赢 \d+% 的交易日/.test(rk.textContent);
      out.uiRankAll = !!rk && rk.textContent === '跑赢 100% 的交易日';
      // 样本不足（仅 3 个历史交易日）→ 整句话隐藏，绝不编数据
      state.diet = [
        { id: 'ui-a', date: addDaysStr(today, -3), name: '饭', kcal: 2000, meal: '午餐', time: '12:00' },
        { id: 'ui-b', date: addDaysStr(today, -2), name: '饭', kcal: 2000, meal: '午餐', time: '12:00' },
        { id: 'ui-c', date: addDaysStr(today, -1), name: '饭', kcal: 2000, meal: '午餐', time: '12:00' },
        { id: 'ui-t', date: today, name: '沙拉', kcal: 200, meal: '午餐', time: '12:00' }
      ];
      render();
      rk = document.getElementById('gap-rank');
      out.uiRankHidden = !!rk && rk.style.display === 'none' && rk.textContent === '';
      out.uiRankFnNull = gapRankPct(-1200) === null;

      // 「按当前速度约 X 周」：近期缺口稳定 → 给出真实周数；无缺口 → 不预估
      state.diet = [];
      for (uik = 10; uik >= 1; uik--) state.diet.push({ id: 'up' + uik, date: addDaysStr(today, -uik), name: '饭', kcal: 1200, meal: '午餐', time: '12:00' });
      state.diet.push({ id: 'upt', date: today, name: '沙拉', kcal: 300, meal: '午餐', time: '12:00' });
      state.user.weight = 78;
      render();
      out.uiPaceShown = /按当前速度约 [\d.]+ 周/.test(g('acct-remain'));
      out.uiPaceNum = paceWeeks(8);
      state.user.weight = 69; render();
      out.uiPaceDone = g('acct-remain').indexOf('已达成目标') >= 0;
      state.diet = [{ id: 'z1', date: today, name: '饭', kcal: 5000, meal: '午餐', time: '12:00' }];
      out.uiPaceNoGap = paceWeeks(8) === null;
      state.user.weight = 76;
    } catch (e) { out.uiErr = String((e && e.message) || e); }
    // ================= v2.7.51：持仓页瘦身 + 结构调整（用户反馈）=================
    try {
      state.user.startWeight = 80; state.user.weight = 78; state.user.targetWeight = 70;
      switchTab('holdings');   // 必须切到持仓页：display:none 时 offsetHeight/getBoundingClientRect 全是 0，断言会假通过
      render();
      var hero3 = document.getElementById('acct-card');
      var rules3 = document.styleSheets[0].cssRules, heroRule = null, hri;
      for (hri = 0; hri < rules3.length; hri++) {
        if (rules3[hri].selectorText === '.hero') { heroRule = rules3[hri]; break; }
      }
      out.uiHeroPadTop = heroRule ? heroRule.style.paddingTop : '';
      out.uiHeroNoGrid = getComputedStyle(hero3, '::before').backgroundImage === 'none';
      out.uiHeroHeight = hero3.offsetHeight;
      // 大数字与「止盈进度 · 已盈 xx kg」并成一行，说明靠右
      out.uiHeroMidRow = !!(hero3.querySelector('.hero-mid .hero-num#acct-rate')
                            && hero3.querySelector('.hero-mid .hero-cap#acct-cap'));
      var cap3 = document.getElementById('acct-cap');
      var num3 = document.getElementById('acct-rate');
      out.uiCapAlign = getComputedStyle(cap3).textAlign;
      out.uiCapRightOfNum = cap3.getBoundingClientRect().left > num3.getBoundingClientRect().right - 1;
      out.uiCapProfitRed = cap3.innerHTML.indexOf('#ff3b47') >= 0 && cap3.textContent.indexOf('+') >= 0;
      out.uiHeroNumSize = getComputedStyle(num3).fontSize;
      // 「持仓明细」整块清零（DOM + CSS），render() 不再引用 h-weight/h-target/h-remain
      out.uiNoDSection = !document.querySelector('#page-holdings .dsection')
                         && !/\.dsection\s*\{/.test(document.head.innerHTML)
                         && !/\.drow\s*\{/.test(document.head.innerHTML);
      out.uiNoHoldRows = !document.getElementById('h-weight') && !document.getElementById('h-target')
                         && !document.getElementById('h-remain');
      // 「距止盈目标」那句话搬进 Hero，琥珀色
      var rem3 = document.getElementById('acct-remain');
      out.uiRemainInHero = !!(rem3 && rem3.closest('#acct-card') && rem3.className.indexOf('hero-remain') >= 0);
      out.uiRemainAmber = rem3 ? rem3.style.color : '';
      out.uiRemainText = rem3 ? rem3.textContent : '';
      // 「🎯 调整目标」按钮 = Hero 右上（顶掉原「持仓 xx 天」徽章位）
      var tw3 = document.getElementById('tw-open-btn');
      out.uiTwInHeroTop = !!(tw3 && tw3.closest('.hero-top') && tw3.classList.contains('hero-badge')
                             && tw3.getAttribute('onclick') === 'toggleTargetW()');
      out.uiHoldBadgeGone = !document.getElementById('acct-hold');
      var wrap3 = document.querySelector('#page-holdings .kw-wrap');
      out.uiTwRowUnderHero = !!(wrap3 && wrap3.previousElementSibling === hero3);
      toggleTargetW();
      var trow3 = document.getElementById('tw-row');
      out.uiTwOpens51 = !!trow3 && trow3.style.display === 'flex';
      closeTargetW();
      out.uiTwCloses51 = !!trow3 && trow3.style.display === 'none';
      // 已达成目标 → 红色（盈利色，与主数字同色）
      state.user.weight = 69; render();
      out.uiRemainMetRed = document.getElementById('acct-remain').style.color;
      state.user.weight = 78; render();
      switchTab('market');
    } catch (e) { out.uiErr51 = String((e && e.message) || e); }
    // ================= v2.7.52：Hero 排版 / 单边柱趋势 / 评级 Hero 化 / tab 顺序与彩色图标 =================
    try {
      state.user.startWeight = 80; state.user.weight = 78; state.user.targetWeight = 70;
      switchTab('holdings');
      state.body = { bodyFat: 19.4, bmi: 24.4 };
      render();
      var hero4 = document.getElementById('acct-card');
      // A) 红色氛围光已删（.hero::after 无内容）
      out.ui52NoGlow = getComputedStyle(hero4, '::after').content === 'none';
      // B) 大数字排版收紧 + 右侧说明改两行右对齐
      var num4 = document.getElementById('acct-rate'), cap4 = document.getElementById('acct-cap');
      var ncs4 = getComputedStyle(num4);
      out.ui52NumSize = ncs4.fontSize;
      out.ui52NumSpacing = ncs4.letterSpacing;
      var k4 = cap4.querySelector('.k'), b4 = cap4.querySelector('b');
      out.ui52CapOneLine = !!(k4 && b4) && Math.abs(k4.getBoundingClientRect().bottom - b4.getBoundingClientRect().bottom) < 4;
      out.ui52CapRight = getComputedStyle(cap4).textAlign === 'right';
      // C) 净热量趋势：单边柱（全部贴同一条基线向上），只有绿(缺口)/红(超额)
      state.diet = []; state.exercise = [];
      var d4, over4;
      for (d4 = 12; d4 >= 1; d4--) {
        over4 = (d4 % 3 === 0);                       // 每 3 天一次爆表 → 应该有红柱
        state.diet.push({ id: 't52d' + d4, date: addDaysStr(today, -d4), name: '饭',
                          kcal: over4 ? 4300 : 1350 + d4 * 12, meal: '午餐', time: '12:00' });
        state.exercise.push({ id: 't52e' + d4, date: addDaysStr(today, -d4), name: '跑步',
                              kcal: over4 ? 90 : 820 + d4 * 9, min: 40, met: 8 });
      }
      render();
      var bars4 = document.querySelectorAll('#trend rect'), bi4;
      out.ui52BarCount = bars4.length;
      var base4 = -1;
      for (bi4 = 0; bi4 < bars4.length; bi4++) {
        var yy4 = +bars4[bi4].getAttribute('y'), hh4 = +bars4[bi4].getAttribute('height');
        if (yy4 + hh4 > base4) base4 = yy4 + hh4;      // 最低边 = 基线
      }
      var allBase = bars4.length > 0, colSet = {}, hSet = {};
      for (bi4 = 0; bi4 < bars4.length; bi4++) {
        var b4 = bars4[bi4], y4 = +b4.getAttribute('y'), h4 = +b4.getAttribute('height');
        if (Math.abs((y4 + h4) - base4) > 0.5) allBase = false;   // 每根柱底都落在同一条基线上 → 单边柱
        if (y4 < 0) allBase = false;                              // 不许越过画布顶 → 没有上下分叉
        colSet[b4.getAttribute('fill')] = 1;
        hSet[Math.round(h4)] = 1;
      }
      out.ui52BarsBaseline = allBase;
      out.ui52BarColors = Object.keys(colSet).sort().join(',');
      out.ui52BarHeights = Object.keys(hSet).length;
      switchTab('market');
      // D) 持仓评级 → Hero 款式
      switchTab('holdings'); render();
      var hr4 = document.getElementById('hr-card');
      out.ui52HrHero = !!hr4 && hr4.className.indexOf('hero') >= 0 && hr4.className.indexOf('hr-hero') >= 0;
      out.ui52HrNoCard = !!hr4 && getComputedStyle(hr4).borderTopWidth === '0px';
      var gr4 = document.getElementById('holdings-rating-text');
      out.ui52HrGradeBig = !!gr4 && parseFloat(getComputedStyle(gr4).fontSize) >= 26;
      out.ui52HrGradeText = gr4 ? gr4.textContent : '';
      out.ui52HrFat = g('hr-fat');
      out.ui52HrBmi = g('hr-bmi');
      var lab4 = hr4 ? hr4.querySelector('.hero-lab') : null;
      out.ui52HrNoDupName = !!lab4 && !!out.ui52HrGradeText
                            && lab4.textContent.indexOf(out.ui52HrGradeText) < 0;
      out.ui52HrDescNoDup = g('holdings-rating-desc').indexOf('19.4%') < 0;
      switchTab('market');
      // E) tab 顺序 + 交易彩色图标
      var tabs4 = [];
      document.querySelectorAll('.tabbar > div').forEach(function (x) { tabs4.push(x.getAttribute('data-tab')); });
      out.ui52TabOrder = tabs4.join(',');
      var tico4 = document.querySelector('.tabbar .ico-trade svg');
      out.ui52TradeIconColorful = !!tico4
        && tico4.innerHTML.indexOf('#e2703f') >= 0        // 鸡腿肉（暖橙）
        && tico4.innerHTML.indexOf('#c9d7ec') >= 0        // 哑铃配重片（钢蓝）
        && tico4.innerHTML.indexOf('#f4efe2') >= 0        // 骨头（奶白）
        && tico4.innerHTML.indexOf('currentColor') < 0;   // 不是线稿图标
      out.ui52TradeIconTag = tico4 ? tico4.tagName.toLowerCase() : '';
      out.ui52OtherIconsLine = document.querySelectorAll('.tabbar .ico svg[stroke="currentColor"]').length;
    } catch (e) { out.uiErr52 = String((e && e.message) || e); }
    // ================= v2.7.53：大数字排版 / 趋势周期+横滑 / 名次分色 / 图标翻转 =================
    try {
      state.user.startWeight = 80; state.user.weight = 78; state.user.targetWeight = 70;
      switchTab('holdings');
      render();
      // A) 大数字分段：整数位 44px / 小数位 30px / 「%」回底线（不再上标）
      var num5 = document.getElementById('acct-rate');
      var iv5 = num5.querySelector('.iv'), dec5 = num5.querySelector('.dec'), pc5 = num5.querySelector('.pc');
      out.ui53HasSeg = !!(iv5 && dec5 && pc5);
      out.ui53IvSize = iv5 ? getComputedStyle(iv5).fontSize : '';
      out.ui53DecSize = dec5 ? getComputedStyle(dec5).fontSize : '';
      out.ui53PcSize = pc5 ? getComputedStyle(pc5).fontSize : '';
      out.ui53DecSmaller = !!dec5 && parseFloat(out.ui53DecSize) < parseFloat(out.ui53IvSize);
      out.ui53PcPos = pc5 ? getComputedStyle(pc5).position : '';
      out.ui53PcTop = pc5 ? getComputedStyle(pc5).top : '';
      out.ui53PcVAlign = pc5 ? getComputedStyle(pc5).verticalAlign : '';
      // B) 「止盈进度 · 已盈 +x kg」回到一条线
      var cap5 = document.getElementById('acct-cap');
      var k5 = cap5.querySelector('.k'), b5 = cap5.querySelector('b');
      var kb5 = k5 ? k5.getBoundingClientRect() : null, bb5 = b5 ? b5.getBoundingClientRect() : null;
      out.ui53CapOneLine = !!(kb5 && bb5) && Math.abs(kb5.bottom - bb5.bottom) < 4 && kb5.right <= bb5.left + 1;
      out.ui53CapNoV = !cap5.querySelector('.v');
      out.ui53CapText = cap5.textContent;
      // C) 净热量趋势：周期切换 + 横向滚动（100 天记录 → 「全部」必须可横滑）
      state.diet = []; state.exercise = [];
      var i5;
      for (i5 = 0; i5 < 100; i5++) {
        var d5 = addDaysStr(today, -i5);
        state.diet.push({ id: 't53d' + i5, date: d5, name: '饭', kcal: 1500, meal: '午餐', time: '12:00' });
        state.exercise.push({ id: 't53e' + i5, date: d5, name: '跑步', kcal: 700 - i5, min: 40, met: 8 });
      }
      switchTab('market'); render(); switchTab('holdings');   // 走一遍「隐藏态量不到宽度 → 切页补绘」的路
      var tab53 = [];
      document.querySelectorAll('#nt-tabs .nt-tab').forEach(function (x) { tab53.push(x.getAttribute('data-nt')); });
      out.ui53Tabs = tab53.join(',');
      var sc5 = document.getElementById('nt-scroll');
      setTrendRange('all');
      out.ui53AllBars = document.querySelectorAll('#trend rect').length;
      out.ui53AllScrollable = !!sc5 && sc5.scrollWidth > sc5.clientWidth + 10;
      out.ui53AllAtEnd = !!sc5 && (sc5.scrollLeft + sc5.clientWidth) >= (sc5.scrollWidth - 6);
      out.ui53Hint = (document.getElementById('nt-hint') || {}).textContent;
      setTrendRange('7d');
      out.ui53SevenBars = document.querySelectorAll('#trend rect').length;
      out.ui53SevenNoScroll = !!sc5 && sc5.scrollWidth <= sc5.clientWidth + 2;
      out.ui53SevenHint = (document.getElementById('nt-hint') || {}).textContent;
      setTrendRange('30d');
      out.ui53MonthBars = document.querySelectorAll('#trend rect').length;
      out.ui53MonthSub = (document.getElementById('trend-sub') || {}).textContent;
      setTrendRange('365d');
      out.ui53YearBars = document.querySelectorAll('#trend rect').length;
      out.ui53YearSub = (document.getElementById('trend-sub') || {}).textContent;
      setTrendRange('all');
      switchTab('market');
      // D) 龙虎榜名次徽章：三档分色（1 最深 → 3 最浅）+ 食物红系 / 运动绿系
      setLbRange('month');
      var lum5 = function (c) { var m = String(c).match(/\d+/g); return m ? 0.299 * +m[0] + 0.587 * +m[1] + 0.114 * +m[2] : -1; };
      var rgb5 = function (c) { var m = String(c).match(/\d+/g); return m ? [+m[0], +m[1], +m[2]] : [0, 0, 0]; };
      var foodR = [], exR = [], k5i;
      for (k5i = 1; k5i <= 3; k5i++) {
        var fe5 = document.querySelector('#lb-content .lb-food .rank.r' + k5i);
        var ee5 = document.querySelector('#lb-content .lb-ex .rank.r' + k5i);
        foodR.push(fe5 ? getComputedStyle(fe5).backgroundColor : '');
        exR.push(ee5 ? getComputedStyle(ee5).backgroundColor : '');
      }
      out.ui53FoodR1 = foodR[0]; out.ui53ExR1 = exR[0];
      out.ui53RankLums = foodR.map(lum5).join(' / ') + ' | ' + exR.map(lum5).join(' / ');
      out.ui53RankRamp = foodR.concat(exR).every(function (v) { return lum5(v) >= 0; })
        && lum5(foodR[0]) < lum5(foodR[1]) && lum5(foodR[1]) < lum5(foodR[2])
        && lum5(exR[0]) < lum5(exR[1]) && lum5(exR[1]) < lum5(exR[2]);
      var fr5 = rgb5(foodR[2]), er5 = rgb5(exR[2]);
      out.ui53RankHue = (fr5[0] > fr5[1]) && (er5[1] > er5[0]);
      out.ui53RankCount = document.querySelectorAll('#lb-content .lb-food').length
                          + document.querySelectorAll('#lb-content .lb-ex').length;
      setLbRange('week');
      // E) 交易图标：翻转 + 双轴过中心
      var tsvg5 = document.querySelector('.tabbar .ico-trade svg');
      out.ui53IconG = tsvg5 && tsvg5.querySelector('g') ? tsvg5.querySelector('g').getAttribute('transform') : '';
      out.ui53IconFlip = !!tsvg5
        && out.ui53IconG.indexOf('scale(1.18)') >= 0
        && tsvg5.innerHTML.indexOf('translate(-1.4') < 0 && tsvg5.innerHTML.indexOf('translate(1.4') < 0
        && tsvg5.innerHTML.indexOf('19.15') >= 0;
    } catch (e) { out.uiErr53 = String((e && e.message) || e); }
    // ===== v2.7.54：底栏等宽列 / Hero 右侧数值收紧 / 止盈目标琥珀 / 缺口评级右对齐 =====
    try {
      switchTab('holdings');
      render();
      // A) 底栏：5 个 tab 等宽 ⇒ 图标中心严格等距，且中间那格落在底栏几何中心
      var tb54 = document.querySelector('.tabbar');
      var its54 = tb54.querySelectorAll(':scope > div');
      var ws54 = [], cs54 = [];
      for (var z54 = 0; z54 < its54.length; z54++) {
        ws54.push(+its54[z54].getBoundingClientRect().width.toFixed(1));
        var rb54 = its54[z54].querySelector('.ico svg').getBoundingClientRect();
        cs54.push(+(rb54.left + rb54.width / 2).toFixed(1));
      }
      out.ui54TabWidths = ws54.join(',');
      out.ui54TabCenters = cs54.join(',');
      out.ui54EvenWidth = Math.max.apply(null, ws54) - Math.min.apply(null, ws54) < 1;
      var gaps54 = [];
      for (var z55 = 1; z55 < cs54.length; z55++) gaps54.push(+(cs54[z55] - cs54[z55 - 1]).toFixed(1));
      out.ui54Gaps = gaps54.join(',');
      out.ui54EvenGaps = Math.max.apply(null, gaps54) - Math.min.apply(null, gaps54) < 1;
      var tbr54 = tb54.getBoundingClientRect();
      out.ui54TradeOnCenter = Math.abs(cs54[2] - (tbr54.left + tbr54.width / 2)) < 0.6;
      out.ui54TradeOffPx = +(cs54[2] - (tbr54.left + tbr54.width / 2)).toFixed(1);
      // 无放大补偿：交易图标框宽 == 其余图标框宽（v2.7.52 的 23px 被 flex 收缩吃掉、从未生效，已删）
      out.ui54IconBoxW = getComputedStyle(tb54.querySelector('.ico-trade svg')).width;
      out.ui54IconBoxWRef = getComputedStyle(tb54.querySelector('.ico svg')).width;
      // B) Hero 右侧「+x kg」：字号收小 + 负字距/负词距
      var cb54 = document.querySelector('#acct-cap b');
      var cs54b = getComputedStyle(cb54);
      out.ui54CapSize = cs54b.fontSize;
      out.ui54CapSpacing = cs54b.letterSpacing;
      out.ui54CapWordSpacing = cs54b.wordSpacing;
      out.ui54CapSmaller = parseFloat(cs54b.fontSize) < 16;
      out.ui54CapTight = parseFloat(cs54b.letterSpacing) < 0 && parseFloat(cs54b.wordSpacing) < 0;
      var ck54 = document.querySelector('#acct-cap .k');
      out.ui54CapOneLine = Math.abs(ck54.getBoundingClientRect().bottom - cb54.getBoundingClientRect().bottom) < 4;
      out.ui54CapNoSuperscript = cs54b.verticalAlign === 'baseline';
      // C) 止盈目标 → 琥珀（目标类数据统一色 #ff9f43，与 Hero 里「距止盈目标 还差」同色）
      var tg54 = document.getElementById('acct-target');
      var tgc54 = getComputedStyle(tg54).color;
      out.ui54TgtColor = tgc54;
      out.ui54TgtAmber = (tgc54 === 'rgb(255, 159, 67)') && tg54.className.indexOf('tgt') >= 0;
      out.ui54TgtSameAsRemain = tgc54 === getComputedStyle(document.getElementById('acct-remain')).color;
      // D) 缺口评级三卡：文字与数字都右对齐（看文字实际右边缘，而不是块级盒子的右边缘）
      var gc54 = document.querySelector('.gap2-grid > div');
      var txtRight54 = function (el) {
        var rg = document.createRange(); rg.selectNodeContents(el);
        return +rg.getBoundingClientRect().right.toFixed(1);
      };
      out.ui54GapAlign = getComputedStyle(gc54).textAlign;
      out.ui54GapRight = getComputedStyle(gc54).textAlign === 'right'
        && getComputedStyle(gc54.querySelector('.v')).textAlign === 'right'
        && getComputedStyle(gc54.querySelector('.l')).textAlign === 'right';
      var vr54 = txtRight54(gc54.querySelector('.v')), lr54 = txtRight54(gc54.querySelector('.l'));
      out.ui54GapFlush = Math.abs(vr54 - lr54) < 1.5;
      out.ui54GapTextRight = vr54 + ' / ' + lr54;
      out.ui54GapNotLeft = vr54 > 60;   // 若是左对齐，数字会从内容左边缘起，右边缘远小于 60
      switchTab('market');
    } catch (e) { out.uiErr54 = String((e && e.message) || e); }

    /* ===== v2.7.55：行情页右上角「↺ 重置」已删除（顶部误触会清空全部记录） ===== */
    try {
      switchTab('market');
      var ph55 = document.querySelector('#page-market .pheader');
      out.ui55HdrKids = ph55 ? ph55.children.length : -1;
      out.ui55LogoOnly = !!ph55 && ph55.children.length === 1
        && ph55.children[0].classList.contains('logo');
      out.ui55HasResetInHdr = !!document.querySelector('#page-market .pheader .reset');
      out.ui55ResetNodes = document.querySelectorAll('.reset').length;
      out.ui55ResetFnGone = (typeof window.resetAll === 'undefined');
      out.ui55HdrOnclicks = document.querySelectorAll('#page-market .pheader [onclick]').length;
      out.ui55HdrOnclickWhat = ph55
        ? Array.prototype.map.call(ph55.querySelectorAll('[onclick]'),
            function(n){ return n.getAttribute('onclick'); }).join(',')
        : 'no-header';
    } catch (e) { out.uiErr55 = String((e && e.message) || e); }
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
    global ok                     # ⚠️ 必须 global：chk() 里改的是模块级 ok，
    html = io.open(SRC, encoding='utf-8').read()   # 否则 run() 的局部 ok 永远 True，RESULT 恒为 OK
    print('inline total chars:', len(html))
    # 静态审计：已删除的标识符不应再出现在代码里
    static = {
        'ring-fill 残留': 'ring-fill' in html,
        'fs-meals 残留': 'fs-meals' in html,
        'curMeal 残留': 'curMeal' in html,
        'MEAL_SUGGEST_HM 残留': 'MEAL_SUGGEST_HM' in html,
        '.meal-row CSS 残留': bool(re.search(r'\.meal-row\s*\{', html)),
        'resetAll 函数残留': 'function resetAll' in html,
        '行情页重置按钮残留': 'onclick="resetAll' in html,
        '.pheader .reset CSS 残留': '.pheader .reset' in html,
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
    chk('交易大厅已整块删除（DOM·v2.7.49）', r['tfCardGone'])
    chk('交易大厅底图元素已删除（v2.7.49）', r['tfBgGone'])
    chk('交易大厅 CSS 已清理（v2.7.49）', r['tfCssGone'])
    chk('交易大厅 JS 引擎/调用已删除（v2.7.49）', r['tfFnGone'])
    chk('交易大厅折叠状态存储键已清理（v2.7.49）', r['tfKeyGone'])
    chk('持仓页首块变为账户总览（v2.7.49）', r['holdingsFirstCardIsAcct'])
    chk('运动网格图渲染出近一年 371 个格子（v2.7.39）', r['heatHasCells'])
    chk('运动网格图带 少/多 图例', r['heatHasLegend'])
    chk('运动网格图带月份标签', r['heatHasMonths'])
    chk('运动网格图有横向滚动容器', r['heatScrollable'])
    chk('网格内容宽度 > 一屏（可横向滚动）', r['heatInnerWide'])
    chk('网格底部带「左右滑动」提示', r['heatFootHint'])
    chk('星期行标 sticky 固定在左侧', r['heatStickyLabels'])
    chk('平滑色阶：亮度随消耗单调不增（v2.7.41）', r['heatColorMonotonic'])
    chk('旧的分档函数 exHeatLevel 已移除', r['heatLevelGone'])
    chk('图例改为连续渐变条', r['heatLegendGradient'])
    chk('龙虎榜本周模式显示 3 张（含暴汗榜，v2.7.46）', r['lbWeekCardCount'] == 3, r['lbWeekCardCount'])
    chk('龙虎榜本周三张均标「本周」且无月榜', r['lbWeekThree'])
    chk('龙虎榜本月模式显示 5 张（v2.7.46）', r['lbMonthCardCount'] == 5, r['lbMonthCardCount'])
    chk('龙虎榜本月五张标题均为 x月（v2.7.46）', r['lbMonthFive'])
    chk('龙虎榜保留 热菜/劳模/暴汗/大胃王日/燃脂日', r['lbKeepsBurn'])
    chk('暴汗榜按消耗热量排名（#1=游泳 650kcal）', r['lbBurnTop'] == '游泳', r['lbBurnTop'])
    chk('持仓评级定位点改为 emoji 🧑（v2.7.46）', r['hrHasEmoji'])
    chk('龙虎榜已无 净流入/连板战绩/板块榜/战绩墙', r['lbNoRemoved'])
    chk('龙虎榜月榜明细显示「xx号（周x）」', r['lbDayFormat'])
    # 2：MA 数值
    chk('MA7 图例带数值', r['ma7'].startswith('● MA7 ') and r['ma7'].split()[1] not in ('', '--'),
        r['ma7'])
    chk('MA30 图例带数值（30 根已够算）', r['ma30'].startswith('● MA30 ') and r['ma30'].endswith('--') is False,
        r['ma30'])
    chk('仅 3 根时 MA7 显示 --', r['ma7Low'] == '● MA7 --', r['ma7Low'])
    chk('仅 3 根时 MA30 显示 --', r['ma30Low'] == '● MA30 --', r['ma30Low'])
    # v2.7.44：身体成分趋势图
    chk('趋势图已渲染 SVG（体脂率 3 点）', r['btHasSvg'])
    chk('日期少：折线不铺满整宽（v2.7.44）', r['btFewNotFill'], r.get('btFewExtent'))
    chk('Y 轴每个颜色分区带自身颜色标注数字（v2.7.44）', r['btColoredLabels'] >= 4, r.get('btColoredLabels'))
    chk('右侧显示颜色分区名（偏低/正常/偏胖/肥胖）', r['btHasBandNames'])
    chk('无数据时 MA30 显示 --', r['ma30None'] == '● MA30 --', r['ma30None'])
    # v2.7.45：身体成分子页定位点 + 趋势图 Y 轴自适应 + 持仓/缺口评级清理
    chk('身体成分子页第一个模块定位点已定位（v2.7.45 修 CSS 选择器）', r.get('bdDotPos') == 'absolute', r.get('bdDotPos'))
    chk('趋势图 Y 轴自适应：折线纵向明显铺开（v2.7.45）', (r.get('btLineYSpread') or 0) > 80, r.get('btLineYSpread'))
    chk('持仓「较起点+xxkg」已删除（v2.7.45）', r['hChangeGone'])
    chk('缺口评级右上「含基础代谢·全天口径」小字已删除（v2.7.45）', r['gapSideGone'])
    chk('目标未达成：琥珀色「还差 xx kg」（v2.7.51 红只留给盈利）',
        '还差' in (r.get('remainUnmet') or '') and 'rgb(255, 159, 67)' in (r.get('remainUnmetColor') or ''),
        (r.get('remainUnmet') or '') + ' / ' + (r.get('remainUnmetColor') or ''))
    chk('目标已达成：红色祝贺语（盈利色）',
        '已达成目标' in (r.get('remainMet') or '') and 'rgb(255, 59, 71)' in (r.get('remainMetColor') or ''),
        (r.get('remainMet') or '') + ' / ' + (r.get('remainMetColor') or ''))

    # ===== v2.7.50：持仓页视觉体系（三级层级 + 账本母题）=====
    chk('账户总览升格为 Hero 账户头（无 card 边框）', r.get('uiHeroIsBlock'))
    chk('Hero 紧跟在 pagetitle 之后（仍是持仓页首块）', r.get('uiHeroRightAfterTitle'))
    chk('Hero 含大号等宽数字 + 3px 进度轨道', r.get('uiHeroHasBigNum') and r.get('uiHeroHasTrack'))
    chk('账本母题：Hero 内 3 行「标签·虚线·等宽数字」', r.get('uiLedgerRows') == 3, r.get('uiLedgerRows'))
    chk('「止盈进度 · 上限 xx kg」已删除（v2.7.50）', r.get('uiNoUpperCap'))
    chk('原「持仓 xx 天」徽章已移除（位子让给调整目标按钮）', r.get('uiHeroBadgeGone'))
    chk('页面身份线 idline 已加', r.get('uiIdline'))
    chk('Primary 卡改左色条（绿=趋势/红=缺口）', r.get('uiPrimaryGreen') and r.get('uiPrimaryRed'))
    chk('Primary 卡去四周边框（左色条替代）', r.get('uiPcardNoBorder'))
    chk('持仓明细 Data 区已删除（v2.7.51）', r.get('uiNoDSection50') and r.get('uiNoMetricGrid'))
    chk('「ⓘ 口径」默认收起 / 点击展开 / 再点收起', r.get('uiNoteFolded') and r.get('uiNoteOpen') and r.get('uiNoteReFolded'))
    chk('🎯 调整目标按钮位于 Hero 顶栏且可点', r.get('uiTwBtn'))
    chk('点「调整目标」弹出输入行 / 取消可收起', r.get('uiTwRowOpens') and r.get('uiTwRowCloses'))
    chk('「跑赢 X% 的交易日」真算（7 日历史+今日极值→100%）', r.get('uiRankShown') and r.get('uiRankAll'), r.get('uiRankAll'))
    chk('历史交易日 < 7 天 → 整句话隐藏（不编数据）', r.get('uiRankHidden') and r.get('uiRankFnNull'))
    chk('「按当前速度约 X 周」真算（近期缺口稳定 → 真实周数）', r.get('uiPaceShown') and isinstance(r.get('uiPaceNum'), (int, float)), r.get('uiPaceNum'))
    chk('已达成目标 → 显示祝贺语', r.get('uiPaceDone'))
    chk('平均缺口 ≤ 50 kcal → 不做周数预估', r.get('uiPaceNoGap'))
    chk('v2.7.50 注入块无异常', not r.get('uiErr'), r.get('uiErr'))

    # ===== v2.7.51：持仓页瘦身 + 结构调整（用户反馈）=====
    chk('Hero 去掉网格纹底（用户嫌像格子）', r.get('uiHeroNoGrid'))
    chk('Hero 内距收窄到 10px（旧版 16px）', r.get('uiHeroPadTop') == '10px', r.get('uiHeroPadTop'))
    chk('Hero 总高收窄到 130~210px（旧版实测 275px；含下限防页面隐藏时 0 假通过）',
        isinstance(r.get('uiHeroHeight'), (int, float)) and 130 <= r.get('uiHeroHeight') <= 210, r.get('uiHeroHeight'))
    chk('大数字为 42px→44px（v2.7.52 排版收紧后仍是页面最大号）',
        r.get('uiHeroNumSize') in ('42px', '44px'), r.get('uiHeroNumSize'))
    chk('大数字与「止盈进度 · 已盈」并成一行、说明靠右',
        r.get('uiHeroMidRow') and r.get('uiCapAlign') == 'right' and r.get('uiCapRightOfNum') is True,
        str(r.get('uiCapRightOfNum')))
    chk('「+xx kg」染红（盈利色）', r.get('uiCapProfitRed'))
    chk('「持仓明细」整块清零（CSS + DOM + render 引用）', r.get('uiNoDSection') and r.get('uiNoHoldRows'))
    chk('「距止盈目标」句搬进 Hero 且为琥珀色',
        r.get('uiRemainInHero') and r.get('uiRemainAmber') == 'rgb(255, 159, 67)',
        (r.get('uiRemainText') or '') + ' / ' + (r.get('uiRemainAmber') or ''))
    chk('已达成目标 → 红色（盈利色）', r.get('uiRemainMetRed') == 'rgb(255, 59, 71)', r.get('uiRemainMetRed'))
    chk('🎯 调整目标按钮移入 Hero 右上（顶掉持仓天数徽章）', r.get('uiTwInHeroTop') and r.get('uiHoldBadgeGone'))
    chk('目标输入行紧跟 Hero 之后 / 可展开可收起',
        r.get('uiTwRowUnderHero') and r.get('uiTwOpens51') and r.get('uiTwCloses51'))
    chk('v2.7.51 注入块无异常', not r.get('uiErr51'), r.get('uiErr51'))

    # ===== v2.7.52：Hero 排版 / 单边柱趋势 / 评级 Hero 化 / tab 顺序与彩色交易图标 =====
    chk('账户总览红色氛围光已删（.hero::after 无内容）', r.get('ui52NoGlow'))
    chk('止盈进度大数字 44px + 字距收紧（-2.4px）',
        r.get('ui52NumSize') == '44px' and r.get('ui52NumSpacing') == '-2.4px',
        str(r.get('ui52NumSize')) + ' / ' + str(r.get('ui52NumSpacing')))
    chk('右侧「止盈进度 · 已盈 +x kg」右对齐（v2.7.53 回到一条线）',
        r.get('ui52CapOneLine') and r.get('ui52CapRight'),
        str(r.get('ui52CapOneLine')) + ' / ' + str(r.get('ui52CapRight')))
    chk('净热量趋势柱全部贴同一条基线向上生长（单边柱，不再 0 轴上下分叉）',
        r.get('ui52BarsBaseline'), r.get('ui52BarCount'))
    chk('趋势柱只有绿(缺口 #00c896)/红(超额 #ff3b47)两色',
        r.get('ui52BarColors') == '#00c896,#ff3b47', r.get('ui52BarColors'))
    chk('趋势柱长短随数值变化（非等长柱）', (r.get('ui52BarHeights') or 0) > 1, r.get('ui52BarHeights'))
    chk('持仓评级升格 Hero 款（.hero.hr-hero + 去边框）',
        r.get('ui52HrHero') and r.get('ui52HrNoCard'))
    chk('评级名升为大字（≥26px）', r.get('ui52HrGradeBig'), r.get('ui52HrGradeText'))
    chk('体脂/BMI 提到右上角且描述行不再重复读数',
        (r.get('ui52HrFat') or '').endswith('%') and bool(r.get('ui52HrBmi')) and r.get('ui52HrDescNoDup'),
        str(r.get('ui52HrFat')) + ' / ' + str(r.get('ui52HrBmi')))
    chk('顶部标签不再重复评级名', r.get('ui52HrNoDupName'))
    chk('tab 顺序 = 行情/持仓/交易/龙虎榜/我的（交易居中）',
        r.get('ui52TabOrder') == 'market,holdings,trade,leaderboard,profile', r.get('ui52TabOrder'))
    chk('交易图标为彩色矢量（鸡腿橙肉 + 奶白骨头 + 钢蓝哑铃，非线稿）',
        r.get('ui52TradeIconColorful') and r.get('ui52TradeIconTag') == 'svg', r.get('ui52TradeIconTag'))
    chk('其余 4 个 tab 图标保持线性同款', r.get('ui52OtherIconsLine') == 4, r.get('ui52OtherIconsLine'))
    chk('v2.7.52 注入块无异常', not r.get('uiErr52'), r.get('uiErr52'))

    # ===== v2.7.53：大数字排版 / 进度一条线 / 趋势周期+横滑 / 名次分色 / 图标翻转 =====
    chk('大数字拆成 整数位+小数位+% 三段（v2.7.53）',
        r.get('ui53HasSeg'), str(r.get('ui53IvSize')) + ' / ' + str(r.get('ui53DecSize')))
    chk('小数点后数字降一档（30px < 44px）', r.get('ui53DecSmaller'), r.get('ui53DecSize'))
    chk('「%」不再上标（static / 无 top 偏移 / 基线对齐）',
        r.get('ui53PcPos') == 'static' and r.get('ui53PcTop') in ('0px', 'auto')
        and r.get('ui53PcVAlign') == 'baseline',
        str(r.get('ui53PcPos')) + ' / ' + str(r.get('ui53PcTop')) + ' / ' + str(r.get('ui53PcVAlign')))
    chk('「止盈进度 · 已盈 +x kg」回到一条线（不再是两行）',
        r.get('ui53CapOneLine') and r.get('ui53CapNoV')
        and (r.get('ui53CapText') or '').startswith('止盈进度 · 已盈'), r.get('ui53CapText'))
    chk('趋势周期 tab = 7日/月度/年度/全部', r.get('ui53Tabs') == '7d,30d,365d,all', r.get('ui53Tabs'))
    chk('趋势「全部」逐日：100 天记录 → 100 根柱', r.get('ui53AllBars') == 100, r.get('ui53AllBars'))
    chk('趋势装不下 → 横向可滑 + 提示「左右滑动查看」',
        r.get('ui53AllScrollable') and r.get('ui53Hint') == '左右滑动查看',
        str(r.get('ui53AllScrollable')) + ' / ' + str(r.get('ui53Hint')))
    chk('趋势默认贴最右（最新）', r.get('ui53AllAtEnd'))
    chk('趋势「7日」= 7 根柱且无需滚动、无滑动提示',
        r.get('ui53SevenBars') == 7 and r.get('ui53SevenNoScroll') and r.get('ui53SevenHint') == '',
        str(r.get('ui53SevenBars')) + ' / noScroll=' + str(r.get('ui53SevenNoScroll')))
    chk('趋势「月度」按自然月聚合（100 天 → 4 个月）+ 副标题标「取日均」',
        r.get('ui53MonthBars') == 4 and '取日均' in (r.get('ui53MonthSub') or ''),
        str(r.get('ui53MonthBars')) + ' / ' + str(r.get('ui53MonthSub')))
    chk('趋势「年度」按自然年聚合（本年 1 根）+ 同样标「取日均」',
        r.get('ui53YearBars') == 1 and '取日均' in (r.get('ui53YearSub') or ''),
        str(r.get('ui53YearBars')) + ' / ' + str(r.get('ui53YearSub')))
    chk('名次徽章三档分色：1 最深 → 3 最浅（亮度递增）',
        r.get('ui53RankRamp') is True, r.get('ui53RankLums'))
    chk('食物榜红系 / 运动榜绿系（色相分开）', r.get('ui53RankHue') is True,
        str(r.get('ui53FoodR1')) + ' vs ' + str(r.get('ui53ExR1')))
    chk('月榜 5 张卡全部带上分色标记类', r.get('ui53RankCount') == 5, r.get('ui53RankCount'))
    chk('交易图标：鸡腿翻转（骨节落到右下 cy=19.15）+ 外框 scale 1.18',
        r.get('ui53IconFlip'), str(r.get('ui53IconG')))
    chk('v2.7.53 注入块无异常', not r.get('uiErr53'), r.get('uiErr53'))

    # ===== v2.7.54：底栏等宽列 / 数值收紧 / 目标琥珀 / 评级卡右对齐 =====
    chk('底栏 5 格等宽（不再 space-around 按项分配）→ 宽度',
        r.get('ui54EvenWidth') is True, r.get('ui54TabWidths'))
    chk('底栏图标中心严格等距 → 间距',
        r.get('ui54EvenGaps') is True, r.get('ui54Gaps') + '  centers=' + str(r.get('ui54TabCenters')))
    chk('交易图标落在底栏几何中心（±0.6px）',
        r.get('ui54TradeOnCenter') is True, str(r.get('ui54TradeOffPx')) + ' px')
    chk('交易图标框宽 == 其余图标框宽（v2.7.52 那条无效的 23px 已删）',
        r.get('ui54IconBoxW') == r.get('ui54IconBoxWRef') == '22px',
        str(r.get('ui54IconBoxW')) + ' vs ' + str(r.get('ui54IconBoxWRef')))
    chk('Hero 右侧「+x kg」字号收小（< 16px）', r.get('ui54CapSmaller') is True, r.get('ui54CapSize'))
    chk('Hero 右侧「+x kg」负字距 + 负词距（等宽字体的松字距已收紧）',
        r.get('ui54CapTight') is True,
        str(r.get('ui54CapSpacing')) + ' / ' + str(r.get('ui54CapWordSpacing')))
    chk('「止盈进度 · 已盈 +x kg」仍是一条线、底部对齐',
        r.get('ui54CapOneLine') is True)
    chk('「+x kg」不再上标（vertical-align 为 baseline）',
        r.get('ui54CapNoSuperscript') is True)
    chk('止盈目标数值为琥珀 #ff9f43 且带 .tgt 类',
        r.get('ui54TgtAmber') is True, r.get('ui54TgtColor'))
    chk('止盈目标与 Hero「距止盈目标 还差」同色（目标类数据统一）',
        r.get('ui54TgtSameAsRemain') is True, r.get('ui54TgtColor'))
    chk('缺口评级三卡 text-align 全为 right（含 .v 与 .l）',
        r.get('ui54GapRight') is True, r.get('ui54GapAlign'))
    chk('缺口评级卡数字与文字右边缘齐平（真的贴右，不是左对齐）',
        r.get('ui54GapFlush') is True and r.get('ui54GapNotLeft') is True, r.get('ui54GapTextRight'))
    chk('v2.7.54 注入块无异常', not r.get('uiErr54'), r.get('uiErr54'))

    # ===== v2.7.55：行情页右上角「↺ 重置」按钮已删除 =====
    chk('行情页头部只剩 logo（重置按钮不在头里了）',
        r.get('ui55LogoOnly') is True, r.get('ui55HdrKids'))
    chk('行情页头部已无 .reset 节点', r.get('ui55HasResetInHdr') is False, r.get('ui55HasResetInHdr'))
    chk('全文档已无任何 .reset 节点', r.get('ui55ResetNodes') == 0, r.get('ui55ResetNodes'))
    chk('resetAll 已从全局删除（就算误触也没得清）', r.get('ui55ResetFnGone') is True)
    chk('行情页头部可点击元素只剩头像（openProfileEdit）',
        r.get('ui55HdrOnclicks') == 1, r.get('ui55HdrOnclickWhat'))
    chk('v2.7.55 注入块无异常', not r.get('uiErr55'), r.get('uiErr55'))

    # ===== v2.7.47：账户总览 / 复盘周报月报 / 数据迁移口 =====
    chk('账户总览卡片已渲染（v2.7.47）', r.get('acctExists'))
    chk('账户总览主数字为「止盈进度」（有上限的 %，v2.7.48）',
        (r.get('acctRate') or '') == '29.4%',
        r.get('acctRate'))
    chk('账户总览不再上屏「上限 xx kg」（v2.7.50 用户要求删除）',
        '上限' not in (r.get('acctCap') or '') and '止盈进度' in (r.get('acctCap') or ''), r.get('acctCap'))
    chk('账户总览进度条宽度 = 止盈进度',
        (r.get('acctBarW') or '') == '29.4%', r.get('acctBarW'))
    chk('账户总览盈利时用红(up)——减重即浮盈', 'up' in (r.get('acctRateClass') or ''), r.get('acctRateClass'))
    chk('账户总览三格（成本/市值/止盈目标）均有值',
        len([x for x in (r.get('acctCells') or '').split('|') if x and x != '--']) == 3,
        r.get('acctCells'))
    chk('账户总览状态标显示「浮盈中」', '浮盈中' in (r.get('acctState') or ''), r.get('acctState'))
    chk('抵达止盈价时封顶 100% 且标「已止盈」',
        (r.get('acctRateDone') or '') == '100.0%' and '已止盈' in (r.get('acctStateDone') or ''),
        (r.get('acctRateDone') or '') + ' / ' + (r.get('acctStateDone') or ''))
    chk('体重远低于止盈价也绝不超 100%（盈利有上限，v2.7.48）',
        (r.get('acctRateOver') or '') == '100.0%', r.get('acctRateOver'))
    chk('复盘模块挂在龙虎榜 lb-content 之后', r.get('rvAfterLb'))
    chk('周视图复盘标题为「复盘周报」', r.get('rvWeekTitle'))
    chk('复盘三宫格齐备（做多最狠/做空之王/缺口达标）', r.get('rvWeekCells'))
    chk('复盘显示缺口达标天数 x / y', r.get('rvWeekHit'))
    chk('复盘含迷你趋势线 SVG', r.get('rvWeekSvg'))
    chk('复盘有「复制战绩」按钮', r.get('rvHasCopy'))
    chk('复制战绩文案含品牌落款', r.get('rvText'))
    chk('月视图复盘标题为「复盘月报」', r.get('rvMonthTitle'))
    chk('数据备份有「复制迁移码」按钮', r.get('migBtn1'))
    chk('数据备份有「粘贴导入」按钮', r.get('migBtn2'))
    chk('粘贴导入弹层 + 文本框存在', r.get('migSheet'))
    chk('导出载荷带 __app / __schema / state',
        r.get('migApp') == 'fitness-trader' and r.get('migSchema') == 1 and r.get('migHasState'),
        str(r.get('migApp')) + ' / ' + str(r.get('migSchema')))
    chk('迁移链兼容新版存档（带元信息）', r.get('migNew'))
    chk('迁移链兼容旧版裸 state（向后兼容）', r.get('migOld'))
    chk('迁移链拒绝来自更高版本的存档', r.get('migReject'))
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
