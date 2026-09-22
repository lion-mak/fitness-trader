# -*- coding: utf-8 -*-
"""
mp_build.py —— 把 PWA（index.html）的业务内核抽取到微信小程序工程。

为什么要有这个脚本：
  PWA 是「单文件 + 业务内核混在渲染代码里」的结构，而小程序必须模块化。
  手工抄一遍有 45k 字符，必然抄错、且以后 PWA 每次迭代都要重抄。
  所以把抽取做成可重跑脚本：PWA 改一次，重跑一次即可同步。

抽取内容：
  1. <style>            → miniprogram/app.wxss   （WXSS 是 CSS 子集，整体搬迁 + 兼容替换）
  2. 顶层常量声明        → miniprogram/lib/calc.js
  3. 纯计算函数（139 个） → miniprogram/lib/calc.js
  4. js/nutrition-engine.js → miniprogram/lib/nutrition-engine.js（加 CommonJS 导出）
  5. data/foods.json    → miniprogram/data/foods.js（JSON 转模块，供同步 require）

安全机制：
  - 依赖闭包分析：抽出后回扫所有标识符，减去「已知全局」，剩下的即「未解析引用」，
    全部打进报告。有未解析引用就是抽取不完整，会显式列出而不是静默漏掉。
  - 渲染函数（碰 document/SVG/canvas 的 100 个）一律不抽，由页面层重写。

用法：python promo/mp_build.py
"""
import io, os, re, json, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SRC_HTML = os.path.join(ROOT, "index.html")
MINI = r"E:\WeChatProjects\jianpan\miniprogram"

def read(p):
    return io.open(p, encoding="utf-8", newline="").read()

def write(p, s):
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    return len(s)

def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


