# -*- coding: utf-8 -*-
"""
negctl_cloud.py —— mp_smoke.js「云开发接线」两条断言的**专属负控**。

为什么需要：通用负控只能证明「必败断言会变 FAIL」，不能证明**新断言本身不是恒真**。
「globalData.env 像不像合法环境 ID / 有没有透传给 wx.cloud.init」这两条尤其容易写成
复述字面量的废话（`env === 'cloud1-xxx'` 只是把产品代码抄了一遍）—— 所以造两个坏副本单验：

  坏副本 ① env 留空        ⇒ 必须命中「不像合法的云环境 ID」（留空 = 落回「默认环境」）
  坏副本 ② 填了但没透传    ⇒ 必须命中「不一致 —— 填了却没透传出去」

⚠️ 两个坏副本都写成「**能跑到底、只是结果错**」的形态：
   真机/内核里都存在的表达式，改完仍可执行、不抛错 ⇒ 失败必然来自断言，而不是崩溃。
   （反面教材：让坏副本去调一个 mp_build 之后已不存在的函数 ⇒ ReferenceError 崩在断言前，
     一条 ✗ 都没有，什么也证明不了 —— 判据要退化成 CRASH 才看得出。）

⚠️ 与老一代负控的差异：**本脚本带非零退出码**（2026-09-23 审计结论：
   凡没有退出码的脚本，驱动器只看打印的 RESULT ⇒ 永远不可能红）。
   判据是三态：非零退出 + 有汇总行 = 真打中；非零退出 + 无汇总行 = CRASH；跑完没 ✗ = BAD。

用法：python promo/negctl_cloud.py
"""
import io
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = r"E:\WeChatProjects\jianpan\miniprogram\app.js"
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
SMOKE = os.path.join(HERE, "mp_smoke.js")
BAK = TARGET + ".negctl_cloud.bak"
OUTTXT = os.path.join(HERE, "_negctl_cloud_out.txt")

ROOT = os.path.normpath(os.path.join(HERE, ".."))
out = []


def log(s):
    out.append(s)


