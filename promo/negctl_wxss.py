# -*- coding: utf-8 -*-
r"""
negctl_wxss.py —— 「WXSS 真编译检查」的专属负控。

为什么单独写一个（而不是靠通用负控）：
  2026-09-22 事故的教训是「门卫是假的」—— mp_lint 的 1~8 项全是静态检查，
  看着全过，实际开发者工具编译不过、整包白屏。
  所以新增「真编译」这一项后，必须反过来证明它**真的会因坏数据 FAIL**，
  否则只是又立了一个恒真的假门卫。

负控做法（破坏 → 验证报错 → 恢复 → 验证恢复）：
  1. 备份 app.wxss
  2. 把 mp_build.py 展开出来的标签行**还原回通配符 `* {`**（即复现事故现场）
  3. 跑 mp_lint.py → 期望 rc≠0，且输出里出现 wcsc 的 `unexpected token`
  4. 恢复文件，重跑 → 期望 rc=0（证明判据是内容驱动的，不是环境脏）
  5. 落盘报告 promo/_negctl_wxss_out.txt

⚠️ 本脚本会临时改写 E:\WeChatProjects\jianpan\miniprogram\app.wxss，
   用 try/finally 保证恢复；跑完可用 mp_build.py 二次兜底重生成。
"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(u"E:\\WeChatProjects\\jianpan\\miniprogram", u"app.wxss")
LINT = os.path.join(HERE, u"mp_lint.py")
TAGFILE = os.path.join(HERE, u"_wxss_tags.txt")
OUT = os.path.join(HERE, u"_negctl_wxss_out.txt")
PY = sys.executable

_lines = []


def log(s=u""):
    _lines.append(s)


def run_lint():
    r = subprocess.run([PY, LINT], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or u"") + (r.stderr or u"")


def flush(code):
    txt = u"\n".join(_lines) + u"\n"
    io.open(OUT, "w", encoding="utf-8", newline="").write(txt)
    sys.stdout.write(txt)
    sys.exit(code)


def main():
    orig = io.open(TARGET, encoding="utf-8", newline="").read()
    tags = io.open(TAGFILE, encoding="utf-8").read().strip()
    needle = tags + u" {"

    log(u"# 「WXSS 真编译」专项负控")
    log()
    n = orig.count(needle)
    log(u"定位展开行：命中 %d 次（必须 =1）" % n)
    if n != 1:
        log(u"⛔ 定位失败 —— 说明 app.wxss 与 promo/_wxss_tags.txt 格式已漂移。")
        log(u"   先跑 promo/mp_build.py 重新生成，再重跑本负控。")
        log()
        log(u"RESULT=BAD（负控没能真正执行，等于验证了个寂寞）")
        flush(1)

    log()
    log(u"【1】复现事故：把展开行还原成通配符 `* {`")
    broken = orig.replace(needle, u"* {", 1)
    try:
        io.open(TARGET, "w", encoding="utf-8", newline="").write(broken)
        rc_bad, out_bad = run_lint()
        caught = (u"unexpected token" in out_bad) and (u"wcsc" in out_bad or u"WXSS" in out_bad)
        log(u"      mp_lint 退出码 = %s（期望 ≠0）" % rc_bad)
        log(u"      捕获到 wcsc 报错 = %s" % (u"是" if caught else u"否"))
        for l in out_bad.split(u"\n"):
            if l.strip().startswith(u"✗"):
                log(u"        " + l.strip())
    finally:
        io.open(TARGET, "w", encoding="utf-8", newline="").write(orig)
        log(u"      ✅ 已恢复 app.wxss（%d 字符）" % len(orig))

    log()
    log(u"【2】恢复后重跑，确认回到 OK（排除「环境脏所以恒 FAIL」）")
    rc_ok, out_ok = run_lint()
    log(u"      mp_lint 退出码 = %s（期望 0）" % rc_ok)

    log()
    if rc_bad != 0 and caught and rc_ok == 0:
        log(u"RESULT=OK —— 真编译检查确实会因 `* {}` FAIL，且恢复后回到 OK（非恒真、非恒假）")
        flush(0)
    else:
        log(u"RESULT=BAD —— 负控未通过：rc_bad=%s caught=%s rc_ok=%s" % (rc_bad, caught, rc_ok))
        flush(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        log(u"UNCAUGHT: " + traceback.format_exc())
        flush(2)
