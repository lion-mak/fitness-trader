# -*- coding: utf-8 -*-
"""
UI 移植性扫描 v2（2026-09-22 修正版）

v1 的缺陷：把「换 API 即可实现」误判为「做不到」（innerHTML / addEventListener /
localStorage 等其实都有确定的替代写法，视觉 100% 一致）。这会产生假警报，比漏报更有害。
v2 改为四档分类，并加「视觉影响度」维度 —— 因为「能不能 100% 复刻」的答案不取决于
「有没有 API 差异」，而取决于「差异会不会被眼睛看到」。

分类：
  OK     小程序/ WXSS 原生直译，像素级一致
  API    浏览器 API → 小程序 API，功能等价、视觉一致（只是写法要换）
  CANVAS 需换绘制方式（SVG 字符串 → canvas 2d），视觉可还原但要逐图重新校准
  DIFF   平台差异，无法像素级一致（字体字宽、DPR 取整、不支持的 CSS 效果）

影响度：
  HI   会把 UI 做坏（数字对不齐、图形错位、文字溢出）—— 必须逐个校准
  MID  看得见但不影响理解
  LO   几乎无感（可安全降级）

用法： python promo/scan_ui_portability.py
"""
import io, re

SRC = "index.html"

CSS_RULES = [
    ("var(--",            "OK",     "LO",  "WXSS 支持 CSS 变量"),
    ("border-radius",     "OK",     "LO",  "WXSS 原生；canvas 用 arcTo/roundRect"),
    ("transform:",        "OK",     "LO",  "WXSS 原生；canvas 用 setTransform"),
    ("linear-gradient",   "OK",     "LO",  "WXSS 原生；canvas createLinearGradient"),
    ("box-shadow",        "OK",     "LO",  "WXSS 原生；canvas shadowBlur+shadowColor"),
    ("transition:",       "OK",     "LO",  "WXSS 原生支持"),
    ("animation:",        "OK",     "LO",  "WXSS 原生支持"),
    ("@keyframes",        "OK",     "LO",  "WXSS 原生支持"),
    ("::before",          "OK",     "LO",  "WXSS 支持伪元素"),
    ("::after",           "OK",     "LO",  "WXSS 支持伪元素"),
    ("display:flex",      "OK",     "LO",  "WXSS 主力布局，原生支持"),
    ("calc(",             "OK",     "LO",  "WXSS 支持 calc"),
    ("radial-gradient",   "OK",     "LO",  "WXSS 原生；canvas createRadialGradient"),
    ("min(",              "OK",     "LO",  "WXSS 支持 min()/max()/clamp()"),
    ("max(",              "OK",     "LO",  "同上"),
    ("env(safe-area",     "OK",     "LO",  "小程序支持，但建议改固定 rpx"),
    ("vh",                "OK",     "LO",  "WXSS 支持 vh/vw"),
    ("vw",                "OK",     "LO",  "WXSS 支持 vh/vw"),
    ("position:sticky",   "DIFF",   "MID", "小程序支持但需在 scroll-view 内且同层，行为有差异"),
    ("letter-spacing",    "DIFF",   "MID", "WXSS 支持；但 canvas 无原生 letterSpacing（需逐字绘制或 ctx.letterSpacing，后者在部分基础库缺失）"),
    ("tabular-nums",      "DIFF",   "HI",  "font-variant-numeric 在小程序支持不稳；canvas 里要靠字体本身等宽 ⇒ 数字列可能对不齐"),
    ("word-spacing",      "DIFF",   "LO",  "canvas 无对应，需手动调空格宽度"),
    ("backdrop-filter",   "DIFF",   "LO",  "小程序不支持毛玻璃。✅但本项目 .backrow 已叠 background:rgba(10,14,26,0.92)，alpha 0.92 几乎不透明 ⇒ 直接改实色 rgba(...,0.96) 视觉无感，安全降级"),
    ("-webkit-",          "DIFF",   "LO",  "厂商前缀视具体属性而定"),
    ("filter:",           "DIFF",   "MID", "WXSS 部分支持 blur/brightness；canvas 无通用 filter"),
    ("aspect-ratio",      "DIFF",   "MID", "小程序支持差，建议改 padding-top 百分比占位"),
    ("scroll-snap",       "DIFF",   "LO",  "小程序不支持 scroll-snap，横滑贴合需 JS 模拟"),
]

