# -*- coding: utf-8 -*-
r"""
negctl_wxss_comment.py —— 「注释提前闭合」两道闸的**专属负控**：

  ① mp_wxss_check.py 的 **D 段静态闸**（comment_close_scan）
  ② mp_build.py 的 **写出前自检**（assert_comments_sane）

背景（v2.7.60 白屏级事故，2026-09-24）：
  ADAPT 适配层里为了说清「页面不许重写这两个前缀」，作者把两个类名连写成了
  「星号紧跟斜杠」再接另一类名 —— 那个序列本身就是 CSS 注释的结束符，
  注释在这里**提前闭合**，余下文字被当样式解析 ⇒ wcsc 报 unexpected ⇒
  开发者工具「编译 .wxss 文件错误」⇒ **整包白屏**。
  wcsc 只给一个落在注释行中间的行:列，字面上完全看不出根因
  ⇒ 当时靠「逐行删测」才定位，花了近一小时。两道闸就是为这个坑立的。

为什么必须有负控：这两道闸都是「新加的静态判据」，很可能恒真（永远不报）或
判据写错（永远报）。必须反过来证明「放上真实坏写法 → 真的红；恢复 → 真的绿」。

负控三段式（判「打中」必须三态可分：OK / BAD / CRASH）：
  【1】把坏注释块原地追加进 miniprogram/app.wxss
       → 期望 mp_wxss_check.py 退出码≠0，且输出同时含：
         · `被提前闭合`            （D 段判据命中）
         · `app.wxss:` 的行号定位  （定位可用）
         · `疑似注释【提前闭合】`  （explain_err 把编译器报错翻译成根因）
         · `unexpected`            （编译器**独立**也判它坏 —— 证明 D 段不是误报）
  【2】就地改坏 mp_build.py 的 ADAPT（安全写法 → 星号紧跟斜杠）
       → 期望 mp_build.py 退出码≠0、输出含我们那句自检文案，
         且 app.wxss **一个字节都没变**（证明自检拦在落盘之前，坏产物不落地）
       ⚠️ 必须校验自检文案：否则「崩在别处」会被误判成「打中」
  【3】恢复后重跑两闸 → 期望都回 0（排除「环境脏所以恒 FAIL」）

⚠️ 本脚本会临时改写 `miniprogram/app.wxss` 与 `promo/mp_build.py`。
   **SIGTERM/SIGINT 下 try/finally 不会执行**（这是 2026-09-23 踩过的坑：被 kill 后
   残留的坏规则会污染之后**所有** wxss 编译与元素级 rect 对拍，且症状极难归因）
   ⇒ 已注册信号处理 → 先恢复再 SystemExit(143)；
   ⇒ 并且批量写盘前先落 .bak，开工时若发现 .bak 存在则**先自愈**再干活。

用法：python promo/negctl_wxss_comment.py
      退出码 0 = RESULT=OK（两道闸都真的会被坏数据打红，且恢复后回绿）
"""
import hashlib
import io
import os
import signal
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MINI = u"E:\\WeChatProjects\\jianpan\\miniprogram"
TARGET = os.path.join(MINI, u"app.wxss")
BUILD = os.path.join(HERE, u"mp_build.py")
WXSS_CHECK = os.path.join(HERE, u"mp_wxss_check.py")
OUT = os.path.join(HERE, u"_negctl_wxss_comment_out.txt")
BAK_APP = os.path.join(HERE, u"_negctl_cmt_app.wxss.bak")
BAK_BUILD = os.path.join(HERE, u"_negctl_cmt_mp_build.py.bak")
PY = sys.executable

# ── 坏写法：两个类名前缀连写成「星号紧跟斜杠」 ──
# ⚠️ 下面这个字符串**故意**是坏的：它写进 WXSS 后会提前闭合注释。
#    在 Python 里它只是一段普通文本，所以本文件自身不受影响。
BAD_COMMENT = (
    u"\n/* 负控·临时插入的注释块（本负控跑完会自动删除，别手工留）\n"
    u"   连写两个类名前缀 `.rv-*/.ghost-btn` 会把注释在此处提前闭合，\n"
    u"   其后的文字被当成样式解析 —— 这正是 v2.7.60 白屏的真实成因。\n"
    u" */\n"
)
BAD_MARK = u"负控·临时插入的注释块"

