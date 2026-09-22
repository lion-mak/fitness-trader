# -*- coding: utf-8 -*-
r"""
mp_wxss_check.py —— 用【微信开发者工具自带的真编译器 wcsc.exe】编译全部 .wxss，
一次性列全编译错误 + 顺带算出「会静默失效的 HTML 标签选择器」清单。

为什么必须有这个脚本：
  mp_lint.py 只做静态文本检查（括号配平 / import 路径 / 标签配平），**不做真编译**，
  因此漏掉了 `* { }` 通配符选择器这类「文本看着合法、编译器判死」的错误 ——
  2026-09-22 开发者工具报「编译 .wxss 文件错误」导致整包白屏，就是它放过去的。
  ⇒ 结论：样式改动必须过真编译器，静态检查不能替代。

wcsc 位置：<开发者工具>/resources/app.asar.unpacked/node_modules/wcc-exec/wcsc.exe

调用要点（2026-09-22 实测定稿，踩过的坑都在这）：
  1. **没有 CLI 帮助可读**：`wcsc` 不打印错误，`-h`/`--version` 才打印 usage。
  2. **输出编码是 GBK/ANSI**（不是 UTF-8）⇒ 必须 `decode("gbk")`。
  3. **stdout 是编译产物，不是错误**：把 stdout 当报错会把 PASS 的文件误判成 FAIL
     （产物里带 `%%HERESUFFIX%%` 前缀，那是 wcsc 给 IDE 用的占位）。
     判错只看 **stderr 里以 `ERR:` 开头的行**。
  4. **`@import` 的文件必须作为参数一起传进来**，且 root 在前、被 import 的在后：
       wcsc -pc 2 <root.wxss> <imported.wxss>
     否则报假警报 `path `..\..\x.wxss` not found`。
  5. **路径用正斜杠、相对 miniprogram/ 更稳**（反斜杠会被 wcsc 渲染成 `////` 畸形路径）；
     配合 `cwd=miniprogram`。
  6. wcsc **每次只报第一个错**并退出 ⇒ 修完必须重跑，直到 0 错。

用法：
  python promo/mp_wxss_check.py
  退出码 0 = 全部通过；1 = 有编译错误
  报告落盘 promo/_wxss_check_out.txt
"""
import io
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


def compile_one(rel):
    """返回 (ok, err_text, product)。product 仅 app.wxss 用来抽标签清单。"""
    deps = resolve_imports(rel)
    # root 在前，被 import 的在后（顺序在实测中重要）
    args = [u"-pc", str(len(deps))] + deps
    try:
        p = subprocess.run([WCSC] + args, capture_output=True, timeout=90, cwd=MINI)
    except Exception as e:
        return False, u"EXEC FAIL: %s" % e, u""
    err = (p.stderr or b"").decode("gbk", "replace")
    prod = (p.stdout or b"").decode("gbk", "replace")
    bad = [l.strip() for l in err.split(u"\n") if l.strip().startswith(u"ERR")]
    if bad or p.returncode != 0:
        return False, (u"\n".join(bad) or err.strip() or u"rc=%s" % p.returncode), prod
    return True, u"", prod


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
    bad = []
    for rel in files:
        ok, err, prod = compile_one(rel)
        deps = resolve_imports(rel)
        note = u" [+import %s]" % u", ".join(deps[1:]) if len(deps) > 1 else u""
        if ok:
            log(u"[ OK ] %s%s" % (rel, note))
        else:
            log(u"[FAIL] %s%s" % (rel, note))
            for l in err.split(u"\n"):
                log(u"        %s" % l.strip())
            bad.append((rel, err))

    log()
    log(u"共 %d 个 .wxss，失败 %d 个" % (len(files), len(bad)))

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
        log(u"RESULT=OK —— 全部 .wxss 通过官方编译器")
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