def run_smoke():
    """跑冒烟，返回 (全文, ✗ 明细行, 是否有汇总行, 退出码)。
    ⚠️ 退出码必须一起返回：只判 'RESULT=' 在不在，会把进程崩溃误判成「坏副本没打中判据」。"""
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(NODE) + ";" + env.get("PATH", "")
    p = subprocess.run([NODE, SMOKE], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    txt = (p.stdout or "") + "\n" + (p.stderr or "")
    # ⚠️ mp_smoke.js 的失败标记**不是** ✗（✗ 是 mp_*_test.js 那批断言套件的记号）：
    #    它走 step() 的 try/catch ⇒ 打 `[FAIL] 名称`，并在末尾汇总块里打
    #    `  · [标签 名称] 异常原文`。照抄 ✗ 的后果是**假阴性**：
    #    两个坏副本明明都把退出码打成 1，第一版却被报成 BAD（「断言可能恒真」）——
    #    差点让我去重写没问题的断言。⭐ 换测试对象时先确认它的失败记号长什么样。
    fails = [l.strip() for l in txt.split("\n")
             if "[FAIL]" in l or "处抛错" in l or l.strip().startswith("· [")]
    return txt, fails, ("RESULT=" in txt), p.returncode


def judge(tag, txt, fails, has_result, rc, keywords):
    """三态判定：CRASH / BAD / OK。
    ⚠️ 关键字只允许取自**异常原文**，⛔ 不能取断言名里出现过的词 ——
       断言名（如「...globalData.env 的环境 ID...」）无论通过与否都会被打印，
       拿它当关键字 = 恒真匹配，负控自欺。所以本脚本的关键字全部是判据句里的独有短语。"""
    if rc != 0 and not has_result:
        log("  ❌ %s → CRASH：非零退出但**没有汇总行** ⇒ 坏副本崩在断言之前，什么也没证明" % tag)
        return False
    if rc == 0:
        log("  ❌ %s → 坏副本没被抓住（退出码 0）⇒ 断言可能是恒真的" % tag)
        return False
    if "RESULT=FAIL" not in txt:
        log("  ❌ %s → 退出码 %s 但没有 RESULT=FAIL 汇总行，本脚本读不懂这个失败形态" % (tag, rc))
        return False
    hit = [l for l in fails if any(k in l for k in keywords)]
    if not hit:
        log("  ❌ %s → BAD：跑完了但没有一条失败明细含关键字 %s" % (tag, keywords))
        log("     实际明细：" + ("; ".join(fails[:6]) if fails else "(无)"))
        return False
    log("  ✅ %s → OK（退出码 %s，命中 %d 条）" % (tag, rc, len(hit)))
    for l in hit[:3]:
        log("       " + l[:180])
    return True


def write_src(text):
    io.open(TARGET, "w", encoding="utf-8", newline="").write(text)


def read_src():
    return io.open(TARGET, encoding="utf-8", newline="").read()


if not os.path.isfile(TARGET):
    log("找不到 %s" % TARGET)
    print("\n".join(out))
    sys.exit(1)

shutil.copy2(TARGET, BAK)
verdicts = []
try:
    src = read_src()
    if "\r" in src:
        raise SystemExit("app.js 行尾不是 LF（本项目铁律），先修行尾再跑本脚本")

    # ---------- 基线：改之前必须本来是 OK ----------
    txt, fails, has_result, rc = run_smoke()
    base_ok = (rc == 0) and has_result
    log("基线（未改动）：退出码 %s / 汇总行 %s / FAIL 行数 %d"
        % (rc, "有" if has_result else "无", len(fails)))
    if not base_ok:
        log("⚠️ 基线就不是绿的 —— 先修好 mp_smoke.js 再谈负控（负控只能在「本来绿」的前提下证明东西）")
        for l in fails[:8]:
            log("    " + l)
    verdicts.append(base_ok)

    # ---------- 坏副本 ①：env 留空 ----------
    # 用正则而不是写死环境 ID：写死的话 Mak 以后换环境，这个负控自己就先烂了。
    # ⚠️ 唯一性必须先验：锚点不唯一 ⇒ 可能改错地方 ⇒ 负控静默失去意义。
    pat1 = re.compile(r"(\benv:\s*)'[^']*'")
    n1 = len(pat1.findall(src))
    if n1 != 1:
        log("样本①锚点不唯一（命中 %d 次），跳过并报错" % n1)
        verdicts.append(False)
    else:
        bad1 = pat1.sub(lambda m: m.group(1) + "''", src, count=1)
        assert bad1 != src, "样本①注入失败"
        write_src(bad1)
        txt, fails, has_result, rc = run_smoke()
        verdicts.append(judge("坏副本① env 留空", txt, fails, has_result, rc,
                             ["不像合法的云环境 ID"]))
        write_src(src)   # 逐副本还原，避免副本互相污染

    # ---------- 坏副本 ②：填了但没透传给 wx.cloud.init ----------
    old2 = "wx.cloud.init({ env: g.env || undefined, traceUser: true });"
    if src.count(old2) != 1:
        log("样本②锚点不唯一（命中 %d 次），跳过并报错" % src.count(old2))
        verdicts.append(False)
    else:
        bad2 = src.replace(old2, "wx.cloud.init({ traceUser: true });", 1)
        assert bad2 != src, "样本②注入失败"
        write_src(bad2)
        txt, fails, has_result, rc = run_smoke()
        verdicts.append(judge("坏副本② 填了却没透传", txt, fails, has_result, rc,
                             ["没透传"]))
        write_src(src)
finally:
    # 还原 + **逐字节**校验（老的负控把 same 算在 remove 之后 ⇒ 恒为 True，等于没校验）
    shutil.copy2(BAK, TARGET)
    restored = io.open(TARGET, "rb").read()
    ok_bytes = restored == io.open(BAK, "rb").read()
    os.remove(BAK)
    log("")
    log("已还原 %s（%.1f KB，逐字节一致：%s）"
        % (TARGET, len(restored) / 1024.0, "✅" if ok_bytes else "❌ 不一致！"))
    if not ok_bytes:
        verdicts.append(False)

# 还原后复跑：必须回到绿，否则「负控跑完留下的痕迹」本身就成了污染
txt, fails, has_result, rc = run_smoke()
back_ok = (rc == 0) and has_result and not fails
log("还原后复跑：退出码 %s / 汇总行 %s / FAIL 行数 %d" % (rc, "有" if has_result else "无", len(fails)))
verdicts.append(back_ok)

log("")
log("负控结论：" + ("✅ 全部坏副本都被对应断言抓住，且还原后回到绿" if all(verdicts)
                else "❌ 有 %d 项未通过" % verdicts.count(False)))

io.open(OUTTXT, "w", encoding="utf-8", newline="").write("\n".join(out) + "\n")
print("\n".join(out))
sys.exit(0 if all(verdicts) else 1)
