# -*- coding: utf-8 -*-
"""
扫描 index.html <script> 里的顶层函数，按「是否碰 DOM / SVG / 浏览器 API」分档。
用途：给小程序迁移划分「纯计算层（可直接搬）」与「渲染层（必须重写）」。
"""
import io, re, os

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.html")
s = io.open(SRC, encoding="utf-8", newline="").read()

i = s.find("<script>")
j = s.rfind("</script>")
js = s[i + 8:j]
base_line = s[:i + 8].count("\n") + 1

DARK = re.compile(
    r"document\.|innerHTML|classList|querySelector|getElementById"
    r"|addEventListener|createElement|\.style\.|window\.|localStorage"
    r"|navigator\.|requestAnimationFrame|elementFromPoint|clientWidth"
    r"|clientHeight|getBoundingClientRect|<svg|<path|<rect |<circle|<polyline"
    r"|getContext|canvas"
)
PURE_HINT = re.compile(r"function\s+([A-Za-z_$][\w$]*)\s*\(")

# 找出所有 function 声明（含嵌套，用缩进判断顶层）
funcs = []
for m in re.finditer(r"^(function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{)", js, re.M):
    name = m.group(2)
    start = m.start()
    # 花括号配平找函数结束
    k = m.end() - 1
    depth = 0
    while k < len(js):
        c = js[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    body = js[start:k + 1]
    line = base_line + js[:start].count("\n")
    funcs.append({
        "name": name,
        "line": line,
        "nlines": body.count("\n") + 1,
        "nchars": len(body),
        "dark": sorted(set(x if isinstance(x, str) else x for x in []) ) or None,
        "darkHits": sorted(set(DARK.findall(body))),
        "body": body,
    })

pure = [f for f in funcs if not f["darkHits"]]
dark = [f for f in funcs if f["darkHits"]]
print("顶层函数共 %d 个：纯计算 %d 个 / 含渲染或浏览器 API %d 个" % (len(funcs), len(pure), len(dark)))
print()
print("=" * 96)
print("【A】纯计算 —— 可直接搬进小程序 lib/")
print("=" * 96)
tp = sum(f["nchars"] for f in pure)
for f in sorted(pure, key=lambda x: -x["nchars"]):
    print("  L%-5d %-30s %5d 行 %7d 字符" % (f["line"], f["name"], f["nlines"], f["nchars"]))
print("  合计 %d 个函数，%d 字符" % (len(pure), tp))
print()
print("=" * 96)
print("【B】含渲染 / 浏览器 API —— 必须重写")
print("=" * 96)
td = sum(f["nchars"] for f in dark)
for f in sorted(dark, key=lambda x: -x["nchars"]):
    print("  L%-5d %-30s %5d 行  %s" % (f["line"], f["name"], f["nlines"], ",".join(f["darkHits"][:6])))
print("  合计 %d 个函数，%d 字符" % (len(dark), td))

# 输出纯函数名单，供下一步抽取
OUTDIR = os.path.dirname(os.path.abspath(__file__))
with io.open(os.path.join(OUTDIR, "_pure_list.txt"), "w", encoding="utf-8", newline="") as fp:
    for f in pure:
        fp.write("%s\t%d\t%d\n" % (f["name"], f["line"], f["nchars"]))

# 报告同时落盘（沙箱 stdout 有时被吞）
with io.open(os.path.join(OUTDIR, "_scan_report.txt"), "w", encoding="utf-8", newline="") as fp:
    fp.write("顶层函数共 %d 个：纯计算 %d 个 / 含渲染或浏览器 API %d 个\n\n" % (len(funcs), len(pure), len(dark)))
    fp.write("【A】纯计算 —— 可直接搬进小程序 lib/（共 %d 个，%d 字符）\n" % (len(pure), tp))
    for f in sorted(pure, key=lambda x: -x["nchars"]):
        fp.write("  L%-5d %-30s %5d 行 %7d 字符\n" % (f["line"], f["name"], f["nlines"], f["nchars"]))
    fp.write("\n【B】含渲染 / 浏览器 API —— 必须重写（共 %d 个，%d 字符）\n" % (len(dark), td))
    for f in sorted(dark, key=lambda x: -x["nchars"]):
        fp.write("  L%-5d %-30s %5d 行  %s\n" % (f["line"], f["name"], f["nlines"], ",".join(f["darkHits"][:6])))
print("done")