SVG_RULES = [
    ("<path",             "CANVAS", "HI",  "canvas 需手写坐标路径（本项目 path 多为折线/柱，坐标算法可留）"),
    ("<text",             "CANVAS", "HI",  "canvas fillText；⚠️字族/字宽会变 ⇒ 30 处文字要重新校准位置与锚点"),
    ("text-anchor",       "CANVAS", "HI",  "canvas 用 ctx.textAlign（middle/start/end 一一对应）"),
    ("<circle",           "CANVAS", "LO",  "canvas arc()"),
    ("<rect",             "CANVAS", "LO",  "canvas fillRect/strokeRect/roundRect"),
    ("<line",             "CANVAS", "LO",  "canvas moveTo/lineTo"),
    ("stroke-dasharray",  "CANVAS", "LO",  "canvas setLineDash"),
    ("<polyline",         "CANVAS", "LO",  "canvas beginPath+lineTo"),
    ("<polygon",          "CANVAS", "LO",  "canvas 闭合路径"),
    ("<g ",               "CANVAS", "LO",  "canvas save/restore + setTransform"),
    ("<linearGradient",   "CANVAS", "LO",  "canvas createLinearGradient"),
    ("<tspan",            "CANVAS", "MID", "需拆成多次 fillText 手动定位"),
    ("dominant-baseline", "CANVAS", "LO",  "canvas textBaseline"),
]

JS_RULES = [
    ("innerHTML",             "API",  "LO",  "→ WXML 模板 + wx:for / wx:if（写法换，UI 不变）"),
    ("addEventListener",      "API",  "LO",  "→ WXML bind*/catch*（写法换，UI 不变）"),
    ("localStorage",          "API",  "LO",  "→ wx.setStorageSync / 云数据库（数据层，不影响 UI）"),
    ("document.createElement", "API", "LO",  "→ 改用 setData 驱动 WXML（58 个图标类元素如需保留，改成独立组件）"),
    ("clientWidth",           "API",  "HI",  "→ SelectorQuery。⚠️异步了，且隐藏态仍返回 0 ⇒ 现有 NT.deferred / exHeat 的「隐藏不绘、显示后补绘」逻辑要整体改成异步回调"),
    ("getBoundingClientRect", "API",  "HI",  "→ createSelectorQuery().boundingClientRect()，同样从同步变异步"),
    ("offsetWidth",           "API",  "MID", "→ SelectorQuery（异步）"),
    ("offsetHeight",          "API",  "MID", "→ SelectorQuery（异步）"),
    ("elementFromPoint",      "API",  "HI",  "⛔小程序无此 API。本项目有 2 处真调用（bindHistTip 命中 .hslot、bindIntradayTip 命中 .evslot）⇒ 必须改成「指针 X → 最近槽索引」反查（K 线已是这种做法，可照抄）"),
    ("requestAnimationFrame", "API",  "LO",  "canvas node.requestAnimationFrame"),
    ("innerWidth",            "API",  "MID", "→ wx.getSystemInfo().windowWidth（⚠️热力图/趋势图用 min(innerWidth,480) 反推格子尺寸，要换成 windowWidth 并重算）"),
    ("innerHeight",           "API",  "LO",  "→ windowHeight"),
    ("devicePixelRatio",      "API",  "MID", "→ wx.getSystemInfo().pixelRatio，且 canvas 必须手动 w*h 缩放否则模糊"),
    ("matchMedia",            "API",  "LO",  "→ 用 windowWidth 判断"),
    ("screen.",               "API",  "LO",  "→ getSystemInfo"),
    ("getComputedStyle",      "API",  "MID", "小程序无，改在 JS 里维护一份色值常量表"),
    ("ResizeObserver",        "API",  "LO",  "→ wx.onWindowResize"),
]

