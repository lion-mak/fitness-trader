# -*- coding: utf-8 -*-
"""negctl_trade_modals.py —— 交易页 6 弹层对拍闸（mp_rect_trade_modals.py）的**专属负控**。

为什么不只跑一次正向就够：
  ⑥c 对拍是「两端比位置」的闸，最容易出的两种假象是
    ① 闸恒真（选择器全失效 ⇒ 全报「未测到」或 0 超阈值）；
    ② 闸太钝（改坏了却报 OK）。
  所以每道闸都要有一个「**故意撤回一处已验证修正**」的坏副本，用来证明闸真的会红，
  而且**只红在相关的那几个弹层上**（其余弹层仍绿 = 闸有分辨力，不是一响全响）。

两个 case 各对应一处 2026-09-23 修掉的真 bug：
  · ghostinline —— 撤回「`.sheet .ghost-btn` 恢复行内级」
      ⇒ 期望只有 **exList** 红（`.ghost-btn` dt=8，块级外边距合并吃掉那 8px）；
         foodSearch 的按钮在同款标记下间距本来就是 10 ⇒ 必须仍绿（分辨力证据）。
  · timeinput  —— 撤回「`.field .inp-time` 高 45」（压回 `.field input` 的 43）
      ⇒ 期望 **含时间输入的 3 个弹层**（foodSheet / exSheet / recEdit）逐个整体偏移 2px 变红；
         不含时间输入的 foodSearch / exList / customEx 必须仍绿。

判据沿用本工程的三态约定（见 memory）：坏副本必须
  OK    = 退出码非 0 且明细行里出现期望关键字；
  BAD   = 跑完了却没命中关键字 ⇒ 断言可能恒真/太钝，要重写坏副本；
  CRASH = 非零退出但没有汇总行 ⇒ 坏副本崩在断言之前，什么都没证明。

恢复方式：**不用手工还原**，直接重跑 mp_build.py（app.wxss 是生成物 ⇒ 天然回到正确内容），
再断言注入标记确实消失。
"""
import io
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import mp_ws                                                     # noqa: E402

# ⚠️ 小程序工程**不在** PWA 仓库里（PWA 仓库只有 promo/ 与 index.html）。
#    路径统一从 mp_ws.PROJ 取，别再硬编码一份（上一版写成 ROOT/miniprogram 直接 FileNotFoundError）。
APP = os.path.join(mp_ws.PROJ, "miniprogram", "app.wxss")
PY = r"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"
VENV = r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

MARK = "/* NEGCTL-TRADE-MODALS */"

CASES = {
    "ghostinline": {
        "inject": MARK + " .sheet .ghost-btn { display: block; }",
        "red": ["exList"],
        "green": ["foodSearch", "foodSheet", "customEx", "exSheet", "recEdit"],
        "must_contain": [".ghost-btn", "dt=8"],
        "desc": "撤回「.sheet .ghost-btn 恢复行内级」⇒ 块级外边距合并吃掉 8px",
    },
    "timeinput": {
        "inject": MARK + " .field .inp-time { height: 43px; }",
        "red": ["foodSheet", "exSheet", "recEdit"],
        "green": ["foodSearch", "exList", "customEx"],
        "must_contain": ["dt=-2"],
        "desc": "撤回「.field .inp-time 高 45」⇒ 含时间输入的弹层整体少 2px",
    },
}


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8", newline="").write(s)


def sections(out):
    """把输出按「── 弹层：<key> ──」切成 {key: 该段文本}。"""
    res = {}
    cur = None
    for ln in out.splitlines():
        if "── 弹层：" in ln:
            cur = ln.split("── 弹层：")[1].split("─")[0].strip()
            res[cur] = []
        elif cur:
            res[cur].append(ln)
    return {k: "\n".join(v) for k, v in res.items()}


ENV_MARKS = ("自动化端口", "测量失败", "灌存档失败", "无可用浏览器内核", "没回 windowHeight")


def run_gate():
    """跑一次对拍闸，返回 (退出码, 输出)。"""
    pr = subprocess.run([VENV, os.path.join(HERE, "mp_rect_trade_modals.py")],
                        cwd=ROOT, capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=900)
    return pr.returncode, (pr.stdout or "") + (pr.stderr or "")


