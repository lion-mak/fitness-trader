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

    def _skip_template(self, i):
        """模板串：`…${ expr }…`。i 指向起始反引号，返回到闭合反引号之后。

        🔴 `_skip_template` 存在的唯一理由（2026-09-23 实测的静默丢失）：
        旧实现把反引号当普通引号 —— `if c in "\\"'`":`，扫到下一个反引号就收尾。
        但 PWA 里**模板串可以嵌套**（`${simple ? '' : `…`}` 这种写法，renderBodyDetail 与
        renderBodyTrend 都这么写），内层反引号会让外层**提前收尾**⇒ 外层函数体被截短、
        紧接着的 HTML 文本被当成代码参与括号配平 ⇒ 括号深度错位。
        后果不是报错，而是紧随其后的顶层声明被判成「被上一个声明包住的嵌套声明」**静默丢掉**
        （parse_top_level 里那句 `if out and it["start"] < out[-1]["end"]: continue`）——
        实测吞掉 bodyLogValue / weightLogBmiPoints / renderBodyTrend 三个函数，
        其中前两个是**纯计算**、本该一字不差地进内核（body-detail 页的趋势图数据全靠它们）。
        ⇒ `${ }` 里是**代码**，必须递归按代码扫（可再套字符串 / 模板串 / 正则）。
        """
        s, n = self.s, self.n
        i += 1
        while i < n:
            ch = s[i]
            if ch == "\\":
                i += 2
                continue
            if ch == "`":
                return i + 1
            if ch == "$" and i + 1 < n and s[i + 1] == "{":
                i += 2
                depth = 1
                while i < n and depth > 0:
                    j = self.skip_noncode(i)
                    if j != i:
                        i = j
                        continue
                    if s[i] == "{":
                        depth += 1
                    elif s[i] == "}":
                        depth -= 1
                    i += 1
                continue
            i += 1
        return n

    def skip_noncode(self, i):
        """若 s[i] 起是字符串/模板串/注释/正则则返回其结束位置，否则原样返回 i"""
        s, n = self.s, self.n
        c = s[i]
        if c == "`":
            return self._skip_template(i)
        if c in "\"'":
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

# 🔴 收敛校验：FUNC_RE 命中的顶层 function 必须**一个不少**地落进 decls。
#    为什么要这道闸：parse_top_level 会用「被前一个声明包住 ⇒ 是嵌套 function，丢掉」这条规则，
#    这本身是对的；但只要扫描器的括号配平被搞错，**真·顶层函数也会被这条规则静默吃掉** ——
#    不报错、不提示，只是内核里少几个函数（用到时才 ReferenceError 或功能静默缺失）。
#    2026-09-23 实测：模板串嵌套（`${x ? '' : `…`}`）让外层提前收尾 ⇒ 吞掉 3 个函数，
#    其中 bodyLogValue / weightLogBmiPoints 是纯计算、本该一字不改地进内核。
#    这里把「静默丢失」升级成「构建期报错」。误报已实测为 0（239 命中 / 239 保留）。
_func_hits = [m.group(1) for m in FUNC_RE.finditer(MAIN_JS)]
_swallowed = sorted(set(_func_hits) - {d["name"] for d in funcs})
if _swallowed:
    raise SystemExit(u"❌ 有顶层函数被括号配平吞掉了（扫描器 bug？）：%s" % u", ".join(_swallowed))