def scan(txt, rules, label, strip_before=None):
    print("=" * 80)
    print(label)
    print("=" * 80)
    rows = []
    for key, cls, impact, note in rules:
        n = txt.count(key)
        if n == 0:
            continue
        rows.append((n, key, cls, impact, note))
    rows.sort(key=lambda r: ({"HI": 0, "MID": 1, "LO": 2}[r[3]], -r[0]))
    if not rows:
        print("  （未使用）")
    for n, key, cls, impact, note in rows:
        print("  [%s/%s] %-24s x%-4d %s" % (cls, impact, key, n, note))
    print()
    return rows

s = io.open(SRC, encoding="utf-8", newline="").read()
css_start, css_end = s.find("<style>"), s.find("</style>")
css = s[css_start:css_end]
js_start, js_end = s.find("<script>"), s.rfind("</script>")
js = s[js_start:js_end]
# 避免 filter: 误命中 backdrop-filter:
css_clean = css.replace("backdrop-filter", "backdrop_XX")

r1 = scan(css_clean, CSS_RULES, "① CSS 视觉特性")
r2 = scan(js, SVG_RULES, "② SVG 特性（字符串拼接）")
r3 = scan(js, JS_RULES, "③ 浏览器 API")

print("=" * 80)
print("汇总 · 按「需要在多大程度上动它」分")
print("=" * 80)
allr = r1 + r2 + r3
def sel(cls, impact=None):
    return [r for r in allr if r[2] == cls and (impact is None or r[3] == impact)]
def cnt(cls, impact=None):
    return sum(r[0] for r in sel(cls, impact))

for cls, desc in [
    ("OK",     "原生直译，像素级一致"),
    ("API",    "换 API，功能等价、视觉一致"),
    ("CANVAS", "换绘制方式，视觉可还原但需逐图校准"),
    ("DIFF",   "平台差异，无法像素级一致"),
]:
    print("  %-7s %-32s 种类 %2d / 出现 %4d" % (cls, desc, len(sel(cls)), cnt(cls)))

print()
print("  ---- 🔴 高影响（HI）：会把 UI 做坏，必须逐个校准 ----")
hi = [r for r in allr if r[3] == "HI"]
hi.sort(key=lambda r: -r[0])
for n, key, cls, impact, note in hi:
    print("     [%s] %-22s x%-4d" % (cls, key, n))
print()
print("  ---- ✅ 低影响（LO）：可安全降级或换写法，看不出来 ----")
lo = [r for r in allr if r[3] == "LO"]
print("     共 %d 种 / %d 处" % (len(lo), sum(r[0] for r in lo)))

print()
print("=" * 80)
print("④ 文字渲染（最大还原风险）")
print("=" * 80)
print("  <text> 元素            = %d 处" % js.count("<text"))
print("  含 font-size 的 text   = %d 处（字号各异 ⇒ 每处都要重设）" % len(re.findall(r"<text[^>]*font-size", js)))
fams = sorted(set(re.findall(r'font-family="([^"]*)"', js)) | set(re.findall(r"font-family:\s*([^;\"']+)", js)) | set(re.findall(r"--mono:\s*([^;]+)", css)))
print("  用到的字族             = %s" % fams)
sizes = sorted(set(int(x) for x in re.findall(r'font-size="(\d+)', js) + re.findall(r"font-size:\s*(\d+)px", css)))
print("  用到的字号             = %s" % sizes)
print("  ⇒ 字族都是系统字体栈（-apple-system / ui-monospace / monospace），无自定义字体 ⇒")
print("     iOS 上小程序与 PWA 字体一致；Android 上 monospace 会映射到别的等宽字体 ⇒ 字宽变化")
