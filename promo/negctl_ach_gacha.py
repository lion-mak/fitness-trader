# -*- coding: utf-8 -*-
"""negctl_ach_gacha.py —— 成就殿堂 / 抽卡 两套新断言的**专属负控**。

为什么必须有：通用负控只能证明「必败断言能变 FAIL」，
**不能证明新断言不是恒真的** ⇒ 每条新断言都要造一个「坏副本」单验：
把产品代码按某个具体口径改坏，确认**对应那一条**断言真的报 FAIL。

判据（三条件同时满足才算这条负控有效）：
  ① 套件「失败」——RESULT=FAIL **或** 退出码非 0
  ② 输出里出现 `✗` 行，且该行包含本 case 的 expect 关键字
  ③ 恢复原文件后，套件重新全过

⚠️ ①里「退出码非 0」这一条是吃过亏补上的（2026-09-22）：
   case 6 的坏副本最初写成 `showGachaResult(results)`，而该函数在 mp_build 之后
   **已不在 lib/calc.js 里**（它被判成 dirty、只在 PWA 侧存在）⇒ 抛 ReferenceError、
   进程直接崩、**一条 `✗` 行都没有**。老判据只看 `RESULT=FAIL` 字样 ⇒ 把「崩溃」
   误判成「坏副本没打中」。
⚠️ 但反过来，**光崩也不算合格**：崩溃发生在断言之前，等于什么也没证明
   ⇒ 所以 ① 与 ② 必须同时满足；只崩不给 `✗` 的 case 会被单独标 `CRASH` 提示改写。

⚠️ 每个 case 都改**真实工程文件**，所以用 try/finally 保证恢复；
   并在最后统一做一次「逐字节比对备份」确认没有残留改动。
⚠️ mp_build 生成的 lib/calc.js 也在这里被改（模拟「钩子签名退回去」）——
   负控用的是**备份恢复**、不重跑 mp_build，所以不会把 mp_build 的规则改掉。

用法：<managed-python> promo/negctl_ach_gacha.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
MINI = r"E:\WeChatProjects\jianpan\miniprogram"
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"

ACH = os.path.join(MINI, "pages", "achievements", "achievements.js")
GACHA = os.path.join(MINI, "pages", "gacha", "gacha.js")
CALC = os.path.join(MINI, "lib", "calc.js")

CASES = [
    {
        "name": "成就：进度条判据漏了「未解锁」条件（showBar = target>1）",
        "file": ACH,
        "old": "showBar: !got && a.target > 1,",
        "new": "showBar: a.target > 1,",
        "suite": "mp_ach_test.js",
        # ⚠️ 期望必须挑一个**观察得到差别**的断言：种子里已解锁的 5 项 target 全是 1
        #    （leek/untie/tryorder/open/firstboard），`target>1` 对它们恒 false
        #    ⇒ 「已解锁⇒不给进度条」在种子上根本区分不出来。改用 F 段解锁的 halfpos（target=5）。
        "expect": "解锁后「半仓干」转为已达成态",
    },
    {
        "name": "成就：kg 型进度文案退回 floor（toFixed(1) 丢掉）",
        "file": ACH,
        "old": "? (Math.min(prog, a.target).toFixed(1) + ' / ' + a.target + ' ' + a.unit)",
        "new": "? (Math.floor(Math.min(prog, a.target)) + ' / ' + a.target + ' ' + a.unit)",
        "suite": "mp_ach_test.js",
        "expect": "kg 型「主升浪」= 2.7 / 3 kg",
    },
    {
        "name": "成就：近期目标排序方向反了（升序）",
        "file": ACH,
        "old": "rows.sort(function (x, y) { return y.r - x.r; });",
        "new": "rows.sort(function (x, y) { return x.r - y.r; });",
        "suite": "mp_ach_test.js",
        "expect": "第 1 条 = 主升浪 90%",
    },
    {
        "name": "抽卡：碎片进度分母写成 need（不再减当前档下界）",
        "file": GACHA,
        "old": "pct: Math.round((own - calc.STAR_NEED[s]) / span * 100),",
        "new": "pct: Math.round(own / need * 100),",
        "suite": "mp_gacha_test.js",
        "expect": "2★ 且 4 片 ⇒ 进度 17%",
    },
    {
        "name": "抽卡：弹层丢掉 refundTotal（页面只读 results）",
        "file": GACHA,
        "old": "resultRefund: (info && info.refundTotal) || 0,",
        "new": "resultRefund: 0,",
        "suite": "mp_gacha_test.js",
        "expect": "弹层 resultRefund = 10",
    },
    {
        # 复刻**历史上那个真 bug**：自动生成的钩子空壳只转发 arguments[0]
        #   ⇒ `__fire('gachaResult', results)` 把数组当 info 传出去、refundTotal 被吞。
        # ⚠️ 早先这行写的是 `showGachaResult(results)`，那是**崩**而不是「打中」：
        #    mp_build 之后 lib/calc.js 里没有 showGachaResult（dirty 函数不进 calc.js）
        #    ⇒ ReferenceError + 无 `✗` 行。改成仍 defined 的 __fire 形态后，
        #    页面拿到的是数组 ⇒ info.results 为 undefined ⇒ 走「空结果 → refund 0」，
        #    是一条**能落到断言上**的 ✗。
        "name": "内核：drawCard 的钩子退回单参数（refundTotal 被吞）",
        "file": CALC,
        "old": "  __fire('gachaResult', { results: results, refundTotal: refundTotal });",
        "new": "  __fire('gachaResult', results);",
        "suite": "mp_gacha_test.js",
        "expect": "弹层 resultRefund = 10",
    },
]


def run_suite(script):
    """跑一套断言 → (合并后的输出, 退出码)。
    退出码必须一起返回：坏副本可能让套件**崩在断言之前**（抛异常 ⇒ rc≠0、无汇总行），
    这时既不能算「打中」也不能算「没打中」，要单独报出来（见 CRASH 分支）。"""
    env = dict(os.environ)
    env["NODE_PATH"] = r"C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules"
    env["PATH"] = os.path.dirname(NODE) + ";" + env.get("PATH", "")
    r = subprocess.run([NODE, os.path.join(HERE, script)], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return (r.stdout or "") + "\n" + (r.stderr or ""), r.returncode


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 92)
    print("成就 / 抽卡 断言专属负控 —— 每条新断言都要能被打坏")
    print("=" * 92)

    ok_all = True
    backups = {}
    for path in {c["file"] for c in CASES}:
        fd, tmp = tempfile.mkstemp(suffix=".bak")
        os.close(fd)
        shutil.copy2(path, tmp)
        backups[path] = tmp

    try:
        for i, c in enumerate(CASES, 1):
            path = c["file"]
            src = io.open(backups[path], encoding="utf-8", newline="").read()
            if src.count(c["old"]) != 1:
                print("[%d] ⚠️ 跳过：锚点在源文件里出现 %d 次（应为 1）—— %s"
                      % (i, src.count(c["old"]), c["name"]))
                ok_all = False
                continue
            io.open(path, "w", encoding="utf-8", newline="").write(src.replace(c["old"], c["new"]))
            try:
                txt, rc = run_suite(c["suite"])
            finally:
                shutil.copy2(backups[path], path)

            # 「崩了」的识别：非零退出且连汇总行都没有 ⇒ 断言根本没跑到
            # （普通失败时套件自己会打 RESULT=FAIL 并正常退出码 1，两者要分开处理）
            crashed = (rc != 0) and ("RESULT=" not in txt)
            hit = [l.strip() for l in txt.splitlines() if "\u2717" in l and c["expect"] in l]
            if hit:
                verdict = "OK"
            elif crashed:
                verdict = "CRASH"
            else:
                verdict = "BAD"
            if verdict != "OK":
                ok_all = False
            print("[%d] %-5s %s" % (i, verdict, c["name"]))
            print("      补丁：%s" % c["file"].replace(MINI, "…miniprogram"))
            print("      套件：%s  →  rc=%s / RESULT=%s / 命中期望断言 %d 条"
                  % (c["suite"], rc, "FAIL" if "RESULT=FAIL" in txt else "OK", len(hit)))
            for h in hit[:2]:
                print("        " + h[:150])
            if verdict == "CRASH":
                print("      ⚠️ 坏副本让套件**崩在断言之前**（rc=%s、无汇总行）⇒ 崩溃证明不了断言非恒真。" % rc)
                print("      ⚠️ 改写坏副本：要让它「仍能跑到底、只是结果错」，而不是抛异常。")
                print("      ---- 套件原始输出（尾部 30 行）----")
                for l in txt.splitlines()[-30:]:
                    print("        " + l[:170])
            elif verdict == "BAD":
                print("      ⚠️ 坏副本跑完了，但没命中 `✗` 关键字 ⇒ 这条断言可能是恒真的，必须重写")
                print("      ---- 套件原始输出（尾部 30 行，便于区分「断言恒真」与「补丁没生效」）----")
                for l in txt.splitlines()[-30:]:
                    print("        " + l[:170])
        print()

        # 恢复校验 + 复跑
        print("-" * 92)
        print("恢复校验（逐字节）")
        for path, tmp in backups.items():
            same = io.open(path, "rb").read() == io.open(tmp, "rb").read()
            print("  %-46s %s" % (os.path.basename(path), "一致 ✅" if same else "**不一致** ❌"))
            if not same:
                ok_all = False
        print()
        print("恢复后复跑两套断言")
        for s in ("mp_ach_test.js", "mp_gacha_test.js"):
            txt, rc = run_suite(s)
            last = [l for l in txt.splitlines() if l.startswith("通过 ")]
            good = ("RESULT=OK" in txt) and rc == 0
            print("  %-20s %s" % (s, (last[-1] if last else "(无汇总)") + "  " +
                                  ("✅" if good else "❌")))
            if not good:
                ok_all = False
    finally:
        for path, tmp in backups.items():
            shutil.copy2(tmp, path)
            os.remove(tmp)

    print()
    print("=" * 92)
    print("负控结论：" + ("✅ 全部坏副本都被对应断言抓住" if ok_all else "❌ 有 case 没打中（见上）"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
