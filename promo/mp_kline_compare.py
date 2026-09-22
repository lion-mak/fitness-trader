# -*- coding: utf-8 -*-
"""
mp_kline_compare.py —— 体重 K 线「PWA 的 SVG 版」vs「小程序 canvas 版」像素对照。

为什么必须做这一步：
    "100% 复刻" 不能靠肉眼 review 代码。K 线有 6 类图元（Y 轴刻度、X 轴标签、
    两条 MA 折线、柱体引线、实体、基线），任何一处的坐标口径写偏一点点，
    在真机上都是"看着差不多但数值对不上"。这里把两版渲染器跑在同一份 mock 数据、
    同一尺寸下截图，逐像素比对。

关键做法：**两边都用真实源码，不手抄副本**
   A 侧（参考）：从 index.html 抽取原版 renderKline()，配一个假 document，
                让它在浏览器里直接跑出 SVG。
   B 侧（被测）：从 pages/market/market.js 抽取 computeGeom()/paint()，
                从 lib/canvas.js 抽取 painter()，组装成 canvas 版。
   辅助函数（aggregateWeight / todayStr …）两边共用 miniprogram/lib/calc.js —— 
   消除"辅助函数口径不同"这个干扰变量。

用法：python promo/mp_kline_compare.py
输出：promo/_kline_cmp.png（左 SVG / 中 canvas / 右差分）
"""
import io, os, re, json, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
MINI = r"E:\WeChatProjects\jianpan\miniprogram"

def read(p):
    return io.open(p, encoding="utf-8", newline="").read()


# ────────────────────────────────────────────────
# JS 块抽取（括号配平；跳过字符串/注释/正则）
# ────────────────────────────────────────────────
class Sc:
    RE_PREV = set("(,=:[!&|?{};+-*%~^<>")
    RE_KW = set("return typeof case in of new delete void instanceof do else yield await".split())

    def __init__(self, s): self.s, self.n = s, len(s)

    def _re_ok(self, i):
        j = i - 1
        while j >= 0 and self.s[j] in " \t\r\n": j -= 1
        if j < 0: return True
        if self.s[j] in self.RE_PREV: return True
        m = re.search(r"([A-Za-z_$][\w$]*)\s*$", self.s[:j + 1])
        return bool(m and m.group(1) in self.RE_KW)

    def skip(self, i):
        s, n = self.s, self.n
        c = s[i]
        if c in "\"'`":
            q, i = c, i + 1
            while i < n:
                if s[i] == "\\": i += 2; continue
                if s[i] == q: return i + 1
                i += 1
            return n
        if c == "/" and i + 1 < n:
            if s[i + 1] == "/":
                j = s.find("\n", i); return n if j < 0 else j
            if s[i + 1] == "*":
                j = s.find("*/", i + 2); return n if j < 0 else j + 2
            if self._re_ok(i):
                i += 1; incls = False
                while i < n:
                    ch = s[i]
                    if ch == "\\": i += 2; continue
                    if ch == "[": incls = True
                    elif ch == "]": incls = False
                    elif ch == "/" and not incls: return i + 1
                    elif ch == "\n": return i
                    i += 1
                return n
        return i

    def block(self, i):
        """i 指向 { ，返回到配平 } 后一位"""
        depth = 0
        while i < self.n:
            j = self.skip(i)
            if j != i: i = j; continue
            c = self.s[i]
            if c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0: return i + 1
            i += 1
        return self.n


def grab_func(src, name):
    """抽 `function name(...) {...}`（顶层）"""
    m = re.search(r"^function\s+" + re.escape(name) + r"\s*\(", src, re.M)
    if not m: raise SystemExit("抽不到函数：" + name)
    b = src.find("{", m.end())
    return src[m.start():Sc(src).block(b)]


def grab_method(src, name):
    """抽对象字面量里的方法 `  name(a,b) {...},`，转成 function 声明"""
    m = re.search(r"^\s{2}" + re.escape(name) + r"\s*\(([^)]*)\)\s*\{", src, re.M)
    if not m: raise SystemExit("抽不到方法：" + name)
    b = src.find("{", m.end() - 1)
    body = src[b:Sc(src).block(b)]
    return "function %s(%s) %s" % (name, m.group(1), body)


# ────────────────────────────────────────────────
# 组装
# ────────────────────────────────────────────────
pwa = read(os.path.join(ROOT, "index.html"))
calc_js = read(os.path.join(MINI, "lib", "calc.js"))
ne_js = read(os.path.join(MINI, "lib", "nutrition-engine.js"))
canvas_js = read(os.path.join(MINI, "lib", "canvas.js"))
market_js = read(os.path.join(MINI, "pages", "market", "market.js"))
calc_js = calc_js.replace("require('./nutrition-engine.js')", "require('nutrition-engine')")

MOCK = json.loads(read(os.path.join(ROOT, "promo", "mock.json")))["state"]
MOCK["klinePeriod"] = "d"

