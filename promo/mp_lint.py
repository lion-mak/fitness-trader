# -*- coding: utf-8 -*-
"""
mp_lint.py —— 小程序工程静态检查（编译前把关）

为什么需要：微信开发者工具的报错常常是"结果"而非"原因"（比如某个 bindtap 指向
不存在的方法，点下去才崩）。能在本地查出来的，就不要留到工具里用肉眼找。

检查项：
  1. app.json 合法，且 pages 里每个路径都有 .js/.json/.wxml/.wxss 四件套
  2. tabBar 的 iconPath / selectedIconPath 文件真实存在（缺文件会直接编译失败）
  3. 所有 .js 语法正确（调 node --check，不执行）
  4. 所有页面 .json 合法
  5. WXML 标签配平（含自闭合）
  6. WXML 里 bind*/catch* 绑定的方法名，在同名 .js 里确实定义了
  7. WXSS 的 @import —— **页面 wxss 一律不许写**（2026-09-22 定稿：共享样式写 app.wxss
     末尾的适配层；跨文件 @import 会让开发者工具的文件清单缺文件 ⇒ 整包编译失败）。
     本项只校验「万一写了，目标文件是否存在」，禁令本身由第 9 项的 mp_wxss_check 判 FAIL。
  8. require() 的相对路径存在
  9. 🔴 **WXSS 真编译**（调用 mp_wxss_check.py → 开发者工具自带的 wcsc.exe）
     —— 新增于 2026-09-22，因为 1~8 全是静态检查，**放过了 `* { }` 通配符选择器**，
        导致开发者工具「编译 .wxss 文件错误」整包白屏。静态检查不能替代真编译。

用法：python promo/mp_lint.py
"""
import io, os, re, json, subprocess, sys

ROOT = os.environ.get("MINI_ROOT", r"E:\WeChatProjects\jianpan")
MINI = os.path.join(ROOT, "miniprogram")
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"

errs, warns, oks = [], [], []


def err(f, m): errs.append("%s：%s" % (f, m))
def warn(f, m): warns.append("%s：%s" % (f, m))
def read(p):
    return io.open(p, encoding="utf-8", newline="").read()


# ---------- 1. app.json 与页面四件套 ----------
app_json = os.path.join(MINI, "app.json")
try:
    app = json.loads(read(app_json))
    oks.append("app.json 合法（%d 个页面）" % len(app.get("pages", [])))
except Exception as e:
    err("app.json", "解析失败 %s" % e)
    print("\n".join(errs)); sys.exit(1)

for pg in app.get("pages", []):
    for ext in ("js", "json", "wxml", "wxss"):
        p = os.path.join(MINI, pg + "." + ext)
        if not os.path.isfile(p):
            err(pg, "缺 %s 文件（%s）" % (ext, os.path.relpath(p, MINI)))
oks.append("页面四件套齐全")

# ---------- 2. tabBar 图标 ----------
for it in app.get("tabBar", {}).get("list", []):
    for key in ("iconPath", "selectedIconPath"):
        ip = it.get(key)
        if not ip:
            err("tabBar", "「%s」缺 %s" % (it.get("text"), key)); continue
        if not os.path.isfile(os.path.join(MINI, ip)):
            err("tabBar", "「%s」的 %s 不存在：%s" % (it.get("text"), key, ip))
oks.append("tabBar 图标 %d 张全部存在" % (2 * len(app.get("tabBar", {}).get("list", []))))

# ---------- 3. JS 语法 ----------
js_files = []
for dp, dn, fn in os.walk(MINI):
    for f in fn:
        if f.endswith(".js"):
            js_files.append(os.path.join(dp, f))
