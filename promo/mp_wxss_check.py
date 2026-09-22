# -*- coding: utf-8 -*-
r"""
mp_wxss_check.py —— 用【微信开发者工具自带的真编译器 wcsc.exe】编译全部 .wxss，
一次性列全编译错误 + 顺带算出「会静默失效的 HTML 标签选择器」清单。

为什么必须有这个脚本：
  mp_lint.py 只做静态文本检查（括号配平 / import 路径 / 标签配平），**不做真编译**，
  因此漏掉了两类「文本看着合法、编译器判死」的错误：
    ① `* { }` 通配符选择器（WXSS 不支持）            —— 2026-09-22 白屏事故 A
    ② 页面里的 `@import` 指向的文件没进编译单元       —— 2026-09-22 白屏事故 B
  ⇒ 结论：样式改动必须过真编译器，静态检查不能替代。

wcsc 位置：<开发者工具>/resources/app.asar.unpacked/node_modules/wcc-exec/wcsc.exe

调用要点（2026-09-22 实测定稿，踩过的坑都在这）：
  1. **没有 CLI 帮助可读**：`wcsc` 不打印错误，`-h`/`--version` 才打印 usage。
  2. **输出编码是 GBK/ANSI**（不是 UTF-8）⇒ 必须 `decode("gbk")`。
  3. **stdout 是编译产物，不是错误**：把 stdout 当报错会把 PASS 的文件误判成 FAIL。
     判错只看 **stderr 里以 `ERR:` 开头的行**。（产物里也含 "error" 字样，
     所以**不要**拿 `ERR|error` 去正则匹配 stdout —— 这坑骗过我一次。）
  4. **路径用正斜杠、相对 miniprogram/ 更稳**（反斜杠会被 wcsc 渲染成 `////` 畸形路径），
     配合 `cwd=miniprogram`。
  5. wcsc **每次只报第一个错**并退出 ⇒ 修完必须重跑，直到 0 错。
  6. `-pc N` = page wxss files count，即「前 N 个文件是页面样式」。

⭐ 两道主检（都是 2026-09-22 新增，对应上面两类事故）：
  A. **工具等价整包编译** —— 按开发者工具构造编译单元的真实形状：
       files = [各页 wxss ... , app.wxss]   pageCount = 页面数
     **刻意不额外传任何 import 文件**，因为工具的编译单元里只有「app.wxss + 各页 wxss
     + 它自己文件索引里剩下的 wxss」；索引是打开项目时建的，之后脚本新增的文件
     （尤其新目录）不在其中 ⇒ 被 import 的文件进不了清单 ⇒
     `path ... not found from ...` ⇒ 整包编译失败 ⇒ 白屏。
     这道闸就是把这个失败模式在本地提前复现。
  B. **页面禁写 @import** —— 由上一条推出的工程规矩：共享样式写 app.wxss 末尾的
     适配层（由 mp_build.py 追加），页面 wxss 只放本页增量。命中直接 FAIL。

用法：
  python promo/mp_wxss_check.py
  退出码 0 = 全部通过；1 = 有编译错误；2 = 脚本自身异常
  报告落盘 promo/_wxss_check_out.txt
"""
import io
import json
import os
import re
import subprocess
import sys

WCSC = u"D:\\微信web开发者工具\\resources\\app.asar.unpacked\\node_modules\\wcc-exec\\wcsc.exe"
MINI = u"E:\\WeChatProjects\\jianpan\\miniprogram"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"_wxss_check_out.txt")

_lines = []


def log(s=u""):
    _lines.append(s)


def find_wxss():
    hits = []
    for root, dirs, files in os.walk(MINI):
        dirs[:] = [d for d in dirs if d not in (u"node_modules", u"_unused_template")]
        for f in files:
            if f.endswith(u".wxss"):
                hits.append(os.path.relpath(os.path.join(root, f), MINI).replace(u"\\", u"/"))
    return sorted(hits)


def read_pages():
    """从 app.json 读页面列表 —— 工具构造编译单元时用的就是这份清单。

    顺带一说：**不要把 styles/ 之类的共享目录加进 pages**，那会让它被当成页面样式。
    """
    p = os.path.join(MINI, u"app.json")
    try:
        cfg = json.loads(io.open(p, encoding="utf-8").read())
        return list(cfg.get(u"pages", []))
    except Exception as e:
        log(u"⚠️ 读 app.json 失败：%s" % e)
        return []


