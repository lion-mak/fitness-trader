# -*- coding: utf-8 -*-
"""
mp_ws.py —— 小程序自动化端口（9420）的共享前置条件。

背景（技能已定论，2026-09-22 再次实证）：
  1. **9420 会在每次自动化会话结束后被 IDE 关掉**（客户端一断，端口也断）
     ⇒ 每个需要用 automator 的脚本（⑥b 像素差分 / ⑥c rect 对拍 / 探针）
        之前都必须先探端口、必要时重新 arm。
  2. 刚 `auto` 完**不能立刻连**：IDE 还在编译，此时 `currentPage()` / `switchTab()`
     会报 `Cannot destructure property 'rawPath' of 't.getPageMetaByWebviewId(...)' as it is null`，
     或更笼统的 `timeout waiting for automator response`。
     ⚠️ 这个报错**分两种成因**，别一律当成「等一下就好」：
       · 等一会儿就好  —— 编译中（本模块的就绪轮询能自愈）
       · 得重启 IDE    —— 会话里压根没注册页面（实测：connect/reLaunch 通，
                         但 currentPage/switchTab/evaluate/pageData 全挂）
                         修法 = 跑 promo/_fix_step2_restart_ide.py
     判别靠 promo/_mp_step.js 的分段结论，不要靠猜。

所以本模块提供的是「arm + 就绪轮询」，把盲等 18s 换成精确等待：
  ensure_port() → 端口没起就 cli auto，然后轮询 _mp_ready.js 直到 currentPage 真能取到。
"""
import os
import socket
import subprocess
import sys
import time

PORT = 9420
CLI = r"D:\微信web开发者工具\cli.bat"
PROJ = r"E:\WeChatProjects\jianpan"
HERE = os.path.dirname(os.path.abspath(__file__))
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NM = r"C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules"


def log(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def port_open(port=PORT, t=1.5):
    s = socket.socket()
    s.settimeout(t)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:                                        # noqa: BLE001
        return False
    finally:
        s.close()


def _node(script, args=None, timeout=90):
    env = dict(os.environ)
    env["NODE_PATH"] = NM
    env["PATH"] = os.path.dirname(NODE) + ";" + env.get("PATH", "")
    return subprocess.run([NODE, os.path.join(HERE, script)] + (args or []),
                          cwd=os.path.dirname(HERE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=timeout)


def ready_once(port=PORT):
    """连一次并试 currentPage()——这是判断「会话真的可用」的唯一可靠信号。"""
    if not port_open(port):
        return False, "端口未监听"
    env_ws = "ws://127.0.0.1:%d" % port
    try:
        r = subprocess.run(
            [NODE, os.path.join(HERE, "_mp_ready.js")],
            cwd=os.path.dirname(HERE), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
            env={**os.environ, "NODE_PATH": NM,
                 "PATH": os.path.dirname(NODE) + ";" + os.environ.get("PATH", ""),
                 "MP_WS": env_ws})
    except subprocess.TimeoutExpired:
        return False, "就绪探测超时"
    for l in (r.stdout or "").splitlines():
        if l.startswith("READY=1"):
            return True, l[6:].strip()
        if l.startswith("READY=0"):
            return False, l[6:].strip()[:120]
    return False, "就绪探测无输出"


def ensure_port(port=PORT, wait=60, quiet=False):
    """确保端口已 arm 且会话就绪。返回 True/False。"""
    def say(m):
        if not quiet:
            log(m)

    if port_open(port):
        okr, why = ready_once(port)
        if okr:
            say("[ws] %d 已就绪（%s）" % (port, why))
            return True
        say("[ws] %d 在监听但会话未就绪（%s）⇒ 重新 arm" % (port, why))
    if not os.path.exists(CLI):
        say("[ws] 找不到 CLI：" + CLI)
        return False
    say("[ws] arm 端口：cli auto --project %s --auto-port %d" % (PROJ, port))
    subprocess.run(["cmd", "/c", CLI, "auto", "--project", PROJ, "--auto-port", str(port)],
                   cwd=os.path.dirname(CLI), capture_output=True)
    t0 = time.time()
    last = ""
    while time.time() - t0 < wait:
        time.sleep(4)
        okr, why = ready_once(port)
        last = why
        if okr:
            say("[ws] √ 就绪（%.0fs）：%s" % (time.time() - t0, why))
            return True
    say("[ws] ✗ %.0fs 内未就绪：%s" % (wait, last))
    say("[ws] 若报 rawPath null 且 connect/reLaunch 通、currentPage 挂 ⇒ 跑 promo/_fix_step2_restart_ide.py")
    return False


if __name__ == "__main__":
    sys.exit(0 if ensure_port() else 1)