# ────────────────────────────────────────────────────────────────
# 2b. DE_DOM —— 把「只沾了一点 DOM」的函数还原成纯计算函数
#
# 为什么需要这一步（2026-09-22 实测踩到的真坑）：
#   settleDay() 里 99% 是状态计算（连板计数、发币、加经验、幂等锚），
#   只有末尾两行在显示一个视觉反馈（把缺口数字塞进涨停庆祝层）。
#   DARK 判据看到 document.getElementById 就把它整只判成「渲染档」⇒ 变成 no-op 空壳
#   ⇒ **币、连板、经验一分不发**，而且不报错、页面看着正常，是纯静默失效。
#   app.js 明明调了 checkDayRollover()，但里面调的 settleDay/saveState 全是空壳。
#
# 处理方式：把 DOM 那两行换成一次钩子调用，函数就回到纯计算档，
#   于是它的逻辑**一字不改**地被抽进 calc.js（而不是变成空壳）。
#   ⚠️ 替换后必须收敛校验：DARK 痕迹没清干净就直接报错退出，
#      否则会「以为修好了、其实又生成了个空壳」—— 这正是这个坑最难查的地方。
# ⚠️ 只在**确实无法在纯函数层表达**才加进来；能整体搬就整体搬。
DE_DOM = {
    "settleDay": [
        (r"(?m)^[ \t]*var ce=document\.getElementById\('celeb-net'\).*$",
         u"    __fire('celebrate', { date: dateStr, net: net, streak: state.limitUpStreak });"),
        (r"(?m)^[ \t]*var cb=document\.getElementById\('celeb'\).*$", u""),
    ],
    # drawCard 同理（2026-09-23）：它 99% 是纯计算（扣币 / 抽卡 / 十连保底 / 满星返币 /
    # 记 totalDraws / 落盘），只有收尾两行是「开结果弹层 + 重绘图鉴」。
    # ⚠️ 但**不能**就这么留着 —— 自动生成的钩子空壳只转发 arguments[0]：
    #     showGachaResult(results, refundTotal) → __fire('showGachaResult', results)
    #   ⇒ refundTotal 被静默丢掉，「满星重复卡已转化 +N 币」那一句永远不显示，
    #     而币其实已经加进 state 了（账对得上、界面少一句话，最难查的一类）。
    #     换成单对象钩子把两个参数一起传出去。
    "drawCard": [
        (r"(?m)^[ \t]*showGachaResult\(results, refundTotal\);[ \t]*\n[ \t]*renderGacha\(\);[ \t]*$",
         u"  __fire('gachaResult', { results: results, refundTotal: refundTotal });"),
    ],
}
de_dom_done = []
for _f in funcs:
    if _f["name"] not in DE_DOM:
        continue
    for _pat, _rep in DE_DOM[_f["name"]]:
        _f["body"], _n = re.subn(_pat, _rep, _f["body"])
        if _n == 0:
            raise SystemExit(u"❌ DE_DOM 的规则没命中 %s：%s —— 源函数改了？请同步更新 mp_build.py"
                             % (_f["name"], _pat))
    _left = DARK.search(_f["body"])
    if _left:
        raise SystemExit(u"❌ DE_DOM 未能清干净 %s 的 DOM 痕迹（还残留 %r）"
                         % (_f["name"], _left.group(0)))
    de_dom_done.append(_f["name"])

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

# 宿主注入的三个符号（在生成出来的 calc.js 头部定义，不是从 PWA 抽出来的）。
# 不列进来的话它们会掉进「② 找不到定义的名字」那一栏，把真问题淹掉 ——
# DE_DOM 用它把渲染行换成钩子调用，必然会出现 __fire。
KNOWN_GLOBAL |= {"__fire", "bindState", "bindHooks"}

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

# 🔴 顶层「可变原始值」变量必须用 getter 导出，⛔不能用 `X: X`。
#    为什么：`X: X` 是**值快照** —— 取 module.exports 的那一刻就把当前值抄进去了。
#    内核里 `trendRange = r` / `lbRange = 'month'` / `switchTab('holdings')` 改的是**模块内的
#    那个 let 绑定**，而 exports 上的副本纹丝不动 ⇒ 页面侧读到的永远是初始值。
#    2026-09-22 实测踩坑：持仓页 `calc.trendRange` 恒为 'all'，切档后 tab 高亮与副标题都不跟着变，
#    但柱子却按新档位重画了（setTrendRange 内部确实改了内核那份）—— 表现为「点了没反应」。
#    getter 每次读取才求值，两条视图从此永远一致。
LIVE_VARS = {"trendRange", "lbRange", "historyRange", "curTab", "curBodyIdx",
             "ocrFilled", "ocrBusy", "klineGeom"}
_live = sorted(LIVE_VARS & set(exports))
_missing_live = sorted(LIVE_VARS - set(exports))
for _n in _missing_live:   # 收敛校验：名单里的名字必须真被抽取到了，否则说明摘录范围变了
    if not re.search(r"(?m)^(?:let|var)\s+%s\s*=" % _n, MAIN_JS):
        raise SystemExit(u"❌ LIVE_VARS 里的 %s 既没被导出、也不在源里 —— 名单过期了" % _n)

footer = u"\n/* ---- 导出 ---- */\nmodule.exports = {\n"
for n in exports:
    if not re.match(r"^[A-Za-z_$][\w$]*$", n):
        continue
    if n in LIVE_VARS:
        footer += u"  get %s() { return %s; },\n" % (n, n)
    else:
        footer += u"  %s: %s,\n" % (n, n)