# ────────────────────────────────────────────────────────────────
# JS 顶层声明扫描器：正确跳过字符串 / 模板串 / 注释，按括号配平切语句
# ────────────────────────────────────────────────────────────────
class Scanner:
    REGEX_PREV = set("(,=:[!&|?{};+-*%~^<>")
    REGEX_KEYWORD = set("return typeof case in of new delete void instanceof do else yield await".split())

    def __init__(self, s):
        self.s = s
        self.n = len(s)

    def _regex_allowed(self, i):
        """判断 s[i] 的 '/' 是正则起始还是除号。
        规则：看前面最后一个非空白字符 —— 是运算符/括号则为正则，是标识符/数字/) 则为除号。
        ⚠️ 这条规则必须存在：源码里有 .replace(/"/g, '&quot;') ——
        不区分正则的话，正则里的引号会被当成字符串起始，导致括号配平错位、
        函数边界一路吞到文件末尾（实测把 escHtml 吞成 97039 字符）。"""
        j = i - 1
        while j >= 0 and self.s[j] in " \t\r\n":
            j -= 1
        if j < 0:
            return True
        c = self.s[j]
        if c in self.REGEX_PREV:
            return True
        m = re.search(r"([A-Za-z_$][\w$]*)\s*$", self.s[:j + 1])
        if m and m.group(1) in self.REGEX_KEYWORD:
            return True
        return False

    def skip_noncode(self, i):
        """若 s[i] 起是字符串/模板串/注释/正则则返回其结束位置，否则原样返回 i"""
        s, n = self.s, self.n
        c = s[i]
        if c in "\"'`":
            q = c
            i += 1
            while i < n:
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == q:
                    return i + 1
                i += 1
            return n
        if c == "/" and i + 1 < n:
            if s[i + 1] == "/":
                j = s.find("\n", i)
                return n if j < 0 else j
            if s[i + 1] == "*":
                j = s.find("*/", i + 2)
                return n if j < 0 else j + 2
            if self._regex_allowed(i):
                i += 1
                in_class = False
                while i < n:
                    ch = s[i]
                    if ch == "\\":
                        i += 2
                        continue
                    if ch == "[":
                        in_class = True
                    elif ch == "]":
                        in_class = False
                    elif ch == "/" and not in_class:
                        return i + 1
                    elif ch == "\n":
                        return i          # 未闭合，当除号处理
                    i += 1
                return n
        return i

    def end_of_statement(self, i):
        """从 i 起（i 指向 = 之后或右括号处）扫到语句结束，返回结束下标（不含）"""
        s, n = self.s, self.n
        depth = 0
        while i < n:
            j = self.skip_noncode(i)
            if j != i:
                i = j
                continue
            c = s[i]
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
                if depth <= 0:
                    # 收尾：吞掉尾随空白与分号
                    k = i + 1
                    while k < n and s[k] in " \t\r\n":
                        k += 1
                    return k + 1 if (k < n and s[k] == ";") else i + 1
            elif c == ";" and depth == 0:
                return i + 1
            i += 1
        return n

    def end_of_block(self, i):
        """i 指向 { ，返回到配平 } 的结束下标（不含）"""
        s, n = self.s, self.n
        depth = 0
        while i < n:
            j = self.skip_noncode(i)
            if j != i:
                i = j
                continue
            c = s[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        return n


DECL_RE = re.compile(r"^(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*", re.M)
FUNC_RE = re.compile(r"^function\s+([A-Za-z_$][\w$]*)\s*\(", re.M)


def parse_top_level(js, base_line):
    """返回顶层声明列表 [{kind,name,start,end,line,body}]，按出现顺序"""
    sc = Scanner(js)
    marks = []
    for m in DECL_RE.finditer(js):
        marks.append(("decl", m.group(1), m.start(), m.end()))
    for m in FUNC_RE.finditer(js):
        marks.append(("func", m.group(1), m.start(), m.start()))
    marks.sort(key=lambda x: x[0 + 2])

    items = []
    for kind, name, start, valpos in marks:
        if kind == "decl":
            end = sc.end_of_statement(valpos)
        else:
            brace = js.find("{", valpos)
            if brace < 0:
                continue
            end = sc.end_of_block(brace)
        items.append({
            "kind": kind, "name": name, "start": start, "end": end,
            "line": base_line + js[:start].count("\n"),
            "body": js[start:end].strip(),
        })
    # 去掉被前一个声明包住的（嵌套 function 等）
    out = []
    for it in items:
        if out and it["start"] < out[-1]["end"]:
            continue
        out.append(it)
    return out


# ────────────────────────────────────────────────────────────────
# 1. 读源
# ────────────────────────────────────────────────────────────────
html = read(SRC_HTML)
si, sj = html.find("<style>"), html.find("</style>")
css = html[si + len("<style>"):sj]
js_head = html.find("<script>\n/* ============ 数据 ============ */")
js_end = html.find("</script>\n<script>\n  /* ============ Service Worker")
MAIN_JS = html[html.find("<script>", html.find("js/food-store.js")) + len("<script>"):js_end]
base_line = html[:html.find("<script>", html.find("js/food-store.js")) + len("<script>")].count("\n") + 1

# ────────────────────────────────────────────────────────────────
# 2. 扫描函数，分「纯计算」与「含渲染」
# ────────────────────────────────────────────────────────────────
DARK = re.compile(
    r"document\.|innerHTML|classList|querySelector|getElementById"
    r"|addEventListener|createElement|window\.|localStorage"
    r"|navigator\.|requestAnimationFrame|elementFromPoint|clientWidth"
    r"|clientHeight|getBoundingClientRect|<svg|<path|<rect |<circle"
    r"|<polyline|getContext|toDataURL|\.style\."
)

decls = parse_top_level(MAIN_JS, base_line)
# ⚠️ 排除状态初始化语句：PWA 里 `let state = loadState();` 长得像常量声明，
#    但它是「状态持有者」——小程序里 state 由 store 注入（bindState），
#    抽进来会与 header 的 var state 重复声明（实测直接 SyntaxError）。
#    判据：名字为 state，或初始化表达式里出现 loadState()。
SKIP_DECL = lambda d: (
    d["name"] == "state"
    or re.search(r"=\s*loadState\s*\(", d["body"][:200]) is not None
)
consts = [d for d in decls if d["kind"] == "decl" and not SKIP_DECL(d)]
skipped_decls = [d for d in decls if d["kind"] == "decl" and SKIP_DECL(d)]
funcs = [d for d in decls if d["kind"] == "func"]
pure = [f for f in funcs if not DARK.search(f["body"])]
dirty = [f for f in funcs if DARK.search(f["body"])]
# 可变（let/var）顶层声明的名字 —— 列进报告，便于人工确认没有把状态变量当常量搬走
mutable = [d["name"] for d in consts if re.match(r"^(let|var)\s", d["body"])]

# ────────────────────────────────────────────────────────────────
# 3. 未解析引用分析
# ────────────────────────────────────────────────────────────────
KNOWN_GLOBAL = set("""
state NutritionEngine FoodStore wx console Math JSON Date Array Object String Number
Boolean RegExp Error TypeError isFinite isNaN parseInt parseFloat setTimeout clearTimeout
setInterval clearInterval encodeURIComponent decodeURIComponent Promise Map Set Symbol
Infinity NaN undefined null true false this arguments return var let const function
new typeof instanceof void delete in of if else for while do switch case break continue
try catch finally throw class extends super yield async await
""".split())

CMT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
STR_RE = re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`", re.S)
IDENT_RE = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*(?!\s*:)")


def unresolved(code, defined):
    clean = STR_RE.sub(" ", CMT_RE.sub(" ", code))
    names = set(IDENT_RE.findall(clean))
    return sorted(names - defined - KNOWN_GLOBAL)


# ────────────────────────────────────────────────────────────────
# 4. 组装 lib/calc.js
# ────────────────────────────────────────────────────────────────
kept_names = {c["name"] for c in consts} | {f["name"] for f in pure}
dirty_names = {f["name"] for f in dirty}
ALL_NAMES = kept_names | dirty_names

# 只找「调用形式」的标识符（name 后跟括号），这样局部变量噪音基本消失。
# 真正危险的是：抽出来的内核代码里调了一个「属于渲染档、因此没被抽出来」的函数 ——
# 那会在运行时 ReferenceError。这一类必须精确抓出来。
CALL_RE = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(")
KEYWORD_CALL = set("if for while switch catch function return typeof".split())


def calls_in(code):
    clean = STR_RE.sub(" ", CMT_RE.sub(" ", code))
    return set(CALL_RE.findall(clean)) - KEYWORD_CALL


ALL_CODE = "\n".join(c["body"] for c in consts) + "\n" + "\n".join(f["body"] for f in pure)
called = calls_in(ALL_CODE)

# ① 引用了渲染档函数（会被钩子接住，或需要在页面层实现）
NEEDS_RENDER = sorted(called & dirty_names)
# ② 完全找不到定义的调用（抽取遗漏 or 浏览器 API）
NEEDS_DEF = sorted(called - ALL_NAMES - KNOWN_GLOBAL - {"require"})

header = u"""/* ============================================================
 * calc.js —— 业务内核（从 PWA index.html 自动抽取，勿手工编辑）
 *
 * 由 promo/mp_build.py 生成。PWA 改动后重跑该脚本即可同步。
 * 抽取范围：全部顶层常量（%d 个）+ 全部纯计算函数（%d 个），
 * 共 %d 字符 —— 这部分与 PWA 逐字节一致，保证计算口径 100%% 不变。
 *
 * 渲染函数（%d 个，碰 DOM/SVG/canvas 的）不在本文件，由 pages/ 重写。
 *
 * ⚠️ state 不再由本文件持有：通过 bindState() 注入 store 里的同一个引用。
 *    PWA 里 state 是模块级可变对象，小程序沿用这个模型（避免每处改写）。
 * ============================================================ */
'use strict';

/* ---- 依赖：BMR/TDEE 计算引擎（PWA 里由 <script src> 提供，小程序里必须显式 require）----
   ⚠️ 少了这一行不会报错，只会让 calcBMR() 走进 catch 兜底返回 1500 ——
   数字看起来"正常"，其实是假的。测试里专门有一条断言盯着它。 */
var NutritionEngine = require('./nutrition-engine.js');

/* ---- 宿主注入点 ---- */
var state = null;                    // 由 store.bindState() 注入
var __hooks = {};                    // 渲染/交互钩子（页面层注册）
function bindState(s) { state = s; }
function bindHooks(h) { __hooks = h || {}; }
function __fire(name, arg) { var f = __hooks[name]; if (typeof f === 'function') f(arg); }

""" % (len(consts), len(pure),
       sum(len(c["body"]) for c in consts) + sum(len(f["body"]) for f in pure),
       len(dirty))

# 渲染 / 交互钩子空壳。
# PWA 里这些函数与内核同一作用域，内核可以随时调用它们；小程序里它们属于页面层。
# 不做空壳的话，内核一旦调到就是 ReferenceError（整页白屏），且很难定位。
# 空壳默认 no-op，页面用 bindHooks({...}) 覆盖成真实现。
# 只透传第一个参数：内核里 toast('xx') 这样的调用，钩子应该直接收到字符串，
# 而不是一个 Arguments 对象。
header += (u"/* ============================================================\n"
           u" * 零、渲染 / 交互钩子空壳（%d 个）\n"
           u" * 内核里调用了这些函数，但它们的实现属于页面层（碰 DOM）。\n"
           u" * 这里先给 no-op 空壳，页面用 bindHooks() 覆盖；不覆盖也只是不显示，不会崩。\n"
           u" * ============================================================ */\n" % len(NEEDS_RENDER))
for n in NEEDS_RENDER:
    header += u"function %s() { __fire('%s', arguments[0]); }\n" % (n, n)
header += u"\n"

body_parts = []
body_parts.append(u"/* ============================================================\n"
                  u" * 一、常量（%d 个）—— 与 PWA 完全一致\n"
                  u" * ============================================================ */\n" % len(consts))
for c in consts:
    body_parts.append(u"/* L%d */ %s\n" % (c["line"], c["body"]))

body_parts.append(u"\n/* ============================================================\n"
                  u" * 二、纯计算函数（%d 个）—— 与 PWA 完全一致\n"
                  u" * ============================================================ */\n" % len(pure))
for f in pure:
    body_parts.append(u"\n/* L%d */ %s\n" % (f["line"], f["body"]))

# 导出：所有常量名 + 纯函数名 + 被内核调用的钩子同名（页面层要能覆盖它们）
exports = sorted(kept_names | set(NEEDS_RENDER) | {"bindState", "bindHooks", "NutritionEngine"})
footer = u"\n/* ---- 导出 ---- */\nmodule.exports = {\n"
footer += "".join(u"  %s: %s,\n" % (n, n) for n in exports if re.match(r"^[A-Za-z_$][\w$]*$", n))
footer += u"};\n"

calc_js = header + "".join(body_parts) + footer

# ────────────────────────────────────────────────────────────────
# 5. app.wxss：CSS 整体搬迁 + 小程序兼容替换
# ────────────────────────────────────────────────────────────────
wxss = css
wxss = wxss.replace(":root {", "page {", 1)
wxss = wxss.replace("body {", "page {", 1)
REPL = [
    # PWA 专属 / 小程序不支持 —— 逐条替换（每条都写明为什么）
    (r"backdrop-filter:\s*blur\([^)]*\);", ""),        # 小程序不支持；该处底色 alpha .92，改实色无视觉差
    (r"-webkit-backdrop-filter:\s*blur\([^)]*\);", ""),
    (r"cursor:\s*pointer;?", ""),                      # 触屏无光标概念
    (r"height:\s*100dvh;", "height:100vh;"),           # dvh 小程序不支持
    (r"scrollbar-width:\s*none;?", ""),
    (r"\.screen::-webkit-scrollbar\s*\{[^}]*\}", ""),  # 滚动条样式无效
    (r"min-height:\s*100vh;", "min-height:100%;"),
    (r"user-select:\s*none;?", "-webkit-user-select:none;"),
]
for pat, rep in REPL:
    wxss = re.sub(pat, rep, wxss)
wxss = (u"/* app.wxss —— 由 promo/mp_build.py 从 PWA index.html 的 <style> 自动生成，勿手工编辑。\n"
        u" * WXSS 是 CSS 子集，故整体搬迁；已就地替换掉小程序不支持的特性（见脚本 REPL 表）。\n"
        u" * 页面级微调请写在各页 .wxss，不要改本文件（会被覆盖）。\n"
        u" */\n") + wxss.strip() + u"\n"

# ────────────────────────────────────────────────────────────────
# 6. 写出
# ────────────────────────────────────────────────────────────────
report = []
def emit(path, content, label):
    n = write(path, content)
    report.append(u"  %-46s %8.1f KB  %s" % (rel(path), n / 1024.0, label))
    return n

n_calc = emit(os.path.join(MINI, "lib", "calc.js"), calc_js,
              u"常量 %d + 纯函数 %d" % (len(consts), len(pure)))
n_wxss = emit(os.path.join(MINI, "app.wxss"), wxss, u"CSS 整体搬迁")

# nutrition-engine.js：加 CommonJS 导出
ne = read(os.path.join(ROOT, "js", "nutrition-engine.js"))
ne_m = re.sub(r"\}\)\(\);\s*$", "})();\n\nmodule.exports = NutritionEngine;\n", ne)
if "module.exports" not in ne_m:
    ne_m += "\nmodule.exports = NutritionEngine;\n"
emit(os.path.join(MINI, "lib", "nutrition-engine.js"), ne_m, u"纯计算引擎（原样 + 导出）")

# foods.json → data/foods.js
#
# ⭐ 字段裁剪（2026-09-22 实测后加入）：这三项只服务「构建期」或只出现在 food-store.js 的
#    文档注释/降级数据里，**运行期一行都没读**（实测：index.html 中 recipe/yield_g/basis 出现 0 次；
#    js/food-store.js 里全是数据字面量，无一处在代码里取值）：
#      recipe   227.6 KB  菜品的配料明细，供 build.py 加权算 kcal 用
#      basis     36.2 KB  '100g' / '100ml'，UI 从不读（界面文案是写死的）
#      yield_g   19.5 KB  出品重量，同上
#    ⇒ 合计 283.3 KB / 全部字段 917.8 KB = 31%。主包从 ~1.0 MB 降到 ~0.72 MB。
#    ⚠️ 源数据 data/foods.json 保持完整；要恢复只需从 STRIP 里删掉对应键再重跑本脚本。
#    ⚠️ py / ini / alias / conv / src 是搜索与排序要用的（js/food-store.js 真读），⛔不能删。
STRIP_FIELDS = ("recipe", "yield_g", "basis")
fj = os.path.join(ROOT, "data", "foods.json")
if os.path.isfile(fj):
    raw = read(fj)
    obj = json.loads(raw)
    saved = [0, 0]      # [裁掉的字节, 条目数]
    if isinstance(obj, dict) and isinstance(obj.get("foods"), list):
        for it in obj["foods"]:
            for k in STRIP_FIELDS:
                if k in it:
                    saved[0] += len(json.dumps({k: it[k]}, ensure_ascii=False).encode("utf-8")) + 1
                    del it[k]
                    saved[1] += 1
    foods_js = (u"/* data/foods.js —— 由 promo/mp_build.py 从 data/foods.json 生成。\n"
                u" * 转为 JS 模块是为了同步 require（小程序不能像 PWA 那样 fetch 本地 json）。\n"
                u" * ⚠️ 已裁掉运行期不读的字段 %s（源 json 完整），详见 promo/mp_build.py 的 STRIP_FIELDS。\n"
                u" */\nmodule.exports = " % (u" / ".join(STRIP_FIELDS))
                + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + u";\n")
    n_foods = emit(os.path.join(MINI, "data", "foods.js"), foods_js,
                   u"食物库 %s 条（裁掉 %d 个字段共 %.1f KB）" % (
                       len(obj.get("foods", obj)) if isinstance(obj, dict) else len(obj),
                       saved[1], saved[0] / 1024.0))
else:
    n_foods = 0

# ────────────────────────────────────────────────────────────────
# 7. 报告
# ────────────────────────────────────────────────────────────────
lines = []
lines.append(u"mp_build 报告  ——  PWA 内核 → 小程序工程")
lines.append(u"=" * 84)
lines.append(u"")
lines.append(u"源：index.html（%d 字符，顶层声明 %d 个）" % (len(html), len(decls)))
lines.append(u"")
lines.append(u"【写出】")
lines.extend(report)
lines.append(u"")
lines.append(u"【函数分档】")
lines.append(u"  纯计算 %3d 个 → lib/calc.js（与 PWA 逐字节一致）" % len(pure))
lines.append(u"  渲染   %3d 个 → 不抽取，由 pages/ 重写" % len(dirty))
lines.append(u"")
lines.append(u"【可变顶层声明（let/var）】%d 个 —— 逐个确认它们不是「状态持有者」：" % len(mutable))
if mutable:
    for n in mutable:
        lines.append(u"    · %s" % n)
else:
    lines.append(u"    无")
lines.append(u"")
lines.append(u"【已排除的声明】%d 个（状态初始化语句，由 store 注入，不能当常量搬）：" % len(skipped_decls))
for d in skipped_decls:
    lines.append(u"    · L%d  %s" % (d["line"], d["body"].split("\n")[0][:70]))
lines.append(u"")
lines.append(u"【依赖检查】")
lines.append(u"  ① 内核里调用、但实现属于页面层的函数（已生成 no-op 空壳，页面覆盖）：")
if NEEDS_RENDER:
    for n in NEEDS_RENDER:
        lines.append(u"      · %s" % n)
else:
    lines.append(u"      无")
lines.append(u"")
lines.append(u"  ② 内核里调用、但完全找不到定义的名字（抽取遗漏 / 浏览器 API）：")
if NEEDS_DEF:
    for n in NEEDS_DEF:
        lines.append(u"      ⚠ %s" % n)
    lines.append(u"  ⇒ 若其中有浏览器 API（fetch/FileReader/alert 等），属预期：")
    lines.append(u"    以 PWA 现有实现为准，小程序侧改用 wx.* 或去掉该分支。")
else:
    lines.append(u"      无 —— 依赖闭合。")
lines.append(u"")
lines.append(u"【未抽取的渲染函数清单（重写工作项）】")
for f in sorted(dirty, key=lambda x: -len(x["body"]))[:40]:
    lines.append(u"    L%-5d %-28s %5d 字符" % (f["line"], f["name"], len(f["body"])))
if len(dirty) > 40:
    lines.append(u"    … 其余 %d 个" % (len(dirty) - 40))

write(os.path.join(HERE, "_build_report.txt"), u"\n".join(lines) + u"\n")
print("mp_build done: calc=%d chars, wxss=%d chars" % (len(calc_js), len(wxss)))