RENDER_KLINE = grab_func(pwa, "renderKline")
GEOM = grab_method(market_js, "computeGeom")
PAINT = grab_method(market_js, "paint")
PAINTER = grab_func(canvas_js, "painter")
ROUNDRECT = grab_func(canvas_js, "roundRectPath")
FONTSTR = grab_func(canvas_js, "fontStr")
HEXA = grab_func(canvas_js, "hexA")

# ⚠️ 模块级常量必须一起注入。
#    第一次跑就因为漏了 W/H/PAD_*/FONT/MONO 而 ReferenceError，
#    结果是 canvas 全空白（截图 100% 背景色）——而"空白"和"画对了"在缩略图上
#    极容易看混，所以这里改成自动抽取全部「大写字母常量」声明，避免再漏。
#    判据：^const 全大写名 = …（market.js 的 store/calc/CV 是小写 require，不会被误抽）
def grab_consts(src):
    out = []
    for m in re.finditer(r"^const\s+([A-Z][A-Z0-9_]*)\s*=", src, re.M):
        st = m.start()
        # 到语句结束（分号在括号深度 0 处）
        sc, i, depth = Sc(src), m.end(), 0
        while i < sc.n:
            j = sc.skip(i)
            if j != i: i = j; continue
            c = src[i]
            if c in "([{": depth += 1
            elif c in ")]}": depth -= 1
            elif c == ";" and depth == 0: i += 1; break
            i += 1
        decl = src[st:i].strip()
        # 排除 require 声明（例如 `const CV = require('../../lib/canvas.js')` 也是大写名，
        # 但它要由宿主提供，注入进来会去调 shim require 而报 unknown module）
        if "require(" in decl:
            continue
        out.append(decl)
    return "\n".join(out)


CONSTS = "\n".join(filter(None, [grab_consts(canvas_js), grab_consts(market_js)]))

# calc.js 当模块加载（浏览器里手工实现 require/module）
LOADER = u"""
var __cache = {};
function require(p) {
  if (__cache[p]) return __cache[p];
  if (p === 'nutrition-engine') {
    var m = { exports: {} };
    (function(module, exports) { %s })(m, m.exports);
    __cache[p] = m.exports; return m.exports;
  }
  if (p === 'calc') {
    var m2 = { exports: {} };
    (function(module, exports, require) { %s })(m2, m2.exports, require);
    __cache[p] = m2.exports; return m2.exports;
  }
  throw new Error('unknown module ' + p);
}
var calc = require('calc');
""" % (ne_js, calc_js)

CARD_W = 319          # 375px 屏下 .card 的内容宽（375 − 左右 margin 28 − padding 28）
CARD_H = 150

CSS_COMMON = u"""
  html,body { margin:0; padding:0; background:#141b2d; }
  #shot { width:%dpx; height:%dpx; background:#141b2d; overflow:hidden; }
  svg { display:block; }
""" % (CARD_W, CARD_H)

# ---- A 侧：PWA 原版 renderKline ----
HTML_A = u"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>%(css)s</style></head>
<body><div id="shot"><div id="kline-host"></div></div>
<script>%(loader)s</script>
<script>
/* 假 document：renderKline 里所有 DOM 操作都被引到这里，
   只有 'kline' 的 innerHTML 真正落地（那是我们要看的东西）。 */
var __fake = {
  getElementById: function(id) {
    var real = (id === 'kline') ? document.getElementById('kline-host') : null;
    return {
      style: {}, dataset: {}, textContent: '', innerHTML: '',
      querySelector: function() { return null; },
      addEventListener: function() {},
      offsetWidth: 0,
      set innerHTML(v) { this._h = v; if (real) real.innerHTML = v; },
      get innerHTML() { return this._h; }
    };
  },
  createElement: function() { return { style:{}, appendChild:function(){}, click:function(){} }; },
  addEventListener: function() {}
};
window.MOCK = %(mock)s;
(function(document){
  state = window.MOCK;                      // renderKline 读全局 state
  %(render)s
  var __realDoc = window.document;
  window.__runA = function() { renderKline(); };
})(__fake);
window.__runA();
</script></body></html>""" % {"css": CSS_COMMON, "loader": LOADER,
                              "mock": json.dumps(MOCK, ensure_ascii=False),
                              "render": RENDER_KLINE}

# ---- B 侧：小程序 canvas 版 ----
HTML_B = u"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>%(css)s</style></head>
<body><div id="shot"><canvas id="cv" width="%(w)s" height="%(h)s"
  style="width:%(w)spx;height:%(h)spx;display:block;"></canvas></div>
<script>%(loader)s</script>
<script>
window.__err = null;
window.onerror = function(m, s, l, c, e) { window.__err = String(m) + ' @L' + l; return false; };
try {
%(consts)s
%(fontstr)s
%(hexa)s
%(roundrect)s
%(painter)s
%(geom)s
%(paint)s

(function(){
  var st = %(mock)s;
  calc.bindState(st);
  var DPR = 2;
  var canvas = document.getElementById('cv');
  canvas.width = %(w)s * DPR; canvas.height = %(h)s * DPR;
  var ctx = canvas.getContext('2d');
  ctx.scale(DPR, DPR);

  /* 复刻 lib/canvas.js 的 fit 行为：设计坐标 340×150 → meet 缩放到实际画布 */
  var s = Math.min(%(w)s / FIT.w, %(h)s / FIT.h);
  var dx = (%(w)s - FIT.w * s) / 2, dy = (%(h)s - FIT.h * s) / 2;
  ctx.translate(dx, dy); ctx.scale(s, s);

  var P = painter(ctx, FIT.w, FIT.h, DPR);
  var page = {                      // 模拟 Page 实例（paint 读 this.geom / this._tipIdx）
    geom: null, _tipIdx: null,
    computeGeom: computeGeom,
    paint: paint
  };
  page.geom = page.computeGeom((st.weightLog || []).slice(), st.klinePeriod || 'd');
  page.paint(P);

  window.__geom = JSON.stringify({
    n: page.geom.n, min: page.geom.min, max: page.geom.max,
    slotW: page.geom.slotW, barW: page.geom.barW,
    firstBar: page.geom.bars[0], lastBar: page.geom.bars[page.geom.bars.length - 1]
  });
})();
} catch (e) { window.__err = String(e && e.stack || e); }
</script></body></html>""" % {"css": CSS_COMMON, "loader": LOADER, "w": CARD_W, "h": CARD_H,
                              "mock": json.dumps(MOCK, ensure_ascii=False),
                              "consts": CONSTS,
                              "fontstr": FONTSTR, "hexa": HEXA, "roundrect": ROUNDRECT,
                              "painter": PAINTER, "geom": GEOM, "paint": PAINT}