footer += u"};\n"

calc_js = header + "".join(body_parts) + footer

# ────────────────────────────────────────────────────────────────
# 5. app.wxss：CSS 整体搬迁 + 小程序兼容替换
# ────────────────────────────────────────────────────────────────
wxss = css
wxss = wxss.replace(":root {", "page {", 1)
wxss = wxss.replace("body {", "page {", 1)

# 🔴 通配符选择器 `*` —— WXSS **不支持**，wcsc 直接报
#    `unexpected token *`（行首列首），**整包编译失败 ⇒ 全站白屏**。
#    2026-09-22 事故：开发者工具报「编译 .wxss 文件错误」，5 个 tab 图标全是破图、页面全白，
#    根因就是这一行 `* { margin:0; padding:0; box-sizing:border-box; }`。
#    ⚠️ 不能只删掉：小程序默认 box-sizing 是 content-box，PWA 全局 border-box，
#    删了布局会整体错位 ⇒ 必须**展开成小程序真实标签列表**（WXSS 只认 element 选择器）。
WXSS_TAGS = (u"page, view, scroll-view, swiper, swiper-item, cover-view, text, rich-text, "
             u"image, canvas, button, input, textarea, label, picker, picker-view, slider, "
             u"switch, navigator, form, checkbox, radio, progress, icon, video, map, "
             u"open-data, web-view, editor, ad, official-account")
n_star = len(re.findall(r"(?m)^\*\s*\{", wxss))
wxss = re.sub(r"(?m)^\*\s*\{", WXSS_TAGS + u" {", wxss, count=1)
if n_star != 1:
    print(u"⚠️  警告：源 CSS 里 `* {` 出现 %d 次（预期 1）—— 请检查是否还有未展开的通配符选择器"
          u"（多出来的会继续让 wcsc 报错）" % n_star)