bad = 0
for p in js_files:
    r = subprocess.run([NODE, "--check", p], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        bad += 1
        msg = (r.stderr or "").strip().split("\n")
        err(os.path.relpath(p, MINI), "语法错误 → " + (msg[0] if msg else "?"))
if not bad:
    oks.append("%d 个 .js 语法全部通过" % len(js_files))

# ---------- 4. 页面 json ----------
for dp, dn, fn in os.walk(MINI):
    for f in fn:
        if f.endswith(".json"):
            p = os.path.join(dp, f)
            try:
                json.loads(read(p))
            except Exception as e:
                err(os.path.relpath(p, MINI), "JSON 解析失败 %s" % e)
oks.append("全部 .json 合法")

# ---------- 5/6. WXML 标签配平 + 事件方法存在性 ----------
WXML_TAG = re.compile(r"<(/?)([A-Za-z][\w:-]*)((?:\s+[^<>]*?)?)(/?)>", re.S)
BIND = re.compile(r'\b(?:bind|catch|capture-bind|capture-catch|mut-bind):?([a-z]+)\s*=\s*"([^"{}]+)"')
VOID_HINT = ("input", "image")

for dp, dn, fn in os.walk(MINI):
    for f in fn:
        if not f.endswith(".wxml"):
            continue
        p = os.path.join(dp, f)
        src = re.sub(r"<!--.*?-->", "", read(p), flags=re.S)
        stack = []
        for m in WXML_TAG.finditer(src):
            closing, tag, attrs, selfclose = m.group(1), m.group(2), m.group(3), m.group(4)
            if closing:
                if not stack:
                    err(os.path.relpath(p, MINI), "多余的 </%s>" % tag)
                elif stack[-1][0] != tag:
                    err(os.path.relpath(p, MINI),
                        "</%s> 与最近的开标签 <%s> 不匹配" % (tag, stack[-1][0]))
                    stack.pop()
                else:
                    stack.pop()
            elif selfclose:
                pass
            else:
                stack.append((tag, m.start()))
        for tag, pos in stack:
            line = src[:pos].count("\n") + 1
            err(os.path.relpath(p, MINI), "标签 <%s> 未闭合（L%d）" % (tag, line))

        # 事件方法是否在对应 js 里定义
        js = os.path.join(dp, f[:-5] + ".js")
        if os.path.isfile(js):
            jsrc = read(js)
            for m in BIND.finditer(src):
                fn = m.group(2)
                if not re.search(r"(^|\s|\{|\s)%s\s*[:(]" % re.escape(fn), jsrc, re.M):
                    err(os.path.relpath(p, MINI), "绑定了 %s，但 %s 里没有该方法" % (fn, os.path.basename(js)))
        else:
            warn(os.path.relpath(p, MINI), "没有同名 .js（仅 wxml 存在）")
oks.append("WXML 标签配平 + 事件绑定全部有效")

# ---------- 7. WXSS @import ----------
for dp, dn, fn in os.walk(MINI):
    for f in fn:
        if not f.endswith(".wxss"):
            continue
        p = os.path.join(dp, f)
        for m in re.finditer(r'@import\s+["\']([^"\']+)["\']', read(p)):
            t = os.path.normpath(os.path.join(dp, m.group(1)))
            if not os.path.isfile(t):
                err(os.path.relpath(p, MINI), "@import 目标不存在：%s" % m.group(1))
oks.append("WXSS @import 全部有效")

# ---------- 8. require 路径 ----------
for p in js_files:
    src = read(p)
    for m in re.finditer(r'require\(\s*["\']([^"\']+)["\']\s*\)', src):
        spec = m.group(1)
        if not spec.startswith("."):
            continue
        t = os.path.normpath(os.path.join(os.path.dirname(p), spec))
        if not os.path.isfile(t) and not os.path.isfile(t + ".js"):
            err(os.path.relpath(p, MINI), "require 路径不存在：%s" % spec)
oks.append("require 相对路径全部有效")

# ---------- 9. WXSS 真编译（wcsc，开发者工具自带编译器）----------
# 🔴 这一项是 2026-09-22 补的，之前【漏了它】：
#    静态检查看不出 `* { margin:0 }` 这类「文本完全合法、编译器判死」的写法，
#    结果是开发者工具报「编译 .wxss 文件错误」→ **整包白屏 + tabBar 图标全变破图**
#    （图标加载不了只是连带现象，别去查图标）。
#    ⇒ 教训：样式改动必须过真编译器；静态检查**不能**替代真编译。
PROMO = os.path.dirname(os.path.abspath(__file__))
WXSS_CHECK = os.path.join(PROMO, "mp_wxss_check.py")
if os.path.isfile(WXSS_CHECK):
    r = subprocess.run([sys.executable, WXSS_CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode == 0:
        oks.append("WXSS 全部通过官方编译器 wcsc")
    else:
        detail = [l.strip() for l in (r.stdout or "").split("\n")
                  if l.strip().startswith("[FAIL]") or l.strip().startswith("ERR")]
        err("WXSS", "真编译失败：%s（完整报告 promo/_wxss_check_out.txt）"
            % (" / ".join(detail) if detail else "见报告"))
else:
    warn("WXSS", "未找到 mp_wxss_check.py —— 跳过了真编译，静态检查不能替代它！")

# ---------- 报告 ----------
out = []
out.append("mp_lint 报告 —— 小程序工程静态检查")
out.append("=" * 80)
out.append("工程：%s" % ROOT)
out.append("")
out.append("【通过】%d 项" % len(oks))
for s in oks:
    out.append("  ✓ " + s)
if warns:
    out.append("")
    out.append("【提示】%d 项" % len(warns))
    for s in warns:
        out.append("  · " + s)
out.append("")
if errs:
    out.append("【错误】%d 项" % len(errs))
    for s in errs:
        out.append("  ✗ " + s)
    out.append("")
    out.append("RESULT=FAIL")
else:
    out.append("【错误】0 项 —— 工程结构完整，且已通过官方 wcsc 编译器")
    out.append("")
    out.append("RESULT=OK")

text = "\n".join(out)
print(text)
io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lint_report.txt"),
        "w", encoding="utf-8", newline="").write(text + "\n")
sys.exit(1 if errs else 0)
