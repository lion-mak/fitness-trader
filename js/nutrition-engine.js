/* ============================================================
 * NutritionEngine —— 纯计算引擎
 *
 * 设计原则：
 *   1. 不依赖任何食物数据，只吃「档案 + 数值」，便于单独替换数据源或复用
 *   2. 所有输出都带 单位、所用公式、误差范围
 *   3. 档案缺失字段一律降级取默认值，绝不报错 / 绝不返回 NaN 或空值，
 *      并在 missing / advice 里说明用了什么默认值、建议补什么
 *
 * 公式出处：
 *   - Mifflin-St Jeor (1990)  人群通用，误差约 ±10%
 *   - Katch-McArdle           需体脂率，误差约 ±5%～8%，更准
 *   - Harris-Benedict (1984 修订版) 老公式，作为交叉校验，误差约 ±10%～15%
 *   - Tanaka (2001) 最大心率 = 208 - 0.7 × 年龄
 *   - Keytel (2005) 由心率推算能耗，误差约 ±10%～20%
 *   - MET 法：ACSM 公式 kcal = MET × 3.5 × 体重(kg) / 200 × 分钟
 * ============================================================ */
var NutritionEngine = (function () {
  'use strict';

  /* ---------- 常量 ---------- */

  // 日常活动水平（PAL：体力活动系数）
  var ACTIVITY_LEVELS = [
    { id: 'sedentary', name: '久坐', pal: 1.20, desc: '办公室为主，几乎不额外运动' },
    { id: 'light', name: '轻度活动', pal: 1.375, desc: '每周轻度运动 1～3 天' },
    { id: 'moderate', name: '中度活动', pal: 1.55, desc: '每周中等强度运动 3～5 天' },
    { id: 'active', name: '高度活动', pal: 1.725, desc: '每周高强度运动 6～7 天' },
    { id: 'athlete', name: '极高活动', pal: 1.90, desc: '体力劳动或每日两次训练' }
  ];

  // 运动强度系数（在 MET 基础上微调）
  var INTENSITY = {
    '低': 0.80,
    '中': 1.00,
    '高': 1.25
  };

  // 档案字段默认值（降级用）
  var DEFAULTS = {
    gender: 'male',
    age: 30,
    height: 170,
    weight: 65,
    bodyFat: null,     // 可选，无默认，缺失时退回 Mifflin
    restingHr: 70,     // 可选，缺失时用 70 bpm 参与心率校正
    activity: 'sedentary'
  };

  // 字段合理区间，用于校验与提示
  var RANGES = {
    age: [10, 100], height: [100, 230], weight: [25, 250],
    bodyFat: [3, 60], restingHr: [35, 120]
  };

  /* ---------- 工具 ---------- */

  function num(v, fallback) {
    var n = parseFloat(v);
    return (isFinite(n) && n > 0) ? n : fallback;
  }

  function clamp(v, min, max) { return Math.min(Math.max(v, min), max); }

  function round(v, digits) {
    var p = Math.pow(10, digits || 0);
    return Math.round(v * p) / p;
  }

  function findActivity(id) {
    for (var i = 0; i < ACTIVITY_LEVELS.length; i++) {
      if (ACTIVITY_LEVELS[i].id === id) return ACTIVITY_LEVELS[i];
    }
    return ACTIVITY_LEVELS[0];
  }

  /* ---------- 档案归一化（降级核心） ---------- */

  /**
   * 把任意残缺档案补全成可用档案。
   * @param {Object} raw 例如 {gender:'male', age:30, weight:72.8}
   * @returns {Object} { profile, missing:[], usedDefaults:{}, advice:[], valid:Boolean }
   */
  function normalizeProfile(raw) {
    raw = raw || {};
    var missing = [];
    var usedDefaults = {};
    var advice = [];

    var gender = (raw.gender === 'female') ? 'female' : 'male';
    if (!raw.gender) { missing.push('gender'); usedDefaults.gender = DEFAULTS.gender; advice.push('未填性别，按「男」计算'); }

    var age = num(raw.age, null);
    if (age === null) {
      age = DEFAULTS.age; missing.push('age'); usedDefaults.age = age;
      advice.push('未填年龄，按 ' + age + ' 岁估算');
    } else {
      age = Math.round(clamp(age, RANGES.age[0], RANGES.age[1]));
    }

    var height = num(raw.height, null);
    if (height === null) {
      height = gender === 'female' ? 160 : 172;
      missing.push('height'); usedDefaults.height = height;
      advice.push('未填身高，按 ' + height + ' cm 估算');
    } else {
      height = clamp(height, RANGES.height[0], RANGES.height[1]);
    }

    var weight = num(raw.weight, null);
    if (weight === null) {
      weight = gender === 'female' ? 55 : 65;
      missing.push('weight'); usedDefaults.weight = weight;
      advice.push('未填体重，按 ' + weight + ' kg 估算');
    } else {
      weight = clamp(weight, RANGES.weight[0], RANGES.weight[1]);
    }

    // 体脂率：可选。缺失不影响计算，只是用不了 Katch-McArdle
    var bodyFat = num(raw.bodyFat, null);
    if (bodyFat !== null) bodyFat = clamp(bodyFat, RANGES.bodyFat[0], RANGES.bodyFat[1]);
    else advice.push('未填体脂率，只能使用 Mifflin-St Jeor 公式（填了可用更准的 Katch-McArdle）');

    // 静息心率：可选。缺省 70 仅用于心率校正
    var restingHr = num(raw.restingHr, null);
    if (restingHr !== null) restingHr = Math.round(clamp(restingHr, RANGES.restingHr[0], RANGES.restingHr[1]));
    else advice.push('未填静息心率，心率校正时按 70 bpm 计');

    var activity = findActivity(raw.activity);
    if (!raw.activity) {
      missing.push('activity'); usedDefaults.activity = activity.id;
      advice.push('未填日常活动水平，按「' + activity.name + '」计算');
    }

    var profile = {
      gender: gender, age: age, height: height, weight: weight,
      bodyFat: bodyFat, restingHr: restingHr,
      activity: activity.id, activityName: activity.name, pal: activity.pal
    };

    return {
      profile: profile,
      missing: missing,
      usedDefaults: usedDefaults,
      advice: advice,
      valid: missing.length === 0
    };
  }

  /* ---------- 基础代谢率 BMR ---------- */

  function bmrMifflin(p) {
    var base = 10 * p.weight + 6.25 * p.height - 5 * p.age;
    return round(base + (p.gender === 'male' ? 5 : -161));
  }

  function bmrKatch(p) {
    var lbm = p.weight * (1 - p.bodyFat / 100);
    return round(370 + 21.6 * lbm);
  }

  function bmrHarris(p) {
    var v = p.gender === 'male'
      ? 13.397 * p.weight + 4.799 * p.height - 5.677 * p.age + 88.362
      : 9.247 * p.weight + 3.098 * p.height - 4.330 * p.age + 447.593;
    return round(v);
  }

  /**
   * 基础代谢率。优先用 Katch-McArdle（有体脂率时更准），否则 Mifflin-St Jeor。
   * @returns {Object} { value, unit:'kcal/天', lbm, formulas:[{key,name,value,error}], primary, error, note }
   */
  function bmr(profile) {
    var n = normalizeProfile(profile);
    var p = n.profile;

    var formulas = [];
    formulas.push({
      key: 'mifflin', name: 'Mifflin-St Jeor (1990)', value: bmrMifflin(p),
      error: '±10%', formula: p.gender === 'male'
        ? '10×体重 + 6.25×身高 − 5×年龄 + 5'
        : '10×体重 + 6.25×身高 − 5×年龄 − 161'
    });
    formulas.push({
      key: 'harris', name: 'Harris-Benedict (1984 修订)', value: bmrHarris(p),
      error: '±10%～15%', formula: '交叉校验用，不作主值'
    });

    var primary = 'mifflin';
    if (p.bodyFat !== null) {
      formulas.unshift({
        key: 'katch', name: 'Katch-McArdle', value: bmrKatch(p),
        error: '±5%～8%', formula: '370 + 21.6 × 去脂体重(LBM)'
      });
      primary = 'katch';
    }

    var chosen = null;
    for (var i = 0; i < formulas.length; i++) {
      if (formulas[i].key === primary) { chosen = formulas[i]; break; }
    }

    return {
      value: chosen.value,
      unit: 'kcal/天',
      primary: primary,
      primaryName: chosen.name,
      error: chosen.error,
      lbm: p.bodyFat !== null ? round(p.weight * (1 - p.bodyFat / 100), 1) : null,
      formulas: formulas,
      missing: n.missing,
      advice: n.advice,
      note: p.bodyFat !== null
        ? '已填写体脂率，采用更准的 Katch-McArdle 公式'
        : '未填体脂率，采用通用的 Mifflin-St Jeor 公式'
    };
  }

  /* ---------- 每日总消耗 TDEE ---------- */

  /**
   * 每日总能量消耗 = BMR × 活动系数（PAL）
   * @returns {Object} { value, unit, bmr, pal, activityName, error, formula, advice }
   */
  function tdee(profile) {
    var b = bmr(profile);
    var n = normalizeProfile(profile);
    var p = n.profile;
    var act = findActivity(p.activity);
    var value = Math.round(b.value * act.pal);

    return {
      value: value,
      unit: 'kcal/天',
      bmr: b.value,
      bmrFormula: b.primaryName,
      bmrError: b.error,
      pal: act.pal,
      activityName: act.name,
      activityDesc: act.desc,
      error: '±15%～20%（活动系数本身主观性较强）',
      formula: 'TDEE = BMR × 活动系数(PAL ' + act.pal + ')',
      advice: n.advice
    };
  }

  /* ---------- 运动消耗 ---------- */

  /**
   * 由 MET 计算消耗：kcal = MET × 3.5 × 体重(kg) / 200 × 分钟 × 强度系数
   */
  function kcalByMet(met, minutes, weight, intensity) {
    var coef = INTENSITY[intensity] || 1.0;
    return Math.round(met * 3.5 * weight / 200 * minutes * coef);
  }

  /**
   * 由平均心率计算消耗：Keytel (2005) 公式
   *   男：kcal/min = (−55.0969 + 0.6309×HR + 0.1988×体重 + 0.2017×年龄) / 4.184
   *   女：kcal/min = (−20.4022 + 0.4472×HR − 0.1263×体重 + 0.074×年龄) / 4.184
   */
  function kcalByHr(avgHr, minutes, p) {
    var perMin = p.gender === 'male'
      ? (-55.0969 + 0.6309 * avgHr + 0.1988 * p.weight + 0.2017 * p.age) / 4.184
      : (-20.4022 + 0.4472 * avgHr - 0.1263 * p.weight + 0.074 * p.age) / 4.184;
    if (perMin < 0) perMin = 0;
    return Math.round(perMin * minutes);
  }

  /**
   * 运动消耗计算。
   * @param {Object} opt { profile, met, minutes, intensity, avgHr }
   * @returns {Object} { kcal, unit, method, metKcal, hrKcal, formula, error, note, hrMax, hrrPercent }
   */
  function exercise(opt) {
    opt = opt || {};
    var n = normalizeProfile(opt.profile);
    var p = n.profile;

    var minutes = num(opt.minutes, 30);
    var met = num(opt.met, 5);
    var intensity = INTENSITY[opt.intensity] ? opt.intensity : '中';
    var avgHr = num(opt.avgHr, null);

    var metKcal = kcalByMet(met, minutes, p.weight, intensity);

    var hrKcal = null, hrMax = null, hrrPercent = null, note = '';
    if (avgHr !== null) {
      hrKcal = kcalByHr(avgHr, minutes, p);
      hrMax = Math.round(208 - 0.7 * p.age);           // Tanaka 公式
      var rest = p.restingHr || DEFAULTS.restingHr;
      var hrr = hrMax - rest;
      hrrPercent = hrr > 0 ? round(clamp((avgHr - rest) / hrr * 100, 0, 100), 0) : null;
      if (p.restingHr === null) note = '静息心率按 70 bpm 估算';
    }

    var kcal, method, error;
    if (hrKcal !== null) {
      kcal = hrKcal; method = 'hr';
      error = '±10%～20%（心率法，比 MET 法更个性化）';
      note = (note ? note + '；' : '') + '已用平均心率校正';
    } else {
      kcal = metKcal; method = 'met';
      error = '±20%～30%（MET 法为群体平均，个体差异较大）';
      note = '未填平均心率，按 MET 法估算';
    }

    return {
      kcal: kcal,
      unit: 'kcal',
      method: method,
      metKcal: metKcal,
      hrKcal: hrKcal,
      hrMax: hrMax,
      hrrPercent: hrrPercent,
      minutes: minutes,
      met: met,
      intensity: intensity,
      profile: p,
      error: error,
      note: note,
      advice: n.advice,
      formula: method === 'hr'
        ? 'Keytel(2005)：kcal/min = (−55.0969 + 0.6309×HR + 0.1988×体重 + 0.2017×年龄) ÷ 4.184（男）'
        : 'ACSM：kcal = MET × 3.5 × 体重(kg) ÷ 200 × 分钟 × 强度系数(' + (INTENSITY[intensity] || 1) + ')'
    };
  }

  /* ---------- 食物营养（把每100g口径换算成实际摄入） ---------- */

  /**
   * @param {Object} food 食物记录（kcal/p/f/c/fb 均为每 100g 或每 100ml）
   * @param {Number} grams 实际克重或毫升数
   * @returns {Object} { kcal, p, f, c, fb, grams }
   */
  function food(food, grams) {
    if (!food) return { kcal: 0, p: 0, f: 0, c: 0, fb: 0, grams: 0 };
    var g = num(grams, num(food.gram, 100));
    var k = g / 100;
    return {
      kcal: Math.round(num(food.kcal, 0) * k),
      p: round(num(food.p, 0) * k, 1),
      f: round(num(food.f, 0) * k, 1),
      c: round(num(food.c, 0) * k, 1),
      fb: round(num(food.fb, 0) * k, 1),
      grams: g
    };
  }

  /**
   * 汇总一组食物记录。
   * @param {Array} items [{food, grams}]
   */
  function sumFoods(items) {
    var t = { kcal: 0, p: 0, f: 0, c: 0, fb: 0 };
    (items || []).forEach(function (it) {
      var v = food(it.food, it.grams);
      t.kcal += v.kcal; t.p += v.p; t.f += v.f; t.c += v.c; t.fb += v.fb;
    });
    t.p = round(t.p, 1); t.f = round(t.f, 1); t.c = round(t.c, 1); t.fb = round(t.fb, 1);
    return t;
  }

  /* ---------- 目标热量建议 ---------- */

  /**
   * 依据 TDEE 与目标（减重/维持/增重）给出每日摄入建议。
   * @param {Number} deficitOrSurplus 负数=制造缺口（减重），0=维持，正数=盈余（增重）
   */
  function targetIntake(profile, deficitOrSurplus) {
    var t = tdee(profile);
    var delta = num(deficitOrSurplus, 0);
    var value = Math.max(1200, Math.round(t.value + delta));
    return {
      value: value,
      unit: 'kcal/天',
      tdee: t.value,
      delta: delta,
      error: t.error,
      formula: '目标摄入 = TDEE(' + t.value + ') + (' + delta + ')',
      note: delta < 0
        ? '每日约 ' + Math.abs(delta) + ' kcal 缺口，理论每周减重 ' + round(Math.abs(delta) * 7 / 7700, 2) + ' kg'
        : (delta > 0 ? '每日约 ' + delta + ' kcal 盈余' : '维持体重'),
      bmr: t.bmr,
      bmrFormula: t.bmrFormula
    };
  }

  /* ---------- 对外接口 ---------- */

  return {
    ACTIVITY_LEVELS: ACTIVITY_LEVELS,
    INTENSITY: INTENSITY,
    DEFAULTS: DEFAULTS,
    RANGES: RANGES,
    normalizeProfile: normalizeProfile,
    bmr: bmr,
    tdee: tdee,
    exercise: exercise,
    food: food,
    sumFoods: sumFoods,
    targetIntake: targetIntake
  };
})();