# 把展开用的标签清单落盘：mp_wxss_check.py 靠它把「我加进去的合法标签」从
# 「PWA 独有的 HTML 标签（在小程序里静默失效）」里排除掉，避免清单变成噪音。
# ⚠️ 落盘要保持 WXSS_TAGS **原样**（含 ", " 分隔）—— 负控脚本要拿它精确匹配
#    生成出来的那一行；两边格式一旦不一致，负控就会「验证了个寂寞」（2026-09-22 踩过）。
_tagfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"_wxss_tags.txt")
with io.open(_tagfile, "w", encoding="utf-8", newline="") as fh:
    fh.write(WXSS_TAGS)

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
# ────────────────────────────────────────────────────────────────
# 5b. 小程序适配层 —— 追加在 PWA 样式**之后**（同权重覆盖 PWA 规则）
#
# 为什么必须有这一块，而不是让各页自己 @import 一个共享文件：
#   2026-09-22 事故：4 个页面写 `@import "../../styles/scaffold.wxss"`，
#   开发者工具报「编译 .wxss 文件错误」→ 整包编译失败 → 页面全白、tab 图标破图。
#   实测（用工具自带的 wcsc.node 复刻它的编译参数，逐项对照）：
#     · files 里**含** styles/scaffold.wxss  → 编译通过
#     · files 里**缺** styles/scaffold.wxss  → 抛 path `../../styles/scaffold.wxss` not found
#       （4 条报错对 4 个写了 @import 的页面，一一对应）
#   而工具的 WXSS 编译单元 = 「app.wxss + 各页 wxss + 它自己文件索引里剩下的 wxss」，
#   索引是打开项目时建的 —— 之后用脚本新增的文件（尤其新目录 styles/）不在其中，
#   于是 import 目标永远进不了清单 ⇒ 跨文件 @import 在本工程是**脆弱依赖**。
#   ⇒ 定稿：**共享样式一律写进 app.wxss（本块），页面 wxss 一律不写 @import**。
#     好处不只是绕开索引问题：app.wxss 本来就是全局层，语义上也更对。
#   ⚠️ mp_wxss_check.py 现在把「页面里出现 @import」直接判 FAIL，别写回去。
#
# 内容约定：
#   1) PWA 的 .page 有 80px 底部留白 —— **要保留**（理由见下面 .page 那段注释）
#   2) PWA 用 HTML 标签承载的语义（<small>/<b>…），小程序无该标签、选择器静默失效
#      ⇒ 在这里用 class 补等价规则（.s / .kt-v …），页面里直接用 class
#   3) PWA 靠 CSS `display:none` 做「默认收起」的组件（.kw-row/.kline-tip/.hist-tip…），
#      小程序侧显隐一律交给 wx:if ⇒ 适配层要把 display:none 改回可用值，
#      否则标签渲染出来就带着 none，**永远展不开**（2026-09-22 踩过两次）
ADAPT = u"""

/* ════════════════════════════════════════════════════════════════
   小程序适配层（由 promo/mp_build.py 追加，勿手改 —— 会被覆盖）
   共享样式写这里；页面 .wxss 只放本页增量，且**不要写 @import**。
   ════════════════════════════════════════════════════════════════ */

/* ⚠️ 这 80px **要保留**。
   旧注释写的理由是「PWA 的 80px 是给自绘底栏占位，小程序用原生 tabBar 故去掉」——
   前半句对、结论错：PWA 的 .tabbar 是 .app 的 flex 子元素（flex-shrink:0），
   **已经在 .screen 之外**，.screen 高度本来就不含底栏 ⇒ 这 80px 是「内容滚到底之后的
   视觉呼吸」，不是给底栏留的布局补偿。
   实测（2026-09-22 元素级对拍 mp_rect_compare.py）：抹成 0 之后小程序滚到底时
   最后一行紧贴底栏，而 PWA 还有 80px 留白 —— 两端 scrollHeight 正好差这 80px。
   （小程序原生 tabBar 会自己占掉页面可视区，所以这里不用再加底栏高度。） */
.page { padding-bottom: 80px; }

/* PWA 顶栏副标题用 <small>（小程序无此标签），改用 .s */
.pheader .lt .id { font-size:15px; font-weight:500; color:#fff; }
.pheader .lt .s { display:block; color:var(--muted); font-size:10px; font-weight:400; }

/* 🔴 .kw-row（快速记录输入行）—— PWA 靠 `display:none` 做「默认收起」，
   JS 里再改 style.display='flex' 展开。小程序侧**不能照搬**：
   页面改用 wx:if / class 控制「在不在」，标签一旦渲染出来就已经带着
   `display:none` ⇒ 怎么点都出不来（2026-09-22 实测：行情页「⚖️ 记体重」
   点开是空的，行高为 0，看着像没反应）。
   ⇒ 在适配层把默认值改成 flex，显隐交给 wx:if。
   ⚠️ 加 `.show` 类也认（允许两种写法），语义一致。 */
.kw-row { display:flex; }

/* 🔴 小程序的 <input> **内容盒会塌成 0** —— 这条不修，所有表单都比 PWA 矮一截。
   ⑥c 实测（2026-09-23，我的页身体档案）：
     PWA `.field input` 高 43px（padding 22 + border 2 + 文本行盒 19）
     小程序 `.field .inp` 高 24px（**只剩 padding 22 + border 2，内容盒 0**）
   7 个输入框每个矮 19px ⇒ `.edit-fields` 整整短 111.2px，下游 .bmr-box / .bmr-tip /
   .confirm.sell 全部连坐偏移 —— 而且页面看着「没坏」，只是比 PWA 紧凑。
   ⚠️ 不能只在小程序里写 `.inp` 的样式：PWA 的规则挂在 `.field input` 上，
      将来交易页录入口（同样的表单）会再踩一次 ⇒ 修在全局层。
   ⚠️ 这里给的是**总高**（全局 `*` 展开后 box-sizing:border-box 已对 input 生效），
      所以 43 = 22 + 2 + 19 一步到位，不用再算行高。 */
.field input { height: 43px; }

/* 🔴 PWA 的 .confirm 是 <button>，UA 默认行高 ≈ 1.333（不是继承页面的 1.6）。
   小程序把它换成 <view> 后继承页面 line-height:1.6 ⇒ 实测高 52 vs 48。
   金币页的 .gap-note 因此整体下移 4px（连坐）。
   ⚠️ .mini-btn 不受影响：PWA 自己在源码里就写了 line-height:1.3（作者早知道这个坑）。 */
.confirm { line-height: 1.333; }

/* 同上：PWA 的 .ghost-btn 也是 <button>（龙虎榜复盘卡的「换一换/分享」）。
   板页曾在本页 wxss 里补过 .rv-acts .ghost-btn{line-height:1.3}（36.9 vs 37），
   既然是同类问题，统一收到这里，页面不再各自打补丁。 */
.ghost-btn { line-height: 1.3; }

/* 🔴 PWA 的 <select> 在小程序里换成 picker 里的 <view>，**内容盒高度不同**。
   ⑥c 实测（2026-09-23，我的页身体档案的两个下拉）：
     PWA `.field select` 高 45px（padding 22 + border 2 + UA 内容盒 21）
        ⚠️ <select> 的 UA 行高不是 normal 的 1.15 —— Chrome 对 14px 字号给的内容盒正好 21px，
           不能按 line-height 推算，只能用实测值。
     小程序 `.field .pick` 高 46.4px（padding 22 + border 2 + 继承行高 1.6 ⇒ 14×1.6 = 22.4）
   ⇒ 每个下拉行高 1.4px，我的页两个下拉共 2.8px，`.edit-fields` 之后的 .bmr-* 系与
     .confirm.sell 全部连坐下移 2.8px（8 项超阈值）。
   ⚠️ 写成固定 21px 而不是 line-height:1.5：1.5 只是 21/14 的巧合，字号一改就漂；
      这里要表达的是「与 PWA <select> 的内容盒同高」。 */
.field .pick { line-height: 21px; }

/* 同上一类：抽卡页的两个大按钮（.gacha-btn）与里程碑领取按钮（.ms-btn）在 PWA 里也是
   <button>，小程序换成 <view> 后行高从 UA 值变成继承的 1.6。
   ⚠️ 值必须是 **1.333**，不是 1.3 —— ⑥c 实测（2026-09-23）：
      写 1.3 时 `.gacha-btn` 高 61.8 vs PWA 63（dh=-1.2），把整卡与后续卡片全顶偏 1.2px；
      反推 PWA 的 UA 行盒：.big(15px) → 20px、.cost(11px) → 15px，比值正是 4/3。
      改 1.333 后 .big 19.995→20、.cost 14.66→15、.ms-btn 12×1.333=16 ⇒ 两端对齐。
   ⚠️ 与 .confirm(1.333) 同源；.ghost-btn 那条是 1.3（当年按 36.9 vs 37 的残差定的），
      两者不冲突：它们字号与容器不同，各自按实测值收敛。 */
.gacha-btn { line-height: 1.333; }
.ms-btn { line-height: 1.333; }

/* ════════════════════════════════════════════════════════════════
   交易页录入口 6 弹层（2026-09-23 ⑥c 对拍 mp_rect_trade_modals.py）
   ════════════════════════════════════════════════════════════════ */

/* 🔴 就是上面 `.field input` 那条注释里预言的「第二次」：食物搜索框同病。
   PWA `.searchbox input` 高 45px（padding 24 + border 2 + 文本行盒 19），
   小程序只剩 26px（**内容盒塌成 0**，只剩 padding + border）。
   ⚠️ 45 是**总高**（box-sizing:border-box 已生效），别和 `.field input` 的 43 抄成同值 ——
      两者差 2px 是因为 `.searchbox input` 上下 padding 是 12px、`.field input` 是 11px。 */
.searchbox input { height: 45px; }

/* 🔴 `.usual-toggle` 的上边距：PWA 里这 9px 挂在**外层 wrapper 的 inline style** 上
   （`<div style="margin-top:9px;" id="fs-usual">`，innerHTML 才是按钮本身），
   小程序没有这层 wrapper ⇒ 必须搬到元素自身。
   ⚠️ 2026-09-23 实况：页面 .wxss 里曾写过 `.fs-usual{margin-top:9px}`，但 wxml 的元素类名是
      `.usual-toggle` ⇒ **规则名没对上、静默失效**（全工程仅此一处引用 fs-usual）。
      ⑥c 实测：缺失时份量弹层从该行起下游全部上移，sheet 高 604.7 vs PWA 618。 */
.usual-toggle { margin-top: 9px; }

/* 🔴 PWA 的 `.fs-macros .mkv div:first-child / div:last-child` —— 小程序对面是 <view>，
   **标签选择器静默失效** ⇒ 宏量格的数值与单位都退回默认字号（⑥c 实测 .fs-macros 高 65.2 vs PWA 54.4）。
   修法与 `.s` / `.kt-v` 同：页面里给两个子元素加 class，规则改挂 class。
   ⚠️ 不要试图写 `view:first-child` —— WXSS 支持的选择器只有
      `.class` / `#id` / `element` / `element,element` / `::after` / `::before`，
      伪类不在清单里，写错会让 wcsc 整包编译失败（白屏），这是本项目最贵的一种错。 */
.fs-macros .mkv .mv { font-size:14px; font-weight:600; color:#fff; }
.fs-macros .mkv .ml { font-size:10px; color:var(--muted2); margin-top:2px; }

/* 🔴 PWA 的 `.ghost-btn` 是 `<button>` = **inline-block**，小程序换成 <view> 后变块级 ——
   这不只影响行高（行高那条在上面），还会改变**外边距合并**规则。
   ⑥c 实测（2026-09-23，运动列表弹层）链路是：
     · 列表项 `.result-item` 自带 `margin-bottom:8px`（PWA index.html:139）；
     · `.results` 不是滚动容器时，末项那个 8px **穿透出去** ⇒ `.results` 的有效下边距 = 8；
     · PWA 的按钮是**行内级**，行内级不参与相邻外边距合并 ⇒ 实际间距 = 8 + 10（自身 margin-top）= **18**；
     · 小程序的块级 `<view>` ⇒ 合并取 max(8,10) = **10** ⇒ 按钮凭空高 8px，底部留白也随之差 8。
   ⇒ 恢复行内级。⚠️ 限定在 `.sheet` 内：
      · `#food-results` 是滚动容器（BFC）⇒ 那 8px 留在内部、间距 10 —— 两端本来就对，
        加这条不会改变它（行内级 + 10 = 10），所以同一个规则能同时满足两种情形；
      · 板页的 `.ghost-btn` 在 flex 容器里（flex 项会被块化）⇒ 不受影响；
      · `.sheet` 目前全工程只有交易页在用（已 grep 确认），波及面可控。 */
.sheet .ghost-btn { display: inline-block; }

/* 🔴 `input[type=time]` 在 Chrome 里的 UA 内容盒是 **21px**（与 `<select>` 同源），
   不是文本输入的 19px ⇒ PWA 里这个框高 **45px**；被上面 `.field input{height:43px}` 统一压成 43 后，
   **每个时间输入少 2px**。
   ⑥c 实测（2026-09-23）：份量 / 运动录入 / 记录编辑 三个弹层各含 1 个时间输入，三个都恰好差 2.0px；
   而食物搜索、运动列表、自建运动（无时间输入）差 0 —— 一一对应。
   ⚠️ 45 = 22(padding 上下各 11) + 2(border) + 21，别抄成 43。
   ⚠️ 选择器必须写成 `.field .inp-time`：`.field input` 的特异性 (0,1,1) 压过单类 (0,1,0)，
      写成 `.inp-time` 会被上面那条覆盖而**静默失效**。
   ⚠️ 也不用 `input[type="time"]` —— WXSS 支持的选择器只有
      `.class`/`#id`/`element`/`element,element`/`::after`/`::before`，属性选择器不在清单里。 */
.field .inp-time { height: 45px; }

/* 🔴 `.sheet h3`（弹层标题）在小程序里**不可能命中** —— 没有 <h3> 这个标签。
   交易页当年是自己在 trade.wxss 里补了一条同名同值的 `.sheet-h`；身体成分录入弹层
   是第二个用它的地方 ⇒ 上收到适配层，页面不用再各写一份（写两份就是两个真相，
   改一处另一处不跟）。⚠️ `<label>` 能直接用是因为它是小程序的真实组件；
   `<h3>`/`<p>`/`<b>`/`<span>` 都不是 ⇒ 一律要换 class。 */
.sheet .sheet-h { font-size:16px; font-weight:500; }
"""