def run_case(name, spec):
    print("=" * 88)
    print("负控 %s —— %s" % (name, spec["desc"]))
    print("=" * 88)
    orig = read(APP)
    if MARK in orig:
        print("⛔ 前置失败：app.wxss 里已经残留注入标记，先跑 mp_build.py")
        return 2

    write(APP, orig + "\n" + spec["inject"] + "\n")
    print("  已注入：%s" % spec["inject"])
    try:
        # ⚠️ 改 app.wxss 会让开发者工具**重新编译整包**，编译期间自动化会话不响应
        #    （实测报 `FAILED: timeout waiting for automator response`，卡在灌存档那步）。
        #    ⇒ 先等编译，再跑；若仍撞上环境超时，等更久重试一次。
        #    （早先手工跑对拍之所以没撞上，是因为注入与对拍之间隔了一次工具往返、编译已完成。）
        time.sleep(18)
        for attempt in (1, 2):
            if attempt > 1:
                print("  （上一轮撞上 IDE 重编译 ⇒ 再等 30s 重试）")
                time.sleep(30)
            code, out = run_gate()
            env_fail = (("合计超阈值：" not in out) and any(x in out for x in ENV_MARKS))
            if not env_fail:
                break
    finally:
        # 恢复：app.wxss 是 mp_build 的生成物，重跑即回到正确内容
        rb = subprocess.run([PY, os.path.join(HERE, "mp_build.py")], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=300)
        back = read(APP)
        restored = (MARK not in back) and rb.returncode == 0
        print("  恢复 app.wxss（重跑 mp_build）：%s" % ("✅" if restored else "❌ 仍有残留！"))
        if not restored:
            write(APP, orig)
            print("  （已用备份兜底写回）")

    ok_summary = "合计超阈值：" in out
    print("  退出码 = %s" % code)
    if not ok_summary:
        # ⚠️ 必须把闸的原始输出尾巴打出来：否则分不清「坏副本崩在断言之前」还是
        #    「环境没就绪（端口/浏览器/灌存档失败）」—— 后者什么都没证明，不能当成负控失败。
        tail = out.strip().splitlines()[-14:]
        print("  ── 闸的原始输出（尾 14 行）──")
        for ln in tail:
            print("     " + ln)
        if any(x in out for x in ENV_MARKS):
            print("  ⇒ ENV：环境未就绪（非坏副本所致）—— 本次负控不作数，先修环境")
            return 3
        print("  ⇒ CRASH：非零退出且无汇总行 —— 坏副本崩在断言之前，什么都没证明")
        return 2
    if code == 0:
        print("  ⇒ BAD：闸跑完了但退出码为 0 ⇒ **闸根本没在报警**（假保证）")
        return 2

    sec = sections(out)
    fails = []
    # 1) 期望关键字必须出现在明细里（且确实是 FAIL 汇总）
    if "RESULT=FAIL" not in out:
        fails.append("输出里没有 RESULT=FAIL")
    for kw in spec["must_contain"]:
        if kw not in out:
            fails.append("明细里没出现期望关键字 %s ⇒ 断言可能恒真/太钝" % kw)
    # 2) 该红的弹层必须红
    for k in spec["red"]:
        seg = sec.get(k)
        if seg is None:
            fails.append("输出里找不到弹层段 %s（脚本崩了？）" % k)
        elif "超阈值：0 个" in seg:
            fails.append("弹层 %s 应当变红，却报 0 超阈值" % k)
    # 3) 不该红的弹层必须仍绿（分辨力）
    for k in spec["green"]:
        seg = sec.get(k)
        if seg is None:
            fails.append("输出里找不到弹层段 %s" % k)
        elif "超阈值：0 个" not in seg:
            fails.append("弹层 %s 本不该受影响却变红了（闸没有分辨力）" % k)

    if fails:
        print("  ⇒ BAD：")
        for f in fails:
            print("     - " + f)
        return 2
    print("  ⇒ OK：退出码非 0、命中 %s、且只有 %s 变红（%s 仍绿）"
          % ("、".join(spec["must_contain"]), "/".join(spec["red"]), "/".join(spec["green"])))
    return 0


def main():
    args = sys.argv[1:]
    names = [a for a in args if not a.startswith("-")] or list(CASES)
    bad = []
    for n in names:
        if n not in CASES:
            print("未知 case：%s（可选 %s）" % (n, "/".join(CASES)))
            return 2
        rc = run_case(n, CASES[n])
        if rc != 0:
            bad.append(n)
    print()
    print("=" * 88)
    if bad:
        print("负控 RESULT=FAIL —— %s" % "、".join(bad))
        return 1
    print("负控 RESULT=OK —— %d 个 case 全部按预期报警且只红在相关弹层" % len(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
