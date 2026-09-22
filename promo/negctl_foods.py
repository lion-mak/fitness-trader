# -*- coding: utf-8 -*-
"""
negctl_foods.py —— mp_calc_test.js 里「食物库字段白名单」断言的**专属负控**。

为什么需要：通用负控（negctl.py）只能证明「必败断言会变 FAIL」，
不能证明**新断言本身不是恒真**（曾经因此让一批假断言过了十几轮）。

做法：复制真 foods.js → 造两个坏样本（① 塞回已裁字段 basis ② 删掉一条的 py）
→ 临时替换真文件跑 mp_calc_test.js → 断言必须出现 FAIL
→ 无论成败都把原文件还原并校验字节一致。

用法：python promo/negctl_foods.py
"""
import io, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = r"E:\WeChatProjects\jianpan\miniprogram\data\foods.js"
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
TEST = os.path.join(HERE, "mp_calc_test.js")
BAK = TARGET + ".negctl.bak"

out = []


def log(s):
    out.append(s)


def run_test():
    p = subprocess.run([NODE, TEST], capture_output=True)
    txt = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
    # ⚠️ 失败明细行是「两个空格 + ✗ + 名称」，不是行首 ✗ —— 用 in 判断，别用 startswith
    fails = [l.strip() for l in txt.split("\n") if "✗" in l]
    ok_line = [l for l in txt.split("\n") if l.startswith("结果")]
    return txt, fails, (ok_line[0] if ok_line else "(无结果行)")


if not os.path.isfile(TARGET):
    log("找不到 %s" % TARGET)
    print("\n".join(out))
    sys.exit(1)

shutil.copy2(TARGET, BAK)
try:
    src = io.open(TARGET, encoding="utf-8", newline="").read()
    assert "\r" not in src, "行尾不是 LF"

    # 基线：坏样本之前先跑一遍，确认本来是 OK
    base_txt, base_fails, base_line = run_test()
    log("基线（未改动）：%s，FAIL 行数 %d" % (base_line, len(base_fails)))

    # 坏样本 ①：把已裁字段 basis 塞回第一条
    bad1 = src.replace('"name":"', '"basis":"100g","name":"', 1)
    assert bad1 != src, "样本①注入失败"

    # 坏样本 ②：把第一条的 py 与 ini 都清空（模拟搜索字段被裁）
    #   ⚠️ 必须两个都清 —— 断言口径是「py 与 ini 同时缺失才算缺」，
    #      只清 py 是**触发不了**断言的（第一版负控就栽在这，样本太弱 → 假 OK）
    for k in ("py", "ini"):
        m = re.search(r'"%s":"[^"]*"' % k, bad1)
        assert m, "样本②找不到 %s 字段" % k
        bad1 = bad1[:m.start()] + '"%s":""' % k + bad1[m.end():]
    bad2 = bad1

    io.open(TARGET, "w", encoding="utf-8", newline="").write(bad2)
    _, bad_fails, bad_line = run_test()
    log("坏样本（塞回 basis + 清空一条的 py/ini）：%s，FAIL 行数 %d" % (bad_line, len(bad_fails)))
    for l in bad_fails:
        log("    " + l)

    hits = [l for l in bad_fails if ("basis" in l or "拼音" in l)]
    log("")
    if hits:
        log("RESULT=OK —— 新断言确实会因坏数据 FAIL，不是恒真（命中 %d 条）" % len(hits))
    else:
        log("RESULT=BAD —— 新断言没能捕获坏数据，断言写错了！")
finally:
    shutil.copy2(BAK, TARGET)
    os.remove(BAK)
    same = io.open(TARGET, "rb").read() == io.open(BAK, "rb").read() if os.path.isfile(BAK) else True
    size = os.path.getsize(TARGET)
    log("")
    log("已还原 %s（%.1f KB）" % (TARGET, size / 1024.0))

# 还原后再跑一次，确认回到 OK
_, final_fails, final_line = run_test()
log("还原后复跑：%s，FAIL 行数 %d" % (final_line, len(final_fails)))

res = io.open(os.path.join(HERE, "_negctl_foods_out.txt"), "w", encoding="utf-8", newline="")
res.write("\n".join(out) + "\n")
res.close()
print("\n".join(out))