wxss = (u"/* app.wxss —— 由 promo/mp_build.py 从 PWA index.html 的 <style> 自动生成，勿手工编辑。\n"
        u" * WXSS 是 CSS 子集，故整体搬迁；已就地替换掉小程序不支持的特性（见脚本 REPL 表）。\n"
        u" * 页面级微调请写在各页 .wxss，不要改本文件（会被覆盖）；共享样式写文件末尾的适配层。\n"
        u" */\n") + wxss.strip() + u"\n" + ADAPT

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

# ────────────────────────────────────────────────────────────────
# 6a. data/py-initials.json → data/py-initials.js
#
# 汉字 → 拼音首字母表（1119 条 / 10.9 KB）。PWA 里由 FoodStore 懒 fetch，
# 只服务一个用途：给**自建食物**算拼音首字母（库里的食物本来就有现成的 py/ini 字段）。
# ⇒ 量很小，直接内联成模块，让 FoodStore 同步可用。
# ⚠️ 少了它不会报错：initialsOf() 会静默返回空串 ⇒ 自建食物搜不到拼音
#    （而中文名搜索照常），属于「看着正常其实坏了一半」的那类。
pi_path = os.path.join(ROOT, "data", "py-initials.json")
if os.path.isfile(pi_path):
    pi = json.loads(read(pi_path))
    pi_js = (u"/* data/py-initials.js —— 由 promo/mp_build.py 从 data/py-initials.json 生成。\n"
             u" * 汉字→拼音首字母表，只给自建食物算 ini 用（库里食物自带 py/ini）。\n"
             u" */\nmodule.exports = " % ()
             + json.dumps(pi, ensure_ascii=False, separators=(",", ":")) + u";\n")
    emit(os.path.join(MINI, "data", "py-initials.js"), pi_js,
         u"拼音首字母表 %d 字" % len(pi))
