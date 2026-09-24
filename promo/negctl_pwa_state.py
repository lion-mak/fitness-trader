# -*- coding: utf-8 -*-
"""negctl_pwa_state.py —— pwa_gate_state.py 的专属负控（两场景）。

为什么要两个场景：
  只坏化 CURVE_VER 时，2026-09-25 事故的「存档被覆盖」并不会发生 —— 因为同一版修复里
  加的 `__loadFailed` 保护模式会兜住（读失败 ⇒ saveState 拒绝写入）。
  于是闸里 A1/A2「存档没被覆盖」这两条断言**从未被证明能红** —— 那本身就是个假保证。
  所以分两场景，把「兜住」和「兜不住」都钉住：

  场景 ①  只坏化 CURVE_VER（保留保护模式）
          期望：闸红，但 A1/A2 **保持绿**（防御层真的兜住了）、C1 **红**（保护模式确实触发了）
  场景 ②  坏化 CURVE_VER + **同时拆掉保护模式**（＝修复前的形态）
          期望：闸红，且 A1/A2 **红**（证明闸真能检出「存档被空档覆盖」）

⚠️ 三态判据（不许只看 rc）：OK / BAD（打偏）/ CRASH（非零退出但没有汇总行）。
⚠️ 本脚本会临时改写 PWA 的 index.html。`try/finally` 挡不住 SIGTERM kill，
   故额外注册信号处理器 + 开工自检残留自愈（与 negctl_wxss*.py 同一套加固）。
"""
import io
import os
import signal
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, u"index.html")
BAK = os.path.join(HERE, u"_negctl_pwa_state_index.html.bak")
GATE = os.path.join(HERE, u"pwa_gate_state.py")
OUT = os.path.join(HERE, u"_negctl_pwa_state_out.txt")
PY = sys.executable

# ---- 坏化锚点（每处都必须唯一，脚本会断言）----
EARLY_DECL = u"const CURVE_VER = 2;\n\n/* 同上"
BAD_EARLY = u"/* 同上"
LATE_ANCHOR = u"function applyCurveUpgrade(s) {"
BAD_LATE = (u"/* 负控·临时挪回：声明在调用点之后 ⇒ TDZ */\n"
            u"const CURVE_VER = 2;\nfunction applyCurveUpgrade(s) {")

GUARD = (u"  if (__loadFailed) {\n"
         u"    console.error('[存档] 保护模式生效：拒绝写入，避免覆盖磁盘上的原存档（本次改动未落盘）');\n"
         u"    return;\n"
         u"  }\n")
BAD_GUARD = u"  /* 负控·临时拆掉保护模式：复现修复前的形态 */\n"

_log = []


def log(s=u""):
    _log.append(s)
    print(s)


def flush_out():
    try:
        io.open(OUT, u"w", encoding=u"utf-8", newline=u"").write(u"\n".join(_log))
    except Exception:
        pass


def restore():
    if os.path.exists(BAK):
        io.open(TARGET, u"w", encoding=u"utf-8", newline=u"").write(
            io.open(BAK, encoding=u"utf-8", newline=u"").read())
        os.remove(BAK)
        return True
    return False


def on_signal(signum, frame):
    print(u"\n收到信号 %s，先还原 index.html 再退出" % signum)
    rest = restore()
    print(u"  残留自愈：%s" % (u"已还原" if rest else u"无备份（无需还原）"))
    flush_out()
    raise SystemExit(143)