def resolve_imports(rel, seen=None):
    """递归收集 rel 的 @import 依赖（相对 miniprogram/ 的 posix 相对路径）。"""
    if seen is None:
        seen = []
    if rel in seen:
        return seen
    seen.append(rel)
    path = os.path.join(MINI, rel.replace(u"/", os.sep))
    try:
        s = io.open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return seen
    base = os.path.dirname(rel)
    for m in re.finditer(r'@import\s+(?:url\()?["\']([^"\']+)["\']', s):
        dep = os.path.normpath(os.path.join(base, m.group(1))).replace(u"\\", u"/")
        if os.path.isfile(os.path.join(MINI, dep.replace(u"/", os.sep))):
            resolve_imports(dep, seen)
    return seen


def _run(args):
    """跑一次 wcsc，返回 (ok, err_text, product)。"""
    try:
        p = subprocess.run([WCSC] + args, capture_output=True, timeout=120, cwd=MINI)
    except Exception as e:
        return False, u"EXEC FAIL: %s" % e, u""
    err = (p.stderr or b"").decode("gbk", "replace")
    prod = (p.stdout or b"").decode("gbk", "replace")
    bad = [l.strip() for l in err.split(u"\n") if l.strip().startswith(u"ERR")]
    if bad or p.returncode != 0:
        return False, (u"\n".join(bad) or err.strip() or u"rc=%s" % p.returncode), prod
    return True, u"", prod


def compile_one(rel):
    """单文件编译（不注入 import 依赖 ⇒ 有 @import 就会暴露缺文件）。"""
    return _run([u"-pc", u"1", rel])


def compile_tool_shape(rel_pages):
    """按开发者工具的**真实形状**整包编译：各页 wxss 在前、app.wxss 在后，pageCount=页数。

    刻意不传任何 import 文件 —— 见文件头「两道主检 A」。
    返回 (ok, err_text, missing)：missing 是 app.json 里列了但文件不存在的页。
    """
    missing = []
    files = []
    for p in rel_pages:
        rel = u"./" + p + u".wxss"
        if os.path.isfile(os.path.join(MINI, (p + u".wxss").replace(u"/", os.sep))):
            files.append(rel)
        else:
            missing.append(rel)
    if os.path.isfile(os.path.join(MINI, u"app.wxss")):
        files.append(u"./app.wxss")
    if not files:
        return True, u"", missing
    ok, err, _prod = _run([u"-pc", u"%d" % len(rel_pages)] + files)
    return ok, err, missing


def strip_comments(s):
    """剥掉 CSS 注释 —— 否则文件里那句「不要写 @import」的**说明文字**会被自己的
    禁令扫描当成违规（假警报），而注释本来也不可能有 import 语义。"""
    return re.sub(r"/\*.*?\*/", u"", s, flags=re.S)


def import_ban():
    """扫描所有 .wxss 里的 @import（先剥注释）：页面 wxss 命中即 FAIL，app.wxss 命中给警告。"""
    page_hits, app_hits = [], []
    for rel in find_wxss():
        raw = io.open(os.path.join(MINI, rel.replace(u"/", os.sep)), encoding="utf-8",
                      errors="replace").read()
        s = strip_comments(raw)
        if u"@import" not in s:
            continue
        for m in re.finditer(r'@import[^;]*;', s):
            stmt = u" ".join(m.group(0).split())[:90]
            (app_hits if rel == u"app.wxss" else page_hits).append((rel, stmt))
    return page_hits, app_hits


def tag_scan(product):
    """从编译产物里找出被 wcsc 转成 `wx-*` 的标签选择器。

    含义：PWA 的 CSS 里写了 HTML 标签选择器（b / small / i / span / div ...），
    wcsc 会把它们映射成小程序内部标签 wx-b / wx-small ...，
    而我们的 WXML 里根本没有这些标签 ⇒ **规则写了但不生效，样式静默丢失**。
    这是「编译通过 ≠ UI 对」的主要来源，必须逐个改用 class 补回来。

    ⚠️ 产物里的 `wx-*` **既包含 PWA 原有的 HTML 标签，也包含 mp_build.py 展开
    `* {}` 时手动加进去的小程序原生标签**。后者本来就合法，必须排除，否则清单全是噪音。
    """
    found = sorted(set(re.findall(r"(?<![\w-])wx-([a-z][\w-]*)", product)))
    native = read_native_tags()
    if native is None:
        return found, None
    return [t for t in found if t not in native], native