else:
    print(u"⚠️  警告：data/py-initials.json 不存在 —— 自建食物的拼音搜索会静默失效")

# ────────────────────────────────────────────────────────────────
# 6b. js/food-store.js → lib/food-store.js（食物搜索 / 索引层）
#
# 为什么必须迁它：交易页的「加食物」、大盘云图、今日板块全读它
#   （search / byName / categories / toGrams），是那三块的共同前置。
#   ⇒ 它是「按依赖排顺序」里的第 1 块，不做它后面几块只能对着空列表做。
#
# 三处适配（其余逐字节照搬）：
#   1) 数据源：小程序不能 fetch 本地 json ⇒ 两个 data/*.json 已转成同步 require 的 JS 模块
#   2) 自建食物：localStorage → wx.getStorageSync/setStorageSync（键名照旧，
#      且兼容 PWA 留下的 JSON 串形态 —— 迁移过来能直接读）
#   3) load() 简化：数据同步就绪，不需要「懒加载 + 失败降级」两段式；FALLBACK 分支保留
# ⚠️ score / search / buildIndex / initialsOf / toGrams 一行不改 ——
#    搜索排序口径必须与 PWA 一致，否则两端搜同一个词得到不同结果。
fs_src = read(os.path.join(ROOT, "js", "food-store.js"))