# mp_build.py 里的安全写法 → 换回坏写法（负控【2】用）
# ⚠️ 坏化后的字符串里「星号紧跟斜杠」**必须真的相邻**（中间夹一个反引号就不成立了，
#    注释不会被截断、负控会静默变成「没打中」）⇒ 改这两个常量后务必看一眼 SAFE→BAD
#    的 diff 是不是变成了 `.rv-*/.ghost-btn` 这种形态。
SAFE_FORM = u"`.rv-*` 与 `.ghost-btn`"
BAD_FORM = u"`.rv-*/.ghost-btn`"

_lines = []


def log(s=u""):
    _lines.append(s)


def read(p):
    return io.open(p, encoding="utf-8", newline="").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8", newline="").write(s)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]


def run(script, timeout=180):
    # cwd 与 mp_gates.py 保持一致（ROOT = 仓库根），别让相对路径解析出两套结果
    r = subprocess.run([PY, script], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, cwd=ROOT)
    return r.returncode, (r.stdout or u"") + (r.stderr or u"")


# ────────────────────────────────────────────────────────────────
# 信号加固：被 kill 时也要把两个文件还原回去
# ────────────────────────────────────────────────────────────────
def restore_all(tag):
    """把 .bak 还原回原文件；返回还原了哪些路径。"""
    done = []
    for bak, dst in ((BAK_APP, TARGET), (BAK_BUILD, BUILD)):
        if os.path.isfile(bak):
            write(dst, read(bak))
            os.remove(bak)
            done.append(os.path.basename(dst))
    if done:
        sys.stderr.write(u"[negctl] %s 已恢复：%s\n" % (tag, u", ".join(done)))
    return done


def _on_signal(signum, _frame):
    # ⚠️ 这里刻意**不**走 flush（报告没意义了），先救文件再以 143 退出
    restore_all(u"SIG%d 中断" % signum)
    sys.exit(143)


def flush(code):
    txt = u"\n".join(_lines) + u"\n"
    io.open(OUT, "w", encoding="utf-8", newline="").write(txt)
    sys.stdout.write(txt)
    sys.exit(code)


