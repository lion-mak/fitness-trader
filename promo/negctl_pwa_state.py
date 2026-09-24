# -*- coding: utf-8 -*-
"""negctl_pwa_state.py —— pwa_gate_state.py 的专属负控。

分五块，把「闸真能红」这件事逐条钉死（每块都是不同的失败通道，不能只测一条就收工）：

  场景 ①  只坏化 CURVE_VER（保留保护模式）—— 运行时闸
          期望：闸红，但 A1/A2 **保持绿**（防御层真的兜住了）、C1 **红**（保护模式确实触发了）
  场景 ②  坏化 CURVE_VER + **三层防御全拆**（保护模式 / 缩水闸 / 空档哨兵）—— 运行时闸
          期望：闸红，且 A1/A2 **红**（证明闸真能检出「存档被空档覆盖」）
          ⚠️ 只拆一层是**故意不够**的：2026-09-25 之后的防线是分层的，剩下的层会接着兜住 ——
             这是分层的正确表现，所以要全拆才能证明 A1/A2 不是假保证。
  场景 ③  拆掉「空档哨兵」—— 运行时闸
          期望：C5/C6 **红**（证明这条新哨兵不是摆设；它红才说明它真在拦）
  场景 ④  拆掉 `takeSnapshot()` 调用 —— 运行时闸
          期望：A7/A9/A10 **红**（证明「快照环」这条回滚通路被真断言覆盖了）
  静态 4 例  S1/S2/S3/S4 各造一个坏样本（**纯内存**，不动文件、不起浏览器）——
          期望：对应那条必须报红，其余不受影响

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
         u"    showSaveGuard('read-failed');\n"
         u"    return;\n"
         u"  }\n")
BAD_GUARD = u"  /* 负控·临时拆掉保护模式：复现修复前的形态 */\n"

# 场景②：连**启动期缩水闸**一起拆掉 —— 2026-09-25 之后防线是分层的：
#   保护模式挡「读不出来」、缩水闸挡「启动期写少了」、空档哨兵挡「任何时刻被清零」。
#   只拆其中一层已经复现不了事故（另一层会接着兜住）—— 这是分层的正确表现，
#   所以场景②必须三层全拆，才能证明 A1/A2「存档没被覆盖」这条断言真会红。
SHRINK = (u"  if (!__booted && __loadedCounts) {\n"
          u"    const now = __recordCounts(state), lost = [];\n"
          u"    Object.keys(__loadedCounts).forEach(function (k) {\n"
          u"      if (now[k] < __loadedCounts[k]) lost.push(k + ' ' + __loadedCounts[k] + '\u2192' + now[k]);\n"
          u"    });\n"
          u"    if (lost.length) {\n"
          u"      console.error('[存档] 缩水闸拦截：' + lost.join('\uff0c') + '（拒绝写入，磁盘上的原存档未动）');\n"
          u"      showSaveGuard('shrink');\n"
          u"      return;\n"
          u"    }\n"
          u"  }\n")
BAD_SHRINK = u"  /* 负控·临时拆掉缩水闸 */\n"

# 场景③：拆掉永久空档哨兵（记录归零时不再拒绝写入）。锚点＝哨兵块的开头到 return（逐字取自源文件）
SENTINEL = (u"  if (__loadedCounts) {\n"
            u"    const now2 = __recordCounts(state), wiped = [];\n"
            u"    Object.keys(__loadedCounts).forEach(function (k) {\n"
            u"      if (__loadedCounts[k] > 0 && now2[k] === 0) wiped.push(k + ' ' + __loadedCounts[k] + '\u21920');\n"
            u"    });\n"
            u"    if (wiped.length) {\n"
            u"      console.error('[存档] 空档哨兵拦截：' + wiped.join('\uff0c') + '（拒绝写入，磁盘上的原存档未动）');\n"
            u"      showSaveGuard('wipe');\n"
            u"      return;\n"
            u"    }\n"
            u"  }\n")
BAD_SENTINEL = u"  /* 负控·临时拆掉空档哨兵 */\n"

# 场景④：拆掉「留快照」这一步（快照环失效）
SNAP_CALL = u"      takeSnapshot(raw);\n"
BAD_SNAP = u"      /* 负控·临时拆掉快照 */\n"

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
                # ⛔ 锚点漂移时不要抛异常崩掉整个负控（那是工具问题，不是产品问题）：
                #    报成「无汇总行 + 明确原因」，落到 CRASH 分支让人看见。
                return (-1, u'坏化锚点漂移：%r 命中 %d 次（改了被测代码就要同步更新锚点）'
                        % (a[:46], n),
                        [u'✗ 坏化锚点不唯一 —— 负控没能真正执行'], False)
            t = t.replace(a, b, 1)
        io.open(TARGET, u"w", encoding=u"utf-8", newline=u"").write(t)
        return run_gate()
    finally:
        io.open(TARGET, u"w", encoding=u"utf-8", newline=u"").write(orig)
        if os.path.exists(BAK):
            os.remove(BAK)


def has_any(fails, keys):
    return any(any(k in f for k in keys) for f in fails)


# ---------------- 静态四例：纯内存负控（不动文件、不起浏览器） ----------------
class Probe(object):
    """假闸：只收集失败项标签，用来跑 pwa_gate_state.static_checks()。"""

    def __init__(self):
        self.total = 0
        self.failed = []

    def ok(self, cond, label, got=u''):
        self.total += 1
        if not cond:
            self.failed.append(label)


def load_gate_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(u'_pwa_gate_mod', GATE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def static_negctl():
    """S1/S2/S3/S4 各造一个坏样本，逐一确认「那一条」真的会红。返回 (ok, 报告行)。"""
    m = load_gate_module()
    src = io.open(TARGET, encoding=u"utf-8", newline=u"").read()
    base = Probe()
    m.static_checks(base, lambda *a, **k: None, src)
    rows = []
    base_green = (not base.failed)
    rows.append(u"  静态基线：%d 项全绿 = %s" % (base.total, u"是" if base_green else u"否"))

    cases = []

    def s1_bad(s):
        n1 = s.count(EARLY_DECL)
        n2 = s.count(LATE_ANCHOR)
        if n1 != 1 or n2 != 1:
            raise AssertionError(u"S1 锚点不唯一：%d / %d" % (n1, n2))
        return s.replace(EARLY_DECL, BAD_EARLY, 1).replace(LATE_ANCHOR, BAD_LATE, 1)

    def s2_bad(s):
        # 多塞一个空 catch ⇒ 超过基线（棘轮必须响）
        return s.replace(u"<script>", u"<script>\ntry { x(); } catch (e) {}\n", 1)

    def s3_bad(s):
        # 注释里写「星号紧跟斜杠」，后面还有内容 ⇒ 注释被提前闭合
        return s.replace(u"<script>", u"<script>\n/* 注释写坏了 */.zz{color:red}\n", 1)

    def s4_bad(s):
        return s.replace(u"空档哨兵拦截", u"哨兵被改名", 1)

    for name, fn, want in [(u"S1 TDZ 静态扫描", s1_bad, u'S1 '),
                           (u"S2 空 catch 棘轮", s2_bad, u'S2 '),
                           (u"S3 注释提前闭合", s3_bad, u'S3 '),
                           (u"S4 安全网符号", s4_bad, u'S4 ')]:
        try:
            bad = fn(src)
        except AssertionError as e:
            rows.append(u"  ✗ %s：造坏样本失败（%s）" % (name, e))
            cases.append(False)
            continue
        if bad == src:
            rows.append(u"  ✗ %s：坏化没生效（锚点没命中）" % name)
            cases.append(False)
            continue
        pr = Probe()
        m.static_checks(pr, lambda *a, **k: None, bad)
        hit = any(want in f for f in pr.failed)
        rows.append(u"  %s %s：造坏后该条报红 = %s%s" % (u"OK  " if hit else u"✗   ", name,
                                                       u"是" if hit else u"否",
                                                       u"" if hit else u"  实际失败=%s" % pr.failed[:3]))
        cases.append(hit)
    return (base_green and all(cases)), rows


def main():
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    if os.path.exists(BAK):
        log(u"⚠️ 发现残留备份（上次被强杀）⇒ 先自愈，再开工")
        restore()

    log(u"# pwa_gate_state.py 专属负控（静态 4 例 + 运行时 4 场景）")
    log()

    # ---- S 静态四例（秒级，先跑）----
    log(u"【S】静态闸负控（纯内存坏样本，不动文件）")
    s_ok, s_rows = static_negctl()
    for r in s_rows:
        log(r)
    log(u"      → %s" % (u"OK：四条静态闸都能被对应的坏样本打红" if s_ok else u"BAD：有静态闸打不红（假保证）"))
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
    log(u"【2】场景②：CURVE_VER 挪后 + **三层防御全拆**（复现修复前形态）")
    rc2, _o2, f2, s2 = broken_run([(EARLY_DECL, BAD_EARLY), (LATE_ANCHOR, BAD_LATE),
                                   (GUARD, BAD_GUARD), (SHRINK, BAD_SHRINK),
                                   (SENTINEL, BAD_SENTINEL)])
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

    # ---- 场景 ③：拆掉空档哨兵 ----
    log()
    log(u"【3】场景③：拆掉「空档哨兵」")
    rc4, _o4, f4, s4 = broken_run([(SENTINEL, BAD_SENTINEL)])
    log(u"      退出码 = %s（期望 ≠0）  有汇总行 = %s" % (rc4, u"是" if s4 else u"否"))
    for l in f4[:10]:
        log(u"        " + l)
    sentinel_red = has_any(f4, [u'C5 ', u'C6 '])
    log(u"      C5/C6 变红（= 哨兵真在拦） = %s" % (u"是" if sentinel_red else u"否"))
    if not s4:
        v3 = (u"CRASH", u"场景③坏副本崩在断言之前")
    elif rc4 != 0 and sentinel_red:
        v3 = (u"OK", u"打中：拆掉哨兵后「记录被清零仍会落盘」被抓")
    elif rc4 == 0:
        v3 = (u"BAD", u"场景③闸仍绿 ⇒ C5/C6 是假保证")
    else:
        v3 = (u"BAD", u"场景③打偏：期望 C5/C6 变红，实际失败项=%s" % f4[:3])
    log(u"      → %s：%s" % v3)

    # ---- 场景 ④：拆掉快照环 ----
    log()
    log(u"【4】场景④：拆掉 `takeSnapshot()` 调用（快照环失效）")
    rc5, _o5, f5, s5 = broken_run([(SNAP_CALL, BAD_SNAP)])
    log(u"      退出码 = %s（期望 ≠0）  有汇总行 = %s" % (rc5, u"是" if s5 else u"否"))
    for l in f5[:10]:
        log(u"        " + l)
    snap_red = has_any(f5, [u'A7 ', u'A9 '])
    log(u"      A7/A9 变红（= 快照环真被断言覆盖） = %s" % (u"是" if snap_red else u"否"))
    if not s5:
        v4 = (u"CRASH", u"场景④坏副本崩在断言之前")
    elif rc5 != 0 and snap_red:
        v4 = (u"OK", u"打中：快照没生成会被闸逮到")
    elif rc5 == 0:
        v4 = (u"BAD", u"场景④闸仍绿 ⇒ A7/A9 是假保证")
    else:
        v4 = (u"BAD", u"场景④打偏：期望 A7/A9 变红，实际失败项=%s" % f5[:3])
    log(u"      → %s：%s" % v4)

    # ---- 5 还原后复跑，确认回绿（排除污染）----
    log()
    rc3, out3, _f3, _s3 = run_gate()
    back = (rc3 == 0 and u"RESULT=OK" in out3)
    log(u"【5】还原后复跑  退出码=%s（期望 0）  回绿=%s" % (rc3, u"是" if back else u"否"))
    if not back:
        log(u"      ⚠️ 没回绿 —— 先怀疑残留污染（index.html 是否被其它改动动过）")

    log()
    log(u"【结论】静态=%s  场景①=%s  场景②=%s  场景③=%s  场景④=%s"
        % (u"OK" if s_ok else u"BAD", v1[0], v2[0], v3[0], v4[0]))
    good = (s_ok and v1[0] == u"OK" and v2[0] == u"OK" and v3[0] == u"OK" and v4[0] == u"OK" and back)
    log(u"RESULT=%s%s" % (u"OK" if good else u"BAD",
                        u"（负控健康：静态四条 + 兜住/兜不住/哨兵/快照都能被打红，还原必绿）"
                        if good else u""))
    flush_out()
    return 0 if good else 1


if __name__ == u"__main__":
    sys.exit(main())