FOODSTORE_REPL = [
    (r"var DATA_URL = 'data/foods\.json';[\r\n]+[ \t]*var PY_URL = 'data/py-initials\.json';",
     u"var DATA = require('../data/foods.js');       // 由 mp_build.py 从 data/foods.json 生成\n"
     u"  var PY = require('../data/py-initials.js');   // 由 mp_build.py 从 data/py-initials.json 生成"),

    # DATA_URL 随数据源一起消失（小程序没有「url」这个概念）。
    # 实测 PWA 侧没有任何地方读 FoodStore.DATA_URL（只在本文件内部用于 fetch），
    # 所以不需要留兼容壳 —— 留着反而是个「指向不存在文件的常量」这种假线索。
    (r"    DATA_URL: DATA_URL,\n", u""),

    (r"var raw = localStorage\.getItem\(CUSTOM_KEY\);[\r\n]+"
     r"[ \t]*var arr = raw \? JSON\.parse\(raw\) : \[\];[\r\n]+"
     r"[ \t]*return Array\.isArray\(arr\) \? arr : \[\];",
     u"var raw = wx.getStorageSync(CUSTOM_KEY);\n"
     u"      // PWA 存的是 JSON 串；从 PWA 迁移过来的可能就是这个形态，一并认\n"
     u"      if (typeof raw === 'string') raw = raw ? JSON.parse(raw) : [];\n"
     u"      return Array.isArray(raw) ? raw : [];"),

    (r"try \{ localStorage\.setItem\(CUSTOM_KEY, JSON\.stringify\(list\)\); \} catch \(e\) \{\}",
     u"try { wx.setStorageSync(CUSTOM_KEY, list); } catch (e) {}"),

    # 导出补三项：供 lib/migrate.js 把自建食物一起搬（PWA 的迁移码默认不含它）
    (r"    toGrams: toGrams\n  \};",
     u"    toGrams: toGrams,\n"
     u"    /* 以下三项是 mp_build.py 加的（PWA 不导出）—— 供 lib/migrate.js 搬自建食物 */\n"
     u"    CUSTOM_KEY: CUSTOM_KEY,\n"
     u"    loadCustom: loadCustom,\n"
     u"    saveCustom: saveCustom\n  };"),
]