def run_gate():
    r = subprocess.run([PY, GATE], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    out = (r.stdout or u"") + (r.stderr or u"")
    fails = [l.strip() for l in out.split(u"\n") if l.strip().startswith(u"✗")]
    has_summary = (u"项，失败" in out)
    return r.returncode, out, fails, has_summary


def broken_run(transforms):
    """在坏副本上跑一次闸，无论成败都还原。返回 (rc, fails, has_summary, out)。"""
    orig = io.open(TARGET, encoding=u"utf-8", newline=u"").read()
    io.open(BAK, u"w", encoding=u"utf-8", newline=u"").write(orig)
    try:
        t = orig
        for a, b in transforms:
            n = t.count(a)
            if n != 1:
                raise AssertionError(u"坏化锚点不唯一：%r 命中 %d 次" % (a[:46], n))
            t = t.replace(a, b, 1)
        io.open(TARGET, u"w", encoding=u"utf-8", newline=u"").write(t)
        return run_gate()
    finally:
        io.open(TARGET, u"w", encoding=u"utf-8", newline=u"").write(orig)
        if os.path.exists(BAK):
            os.remove(BAK)


def has_any(fails, keys):
    return any(any(k in f for k in keys) for f in fails)


def main():
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    if os.path.exists(BAK):
        log(u"⚠️ 发现残留备份（上次被强杀）⇒ 先自愈，再开工")
        restore()

    log(u"# pwa_gate_state.py 专属负控（两场景）")
    log()

    # ---- 0 基线：正常文件下闸必须绿 ----
    rc0, out0, _f0, _s0 = run_gate()
    log(u"【0】基线：未坏化时跑闸  退出码=%s（期望 0）  闸绿=%s"
        % (rc0, u"是" if (rc0 == 0 and u"RESULT=OK" in out0) else u"否"))
    if not (rc0 == 0 and u"RESULT=OK" in out0):
        log(u"      ⛔ 基线就红了 —— 先修闸，再谈负控。")
        log()
        log(u"RESULT=BAD（基线不绿）")
        flush_out()
        return 1

    # ---- 场景 ①：只坏化 CURVE_VER（保留保护模式）----
    log()
    log(u"【1】场景①：CURVE_VER 挪到调用点之后（**保留**保护模式）")
    rc1, _o1, f1, s1 = broken_run([(EARLY_DECL, BAD_EARLY), (LATE_ANCHOR, BAD_LATE)])
    log(u"      退出码 = %s（期望 ≠0）  有汇总行 = %s" % (rc1, u"是" if s1 else u"否"))
    for l in f1[:10]:
        log(u"        " + l)
    kept = (not has_any(f1, [u'A1 ', u'A2 ']))
    guard_fired = has_any(f1, [u'C1 '])
    log(u"      A1/A2 保持绿（= 保护模式兜住了存档）= %s" % (u"是" if kept else u"否"))
    log(u"      C1 变红（= 保护模式确实触发、拒绝写入）= %s" % (u"是" if guard_fired else u"否"))
    if not s1:
        v1 = (u"CRASH", u"场景①坏副本崩在断言之前")
    elif rc1 != 0 and kept and guard_fired:
        v1 = (u"OK", u"打中：闸红，且证明「保护模式兜住了存档」")
    elif rc1 == 0:
        v1 = (u"BAD", u"场景①闸仍绿 ⇒ 闸是假保证")
    else:
        v1 = (u"BAD", u"场景①打偏：期望 A1/A2 保持绿 + C1 变红，实际失败项=%s" % f1[:3])
    log(u"      → %s：%s" % v1)

    # ---- 场景 ②：坏化 CURVE_VER + 拆掉保护模式（＝修复前的形态）----
    log()
    log(u"【2】场景②：CURVE_VER 挪后 + **拆掉**保护模式（复现修复前形态）")
    rc2, _o2, f2, s2 = broken_run([(EARLY_DECL, BAD_EARLY), (LATE_ANCHOR, BAD_LATE),
                                   (GUARD, BAD_GUARD)])
    log(u"      退出码 = %s（期望 ≠0）  有汇总行 = %s" % (rc2, u"是" if s2 else u"否"))
    for l in f2[:10]:
        log(u"        " + l)
    data_lost = has_any(f2, [u'A1 ', u'A2 '])
    log(u"      A1/A2 变红（= 闸检出了「存档被空档覆盖」）= %s" % (u"是" if data_lost else u"否"))
    if not s2:
        v2 = (u"CRASH", u"场景②坏副本崩在断言之前")
    elif rc2 != 0 and data_lost:
        v2 = (u"OK", u"打中：闸真能检出存档被覆盖")
    elif rc2 == 0:
        v2 = (u"BAD", u"场景②闸仍绿 ⇒ A1/A2 这两条断言是假保证")
    else:
        v2 = (u"BAD", u"场景②打偏：期望 A1/A2 变红，实际失败项=%s" % f2[:3])
    log(u"      → %s：%s" % v2)

    # ---- 3 还原后复跑，确认回绿（排除污染）----
    log()
    rc3, out3, _f3, _s3 = run_gate()
    back = (rc3 == 0 and u"RESULT=OK" in out3)
    log(u"【3】还原后复跑  退出码=%s（期望 0）  回绿=%s" % (rc3, u"是" if back else u"否"))
    if not back:
        log(u"      ⚠️ 没回绿 —— 先怀疑残留污染（index.html 是否被其它改动动过）")

    log()
    log(u"【结论】场景①=%s  场景②=%s" % (v1, v2))
    good = (v1[0] == u"OK" and v2[0] == u"OK" and back)
    log(u"RESULT=%s%s" % (u"OK" if good else u"BAD",
                        u"（负控健康：兜住/兜不住两态都钉住了，还原必绿）" if good else u""))
    flush_out()
    return 0 if good else 1


if __name__ == u"__main__":
    sys.exit(main())