def main():
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _on_signal)
        except Exception:
            pass

    log(u"# 「注释提前闭合」负控（D 段静态闸 + 构建器写出前自检）")
    log()

    # ── 开工自检：上一轮被 kill / 崩溃留下的残留，先自愈 ──
    healed = restore_all(u"开工自检")
    if healed:
        log(u"⚠️ 发现上一轮残留（%s），已先自愈再开工。" % u", ".join(healed))
    else:
        log(u"开工自检：无残留。")

    # 兜底：若 app.wxss 里还留着坏注释块（.bak 丢了的情况），用构建器重生成
    app_orig = read(TARGET)
    if BAD_MARK in app_orig:
        log(u"⚠️ app.wxss 里残留负控注释块 → 跑 mp_build.py 重生成。")
        rc, out = run(BUILD)
        log(u"      mp_build 退出码 = %s" % rc)
        app_orig = read(TARGET)
        if BAD_MARK in app_orig:
            log(u"⛔ 重生成后仍残留，停止（先手工修 app.wxss 再来跑）。")
            log()
            log(u"RESULT=BAD（负控没能真正执行，等于验证了个寂寞）")
            flush(1)

    build_orig = read(BUILD)
    safe_n = build_orig.count(SAFE_FORM)
    log(u"定位 mp_build.py 里的安全写法：命中 %d 次（必须 =1）" % safe_n)
    if safe_n != 1:
        log(u"⛔ 定位失败 —— mp_build.py 的 ADAPT 文案已漂移。")
        log(u"   本负控靠 `%s` 这个子串做坏化，文案一改就必须同步改这里。" % SAFE_FORM)
        log()
        log(u"RESULT=BAD（负控没能真正执行，等于验证了个寂寞）")
        flush(1)

    ok1 = ok2 = ok3 = False
    try:
        # ──【1】坏注释块追加进 app.wxss → D 段必须红，且编译器独立也判坏 ──
        log()
        log(u"【1】把坏注释块追加进 miniprogram/app.wxss")
        write(BAK_APP, app_orig)
        write(TARGET, app_orig + BAD_COMMENT)
        rc1, out1 = run(WXSS_CHECK)
        has_d = u"被提前闭合" in out1
        has_loc = u"app.wxss:" in out1
        has_hint = u"疑似注释【提前闭合】" in out1
        has_cc = u"unexpected" in out1
        log(u"      mp_wxss_check 退出码 = %s（期望 ≠0）" % rc1)
        log(u"      D 段判据命中（被提前闭合）        = %s" % (u"是" if has_d else u"否"))
        log(u"      给出 app.wxss:行 定位            = %s" % (u"是" if has_loc else u"否"))
        log(u"      explain_err 点出根因              = %s" % (u"是" if has_hint else u"否"))
        log(u"      编译器独立也判 unexpected         = %s" % (u"是" if has_cc else u"否"))
        for l in out1.split(u"\n"):
            s = l.strip()
            if s.startswith(u"[FAIL]") or s.startswith(u"app.wxss:") or s.startswith(u"ERR"):
                log(u"        " + s[:150])
        ok1 = (rc1 != 0) and has_d and has_loc and has_hint and has_cc
        write(TARGET, app_orig)
        os.remove(BAK_APP)
        log(u"      ✅ 已恢复 app.wxss")

        # ──【2】改坏 mp_build.py → 写出前自检必须拦住，且 app.wxss 不变 ──
        log()
        log(u"【2】把 mp_build.py 的安全写法改回坏写法，验证自检拦在落盘之前")
        write(BAK_BUILD, build_orig)
        write(BUILD, build_orig.replace(SAFE_FORM, BAD_FORM, 1))
        before = sha(TARGET)
        rc2, out2 = run(BUILD)
        after = sha(TARGET)
        hit_self = u"被【提前闭合】" in out2
        log(u"      mp_build 退出码 = %s（期望 ≠0）" % rc2)
        log(u"      自检文案命中（被【提前闭合】）    = %s" % (u"是" if hit_self else u"否"))
        log(u"      app.wxss 未被改写（%s → %s）    = %s"
            % (before, after, u"是" if before == after else u"否❗"))
        for l in out2.split(u"\n"):
            if u"提前闭合" in l or l.strip().startswith(u"⛔"):
                log(u"        " + l.strip()[:150])
        ok2 = (rc2 != 0) and hit_self and (before == after)
        write(BUILD, build_orig)
        os.remove(BAK_BUILD)
        log(u"      ✅ 已恢复 mp_build.py")

        # ──【3】恢复后两闸都要回绿（排除恒 FAIL） ──
        log()
        log(u"【3】恢复后重跑两闸，确认回到 OK")
        rc3a, out3a = run(WXSS_CHECK)
        rc3b, out3b = run(BUILD)
        log(u"      mp_wxss_check 退出码 = %s（期望 0）" % rc3a)
        log(u"      mp_build      退出码 = %s（期望 0）" % rc3b)
        ok3 = (rc3a == 0) and (rc3b == 0)
    finally:
        restore_all(u"finally")

    log()
    if ok1 and ok2 and ok3:
        log(u"RESULT=OK —— D 段静态闸与构建器自检都会因真实坏写法 FAIL，"
            u"且恢复后回到 OK（非恒真、非恒假；自检确实拦在落盘之前）")
        flush(0)
    log(u"RESULT=BAD —— 未通过：ok1(D段)=%s ok2(构建器自检)=%s ok3(恢复)=%s"
        % (ok1, ok2, ok3))
    flush(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        log(u"UNCAUGHT: " + traceback.format_exc())
        restore_all(u"异常退出")
        flush(2)