def read_native_tags():
    """读 mp_build.py 落盘的展开标签清单（单一真源，别在这里硬编码第二份）。"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"_wxss_tags.txt")
    if not os.path.isfile(p):
        return None
    s = io.open(p, encoding="utf-8").read().strip()
    return set(t.strip() for t in s.split(u",") if t.strip())


def main():
    if not os.path.isfile(WCSC):
        log(u"⛔ 找不到 wcsc.exe：%s" % WCSC)
        log(u"   （开发者工具升级/换路径后要改本脚本顶部的 WCSC 常量）")
        flush(1)
        return

    log(u"# WXSS 真编译检查（wcsc.exe，开发者工具自带编译器）")
    log()

    files = find_wxss()
    pages = read_pages()
    bad = []

    # ── 主检 A：工具等价整包编译 ──
    log(u"## A. 工具等价整包编译（各页 wxss + app.wxss，pageCount=%d，不额外传 import）" % len(pages))
    ok, err, missing = compile_tool_shape(pages)
    for rel in missing:
        log(u"[FAIL] app.json 里列了这个页面但文件不存在：%s" % rel)
        bad.append((u"(缺页)", rel))
    if ok:
        log(u"[ OK ] 整包编译通过（工具不会报「编译 .wxss 文件错误」）")
    else:
        log(u"[FAIL] 整包编译失败 —— 开发者工具会报「编译 .wxss 文件错误」并整包白屏")
        for l in err.split(u"\n"):
            log(u"        %s" % l.strip())
        bad.append((u"(整包)", err))

    # ── 主检 B：页面禁写 @import ──
    log()
    log(u"## B. @import 禁令（共享样式必须写 app.wxss 末尾的适配层）")
    page_hits, app_hits = import_ban()
    if page_hits:
        log(u"[FAIL] 以下页面 .wxss 写了 @import（会让工具的文件清单缺文件 ⇒ 整包编译失败）：")
        for rel, stmt in page_hits:
            log(u"        %s : %s" % (rel, stmt))
        bad.append((u"(@import 禁令)", u"%d 处" % len(page_hits)))
    else:
        log(u"[ OK ] 没有页面 .wxss 使用 @import")
    for rel, stmt in app_hits:
        log(u"⚠️  app.wxss 里有 @import（全局层原则上也不需要，建议内联）：%s" % stmt)

    # ── 逐文件编译（抓单文件语法错） ──
    log()
    log(u"## C. 逐文件编译（单文件语法/选择器语法）")
    for rel in files:
        ok, err, prod = compile_one(rel)
        if ok:
            log(u"[ OK ] %s" % rel)
        else:
            log(u"[FAIL] %s" % rel)
            for l in err.split(u"\n"):
                log(u"        %s" % l.strip())
            bad.append((rel, err))

    log()
    log(u"共 %d 个 .wxss，失败项 %d" % (len(files), len(bad)))

    # ── 附加：静默失效的标签选择器清单 ──
    log()
    log(u"# 会静默失效的 HTML 标签选择器（编译能过，但 WXML 里无此标签 ⇒ 规则不生效）")
    ok_app, _, prod = compile_one(u"app.wxss")
    extra, native = tag_scan(prod) if ok_app else ([], None)
    if native is None:
        log(u"⚠️ 读不到 promo/_wxss_tags.txt（跑一次 mp_build.py 会生成）—— 无法排除原生标签，清单会含噪音")
    if extra:
        log(u"app.wxss 里的 PWA 独有标签：%s" % u", ".join(extra))
        log(u"⇒ 迁每页时在该页 .wxss 用 class 补等价规则（PWA 的 DOM 标签在小程序不存在）。")
    elif ok_app:
        log(u"（无 —— app.wxss 里没有 PWA 独有的 HTML 标签选择器；已排除 %d 个小程序原生标签）"
            % (len(native) if native else 0))

    if bad:
        log()
        log(u"=== 待修清单（编译器给的行号 = 该文件内的 行:列）===")
        for rel, err in bad:
            first = [l for l in err.split(u"\n") if l.startswith(u"ERR")]
            log(u"  - %s : %s" % (rel, first[0] if first else err[:120]))
        log()
        log(u"RESULT=FAIL")
    else:
        log()
        log(u"RESULT=OK —— 整包/逐文件均通过官方编译器，且无页面 @import")
    flush(1 if bad else 0)


def flush(code):
    txt = u"\n".join(_lines) + u"\n"
    io.open(OUT, "w", encoding="utf-8", newline="").write(txt)
    sys.stdout.write(txt)
    sys.exit(code)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        log(u"UNCAUGHT: " + traceback.format_exc())
        flush(2)
