# -*- coding: utf-8 -*-
"""准备「一次就能导成功」的存档：把 PWA 真实存档转成合法格式，写到桌面 + 放进系统剪贴板。

为什么需要：`promo/mock.json` 是我从 PWA 导出的取证样本，顶层是 `{state, summary}` ——
**没有 `__app`/`__schema`**，所以它**不能**直接导入（会被 migrate.parse 以
「没有任何已知字段」正确拦下）。这里补齐元信息，产出真正可导的两份东西：

  · 桌面上的 .json 文件  → 走「从聊天文件导入」（开发者工具会弹本地文件选择框）
  · 系统剪贴板里的文本    → 走「从剪贴板导入」（一步到位）

⚠️ 剪贴板是**全局共享**的：任何复制操作都会覆盖它。被覆盖了重跑本脚本即可。
"""
import ctypes
import io
import json
import os
import sys
import time

SRC = r"E:\WorkBuddy\jianpan-ghpages\promo\mock.json"
DESKTOP = r"C:\Users\Administrator\Desktop"
APP_TAG = "fitness-trader"
SCHEMA = 1

# ---------- 1. 读样本并补齐元信息 ----------
j = json.loads(io.open(SRC, encoding="utf-8").read())
state = j.get("state")
if not isinstance(state, dict):
    print("⛔ 样本里没有 state"); sys.exit(2)

payload = {
    "__app": APP_TAG,
    "__schema": SCHEMA,
    "__exportedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
    "__appVersion": "2.7.56",
    "state": state,
}
text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
nbytes = len(text.encode("utf-8"))

stamp = (state.get("lastDate") or time.strftime("%Y-%m-%d"))
days = len({r.get("date") for k in ("diet", "exercise", "weightLog")
            for r in (state.get(k) or []) if r.get("date")})

print("=" * 76)
print("源：%s" % SRC)
print("  真实记录：%d 天 / 饮食 %d 笔 / 运动 %d 笔 / 体重 %d 条"
      % (days, len(state.get("diet") or []), len(state.get("exercise") or []),
         len(state.get("weightLog") or [])))
print("  健康币 %s / 经验 %s" % (state.get("coins"), state.get("exp")))
print()

# ---------- 2. 写桌面文件 ----------
os.makedirs(DESKTOP, exist_ok=True)
name = u"健身交易员-存档-%s.json" % stamp.replace("-", "")
dest = os.path.join(DESKTOP, name)
io.open(dest, "w", encoding="utf-8", newline="").write(
    json.dumps(payload, ensure_ascii=False, indent=1))
print("=" * 76)
print("① 桌面文件已写好（走「从聊天文件导入」）")
print("   %s" % dest)
print("   %d 字节（写入后 %d 字节）" % (nbytes, os.path.getsize(dest)))

# ---------- 3. 放进系统剪贴板（ctypes，避开 shell 编码问题） ----------
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
u = ctypes.windll.user32
k = ctypes.windll.kernel32
k.GlobalAlloc.restype = ctypes.c_void_p
k.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
k.GlobalLock.restype = ctypes.c_void_p
k.GlobalLock.argtypes = [ctypes.c_void_p]
k.GlobalUnlock.argtypes = [ctypes.c_void_p]
u.SetClipboardData.restype = ctypes.c_void_p
u.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
u.GetClipboardData.restype = ctypes.c_void_p
u.GetClipboardData.argtypes = [ctypes.c_uint]

if not u.OpenClipboard(None):
    print("\n⛔ 打不开剪贴板（可能被别的程序占用），跳过剪贴板那一步。")
    sys.exit(3)
try:
    u.EmptyClipboard()
    buf = text.encode("utf-16-le") + b"\x00\x00"
    h = k.GlobalAlloc(GMEM_MOVEABLE, len(buf))
    p = k.GlobalLock(h)
    ctypes.memmove(p, buf, len(buf))
    k.GlobalUnlock(h)
    if not u.SetClipboardData(CF_UNICODETEXT, h):
        print("\n⛔ SetClipboardData 失败")
        sys.exit(4)
    # 立刻读回自校验（写入不报错 ≠ 真的写对了）
    u.CloseClipboard()
    u.OpenClipboard(None)
    got = u.GetClipboardData(CF_UNICODETEXT)
    back = ctypes.wstring_at(got) if got else ""
    ok = (back == text)
    print()
    print("=" * 76)
    print("② 系统剪贴板已就绪（走「从剪贴板导入」）")
    print("   写回读校验：%s" % ("✅ 与源文本逐字符一致" if ok else "❌ 不一致！"))
    print("   长度 %d 字符 / %d 字节（源 %d 字符）" % (len(back), nbytes, len(text)))
    print("   开头：%s" % back[:72])
finally:
    u.CloseClipboard()

print()
print("=" * 76)
print("现在打开小程序 →「我的」→「数据迁移」，二选一：")
print("  A. 点「从剪贴板导入」  ← 剪贴板已备好，最短路径")
print("  B. 点「从聊天文件导入」→ 选桌面上的 %s" % name)
print()
print("⚠️ 剪贴板是全局的，中途复制任何东西都会覆盖它 —— 被覆盖就重跑本脚本。")
