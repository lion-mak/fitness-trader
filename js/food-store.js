/* ============================================================
 * FoodStore —— 食物数据访问层
 *
 * 设计原则：
 *   1. 与计算逻辑完全解耦：NutritionEngine 不认识 FoodStore，FoodStore 不做热量计算
 *   2. 数据源可替换：默认从 data/foods.json 懒加载；日后换成远端 API，
 *      只需把 loadRemote() 换成 fetch(url) 返回同样结构的 JSON 即可，上层无感
 *   3. 降级不报错：加载失败（如 file:// 打开、离线）时回退到内置精简库，
 *      仍然能搜索、能记录，并在 status 里说明当前用的是哪套数据
 *   4. 支持用户自建食物：存 localStorage，src 标记为 custom
 *
 * 数据结构（每条）：
 *   { id, name, alias[], cat, kcal, p, f, c, fb, alc,
 *     unit, qty, gram, conv[{label,gram}], py, ini, src, basis, recipe?, yield_g? }
 *   其中 kcal/p/f/c/fb/alc 均为「每 100 克（或 100 毫升）可食部」口径
 * ============================================================ */
var FoodStore = (function () {
  'use strict';

  var DATA_URL = 'data/foods.json';
  var PY_URL = 'data/py-initials.json';
  var CUSTOM_KEY = 'jianpan_custom_foods_v1';

  var foods = [];        // 全量（库 + 自建）
  var index = [];        // 检索索引
  var meta = null;
  var pyMap = {};        // 汉字 → 拼音首字母
  var status = { state: 'idle', source: 'none', count: 0, error: null };
  var loadingPromise = null;

  /* ---------- 离线降级用的精简库（约 30 条常见食物，每 100g 口径） ---------- */
  var FALLBACK = [
    { name: '米饭', alias: ['白米饭', '饭'], cat: '主食', kcal: 116, p: 2.6, f: 0.3, c: 25.9, fb: 0.3, unit: '碗', qty: 1, gram: 150, src: 'table', basis: '100g' },
    { name: '馒头', alias: ['白馒头'], cat: '主食', kcal: 223, p: 7.0, f: 1.1, c: 47.0, fb: 1.3, unit: '个', qty: 1, gram: 100, src: 'table', basis: '100g' },
    { name: '面条(煮)', alias: ['煮面'], cat: '主食', kcal: 137, p: 4.5, f: 0.4, c: 27.7, fb: 0.4, unit: '碗', qty: 1, gram: 200, src: 'table', basis: '100g' },
    { name: '鸡蛋', alias: ['鸡子'], cat: '肉蛋', kcal: 144, p: 13.3, f: 8.8, c: 2.8, fb: 0, unit: '个', qty: 1, gram: 50, src: 'table', basis: '100g' },
    { name: '鸡胸肉', alias: ['鸡胸'], cat: '肉蛋', kcal: 118, p: 24.6, f: 1.9, c: 2.5, fb: 0, unit: '块', qty: 1, gram: 120, src: 'table', basis: '100g' },
    { name: '猪肉(瘦)', alias: ['瘦肉'], cat: '肉蛋', kcal: 143, p: 20.3, f: 6.2, c: 1.5, fb: 0, unit: '份', qty: 1, gram: 100, src: 'table', basis: '100g' },
    { name: '牛肉(瘦)', alias: ['牛瘦肉'], cat: '肉蛋', kcal: 106, p: 20.2, f: 2.3, c: 1.2, fb: 0, unit: '份', qty: 1, gram: 100, src: 'table', basis: '100g' },
    { name: '北豆腐', alias: ['老豆腐'], cat: '豆奶', kcal: 98, p: 12.2, f: 4.8, c: 1.5, fb: 0.5, unit: '块', qty: 1, gram: 200, src: 'table', basis: '100g' },
    { name: '牛奶(全脂)', alias: ['纯牛奶'], cat: '豆奶', kcal: 65, p: 3.3, f: 3.6, c: 4.9, fb: 0, unit: '盒', qty: 1, gram: 250, src: 'table', basis: '100ml' },
    { name: '苹果', alias: [], cat: '蔬果', kcal: 54, p: 0.2, f: 0.2, c: 13.5, fb: 1.2, unit: '个', qty: 1, gram: 200, src: 'table', basis: '100g' },
    { name: '香蕉', alias: [], cat: '蔬果', kcal: 93, p: 1.4, f: 0.2, c: 22.0, fb: 1.2, unit: '根', qty: 1, gram: 120, src: 'table', basis: '100g' },
    { name: '番茄', alias: ['西红柿'], cat: '蔬果', kcal: 20, p: 0.9, f: 0.2, c: 4.0, fb: 0.5, unit: '个', qty: 1, gram: 150, src: 'table', basis: '100g' },
    { name: '黄瓜', alias: ['青瓜'], cat: '蔬果', kcal: 16, p: 0.8, f: 0.2, c: 2.9, fb: 0.5, unit: '根', qty: 1, gram: 200, src: 'table', basis: '100g' },
    { name: '土豆', alias: ['马铃薯'], cat: '蔬果', kcal: 76, p: 2.0, f: 0.2, c: 17.2, fb: 1.1, unit: '个', qty: 1, gram: 150, src: 'table', basis: '100g' },
    { name: '西兰花', alias: [], cat: '蔬果', kcal: 36, p: 4.1, f: 0.6, c: 4.3, fb: 1.6, unit: '份', qty: 1, gram: 150, src: 'table', basis: '100g' },
    { name: '番茄炒蛋', alias: ['西红柿炒鸡蛋'], cat: '家常', kcal: 76, p: 6.1, f: 4.6, c: 3.4, fb: 0.6, unit: '份', qty: 1, gram: 340, src: 'calc', basis: '100g' },
    { name: '食用油', alias: ['植物油'], cat: '油脂', kcal: 899, p: 0, f: 99.9, c: 0, fb: 0, unit: '勺', qty: 1, gram: 10, src: 'table', basis: '100g' },
    { name: '白砂糖', alias: ['砂糖'], cat: '调味', kcal: 400, p: 0, f: 0, c: 99.9, fb: 0, unit: '勺', qty: 1, gram: 8, src: 'table', basis: '100g' },
    { name: '可乐', alias: [], cat: '饮品', kcal: 43, p: 0, f: 0, c: 10.8, fb: 0, unit: '罐', qty: 1, gram: 330, src: 'brand', basis: '100ml' },
    { name: '薯片', alias: [], cat: '零食', kcal: 548, p: 6.0, f: 35.0, c: 52.0, fb: 4.0, unit: '包', qty: 1, gram: 70, src: 'brand', basis: '100g' }
  ];

  /* ---------- 自建食物（localStorage） ---------- */

  function loadCustom() {
    try {
      var raw = localStorage.getItem(CUSTOM_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr : [];
    } catch (e) { return []; }
  }

  function saveCustom(list) {
    try { localStorage.setItem(CUSTOM_KEY, JSON.stringify(list)); } catch (e) {}
  }

  /* ---------- 拼音（自建食物用） ---------- */

  function initialsOf(text) {
    var out = '';
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      out += pyMap[ch] || (/[a-zA-Z0-9]/.test(ch) ? ch.toLowerCase() : '');
    }
    return out;
  }

  /* ---------- 索引 ---------- */

  function buildIndex() {
    index = foods.map(function (f, i) {
      var alias = f.alias || [];
      var iniStr = (f.ini || '').replace(/\s+/g, '');
      var pyStr = (f.py || '').replace(/\s+/g, '');
      if (!iniStr) iniStr = initialsOf(f.name);
      return {
        i: i, f: f,
        name: f.name,
        nameL: String(f.name).toLowerCase(),
        aliasL: alias.map(function (a) { return String(a).toLowerCase(); }),
        cat: f.cat || '',
        ini: iniStr,
        py: pyStr,
        custom: f.src === 'custom'
      };
    });
  }

  function rebuild() {
    foods = loadCustom().concat(foods.filter(function (f) { return f.src !== 'custom'; }));
    buildIndex();
    status.count = foods.length;
  }

  /* ---------- 加载 ---------- */

  function fetchJson(url) {
    return fetch(url, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function applyData(json) {
    meta = json.meta || null;
    var list = (json.foods || []).slice();
    // 自建食物排在最前，便于优先命中
    var custom = loadCustom();
    foods = custom.concat(list);
    buildIndex();
    status.state = 'ready';
    status.source = 'json';
    status.count = foods.length;
    return status;
  }

  /**
   * 懒加载食物库。可重复调用，返回同一个 Promise。
   * 失败时降级到内置精简库，不抛异常。
   */
  function load() {
    if (status.state === 'ready' || loadingPromise) return loadingPromise || Promise.resolve(status);

    loadingPromise = Promise.all([
      fetchJson(DATA_URL),
      fetchJson(PY_URL).catch(function () { return {}; })   // 拼音表缺失不影响主流程
    ]).then(function (res) {
      pyMap = res[1] || {};
      return applyData(res[0]);
    }).catch(function (err) {
      // 降级：用内置精简库，保证功能可用
      foods = loadCustom().concat(FALLBACK.map(function (f, i) {
        var c = JSON.parse(JSON.stringify(f));
        c.id = 'fb' + (i + 1);
        c.alc = c.alc || 0;
        c.conv = c.conv || [];
        c.py = ''; c.ini = '';
        return c;
      }));
      buildIndex();
      status.state = 'ready';
      status.source = 'fallback';
      status.error = String(err && err.message || err);
      status.count = foods.length;
      return status;
    });

    return loadingPromise;
  }

  function ready() { return load(); }

  /* ---------- 检索 ---------- */

  function score(rec, q) {
    var n = rec.name;
    if (n === q) return 100;
    if (rec.nameL.indexOf(q) === 0) return 90;
    if (rec.ini === q) return 88;
    if (rec.ini.indexOf(q) === 0) return 80;
    if (rec.nameL.indexOf(q) > 0) return 70;
    for (var i = 0; i < rec.aliasL.length; i++) {
      var a = rec.aliasL[i];
      if (a === q) return 86;
      if (a.indexOf(q) === 0) return 78;
      if (a.indexOf(q) > 0) return 62;
    }
    if (rec.py.indexOf(q) === 0) return 66;
    if (rec.py.indexOf(q) > 0) return 48;
    if (rec.ini.indexOf(q) > 0) return 46;
    if (rec.cat.indexOf(q) >= 0) return 30;
    return 0;
  }

  /**
   * 搜索。支持：中文名称 / 别名 / 全拼 / 拼音首字母 / 分类
   * @param {String} query
   * @param {Object} opt { limit, cat }
   */
  function search(query, opt) {
    opt = opt || {};
    var limit = opt.limit || 60;
    var q = String(query == null ? '' : query).trim().toLowerCase().replace(/\s+/g, '');

    var pool = index;
    if (opt.cat && opt.cat !== '全部') {
      pool = pool.filter(function (r) { return r.cat === opt.cat; });
    }

    if (!q) {
      return pool.slice(0, limit).map(function (r) { return r.f; });
    }

    var scored = [];
    for (var i = 0; i < pool.length; i++) {
      var s = score(pool[i], q);
      if (s > 0) scored.push({ s: s + (pool[i].custom ? 5 : 0), f: pool[i].f, i: pool[i].i });
    }
    scored.sort(function (a, b) { return b.s - a.s || a.i - b.i; });
    return scored.slice(0, limit).map(function (x) { return x.f; });
  }

  function get(id) {
    for (var i = 0; i < foods.length; i++) if (foods[i].id === id) return foods[i];
    return null;
  }

  function byName(name) {
    for (var i = 0; i < foods.length; i++) if (foods[i].name === name) return foods[i];
    return null;
  }

  function all() { return foods.slice(); }
  function categories() {
    return meta && meta.categories ? Object.keys(meta.categories) : ['主食', '家常', '外卖', '肉蛋', '水产', '蔬果', '豆奶', '坚果', '调味', '包装', '饮品', '零食', '自建'];
  }
  function getMeta() { return meta; }
  function getStatus() { return status; }

  /* ---------- 自建食物 ---------- */

  /**
   * 新增自建食物。
   * @param {Object} data { name, alias, cat, kcal, p, f, c, fb, unit, gram }
   */
  function addCustom(data) {
    var name = String(data.name || '').trim();
    if (!name) return { ok: false, msg: '请填写食物名称' };

    var f = {
      id: 'c' + Date.now(),
      name: name,
      alias: (data.alias || '').split(/[ ,，、]+/).filter(Boolean),
      cat: data.cat || '自建',
      kcal: parseFloat(data.kcal) || 0,
      p: parseFloat(data.p) || 0,
      f: parseFloat(data.f) || 0,
      c: parseFloat(data.c) || 0,
      fb: parseFloat(data.fb) || 0,
      alc: 0,
      unit: data.unit || '份',
      qty: 1,
      gram: parseFloat(data.gram) || 100,
      conv: [],
      basis: '100g',
      src: 'custom'
    };
    f.py = ''; f.ini = initialsOf(name);

    var list = loadCustom();
    list.unshift(f);
    saveCustom(list);
    rebuild();
    return { ok: true, food: f };
  }

  function removeCustom(id) {
    var list = loadCustom().filter(function (f) { return f.id !== id; });
    saveCustom(list);
    rebuild();
  }

  function customFoods() { return foods.filter(function (f) { return f.src === 'custom'; }); }

  /* ---------- 份量换算 ---------- */

  /**
   * 某食物某份量对应的克重。
   * @param {Object} food
   * @param {Number} qty 份量数量
   * @param {String} unit 'unit' 用默认单位，或 'g' 直接按克
   */
  function toGrams(food, qty, unit) {
    if (!food) return 0;
    var q = parseFloat(qty);
    if (!isFinite(q) || q <= 0) q = 1;
    if (unit === 'g') return Math.round(q);
    return Math.round(q * (parseFloat(food.gram) || 100));
  }

  return {
    DATA_URL: DATA_URL,
    load: load,
    ready: ready,
    search: search,
    get: get,
    byName: byName,
    all: all,
    categories: categories,
    getMeta: getMeta,
    getStatus: getStatus,
    addCustom: addCustom,
    removeCustom: removeCustom,
    customFoods: customFoods,
    toGrams: toGrams
  };
})();