# load() 整段替换（懒加载两段式 → 同步就绪；FALLBACK 分支保留）
FS_LOAD_RE = re.compile(r"/\* ---------- 加载 ---------- \*/.*?function ready\(\) \{ return load\(\); \}", re.S)
FS_LOAD_NEW = u"""/* ---------- 加载（小程序适配：数据已内联为 JS 模块，同步就绪） ---------- */

function applyData(json) {
  meta = json.meta || null;
  var list = (json.foods || []).slice();
  // 自建食物排在最前，便于优先命中（与 PWA 一致）
  var custom = loadCustom();
  foods = custom.concat(list);
  buildIndex();
  status.state = 'ready';
  status.source = 'json';
  status.count = foods.length;
  return status;
}

/**
 * 同步就绪版的 load()。保留 Promise 形态是为了与 PWA 调用方（FoodStore.ready().then(...)）
 * 完全兼容 —— 页面代码两边可以长得一样。
 * ⚠️ 失败时仍降级到 FALLBACK，不抛异常：FALLBACK 分支是「功能不能整块消失」的保证。
 */
function load() {
  if (status.state === 'ready') return Promise.resolve(status);
  if (loadingPromise) return loadingPromise;

  loadingPromise = new Promise(function (resolve) {
    try {
      pyMap = PY || {};
      if (!DATA || !DATA.foods || !DATA.foods.length) throw new Error('食物库模块为空');
      resolve(applyData(DATA));
    } catch (err) {
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
      resolve(status);
    }
  });

  return loadingPromise;
}

function ready() { return load(); }"""

fs_m = fs_src
for _pat, _rep in FOODSTORE_REPL:
    fs_m, _n = re.subn(_pat, _rep, fs_m)
    if _n != 1:
        raise SystemExit(u"❌ food-store 适配规则命中 %d 次（预期 1）：%s" % (_n, _pat[:70]))
fs_m, _n = FS_LOAD_RE.subn(FS_LOAD_NEW, fs_m)
if _n != 1:
    raise SystemExit(u"❌ food-store 的「加载」整段替换命中 %d 次（预期 1）" % _n)

fs_js = (u"/* lib/food-store.js —— 由 promo/mp_build.py 从 js/food-store.js 生成，勿手工编辑。\n"
         u" * 食物搜索 / 索引层。搜索相关函数与 PWA 逐字节一致；差异只在「数据源 / 自建食物落盘 /\n"
         u" * 加载方式」三处小程序适配，逐条写在文件末尾的适配说明里。\n"
         u" */\n") + fs_m.rstrip() + u"\n"

fs_js += (u"\n/* ============================================================\n"
          u" * 小程序适配说明（与 PWA 的差异，逐条列明）\n"
          u" *   1) 数据源：不再 fetch，data/foods.js + data/py-initials.js 同步 require\n"
          u" *   2) 自建食物：localStorage → wx.setStorageSync（键名 jianpan_custom_foods_v1 不变，\n"
          u" *      getStorageSync 兼容 PWA 留下的 JSON 串形态 ⇒ 迁移过来能直接读）\n"
          u" *   3) load() 简化：数据同步就绪，不再需要「懒加载 + 失败降级」两段式；\n"
          u" *      FALLBACK 分支保留，失败时功能不整块消失\n"
          u" *   4) 多导出 CUSTOM_KEY / loadCustom / saveCustom，供 lib/migrate.js 搬自建食物\n"
          u" * ⚠️ 除以上四点，score / search / buildIndex / initialsOf / toGrams 与 PWA 逐字节一致\n"
          u" *    —— 搜索排序口径必须一致，否则用户在两端搜同一个词会得到不同结果。\n"
          u" * ============================================================ */\n"
          u"module.exports = FoodStore;\n")
emit(os.path.join(MINI, "lib", "food-store.js"), fs_js, u"食物搜索层（同步数据源 + wx storage）")

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
if de_dom_done:
    lines.append(u"  ↗ 其中 %d 个是 DE_DOM 从「渲染档」救回「纯计算档」的（DOM 行换成钩子调用）：" % len(de_dom_done))
    for n in de_dom_done:
        lines.append(u"      · %s" % n)
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