pa = os.path.join(HERE, "_kline_a_svg.html")
pb = os.path.join(HERE, "_kline_b_canvas.html")
io.open(pa, "w", encoding="utf-8", newline="").write(HTML_A)
io.open(pb, "w", encoding="utf-8", newline="").write(HTML_B)

# ────────────────────────────────────────────────
# 截图
# ────────────────────────────────────────────────
from playwright.sync_api import sync_playwright
from PIL import Image, ImageChops

LAUNCH = [{"channel": "msedge"},
          {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"}]

shots = {}
geom_info = None
err_a = err_b = None
with sync_playwright() as p:
    b = None
    for kw in LAUNCH:
        try:
            b = p.chromium.launch(**kw); break
        except Exception:
            pass
    if b is None:
        raise SystemExit("无可用浏览器内核")
    page = b.new_page(viewport={"width": 900, "height": 400}, device_scale_factor=3)

    page.goto("file:///" + pa.replace("\\", "/"))
    page.wait_for_timeout(500)
    err_a = page.evaluate("window.__err")
    svg_html = page.locator("#kline-host").inner_html()
    shots["svg"] = page.locator("#shot").screenshot()

    page.goto("file:///" + pb.replace("\\", "/"))
    page.wait_for_timeout(500)
    err_b = page.evaluate("window.__err")
    geom_info = page.evaluate("window.__geom")
    shots["canvas"] = page.locator("#shot").screenshot()
    b.close()

for k, v in shots.items():
    io.open(os.path.join(HERE, "_kline_%s.png" % k), "wb").write(v)

A = Image.open(io.BytesIO(shots["svg"])).convert("RGB")
B = Image.open(io.BytesIO(shots["canvas"])).convert("RGB")
print("A(SVG)   截图 =", A.size, " 运行错误:", err_a or "无")
print("B(canvas)截图 =", B.size, " 运行错误:", err_b or "无")
print()
print("canvas 版几何：", geom_info)
print("SVG 字符串长度 =", len(svg_html), "（非 0 说明原版 renderKline 真的跑起来了）")

# ────────────────────────────────────────────────
# 比对
# ────────────────────────────────────────────────
if A.size != B.size:
    B = B.resize(A.size, Image.LANCZOS)
diff = ImageChops.difference(A, B).convert("L")
px = list(diff.getdata())
n = len(px)
mean = sum(px) / n
over = sum(1 for v in px if v > 48)
over_pct = 100.0 * over / n

print()
print("逐像素差异：平均 %.2f / 255   差异>48 的像素 %d 个（%.3f%%）"
      % (mean, over, over_pct))

# 差分可视化（放大差异）
diff_vis = diff.point(lambda v: min(255, v * 4))

W, H = A.size
PAD = 10
sheet = Image.new("RGB", (W * 3 + PAD * 4, H + PAD * 2 + 30), (20, 26, 42))
from PIL import ImageDraw
d = ImageDraw.Draw(sheet)
for i, (im, lab) in enumerate([(A, "A: PWA 原版 (SVG)"), (B, "B: 小程序版 (canvas 2d)"), (diff_vis, "差分 ×4")]):
    x = PAD + i * (W + PAD)
    sheet.paste(im, (x, PAD + 24))
    d.text((x, PAD + 6), lab, fill=(200, 210, 230))
sheet.save(os.path.join(HERE, "_kline_cmp.png"))
print("对照图已写出 promo/_kline_cmp.png")
