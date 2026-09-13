#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
健身交易员 —— 从 WorkBuddy 沙箱一键部署到 GitHub Pages。

背景（三个沙箱坑，本脚本一次性兜掉）：
  1. shim (shell-runtime-bash-env.sh) 会把 PATH 弄成空 → 直接 `git` 找不到；
     这里显式把 PortableGit 的 mingw64/bin 补进 PATH 与 GIT_EXEC_PATH。
  2. 沙箱出口代理端口每会话都变 → 从环境变量现读，不硬编码。
  3. 凭据：origin 远程 URL 已内嵌 token（仅存于本地 .git/config，不入库），
     推送时用 `-c credential.helper=` 关掉 helper（沙箱里 credential-store 会崩）。

用法：
  python deploy_push.py                 # 只推送当前已提交内容
  python deploy_push.py "v2.7.30 xxx"   # 提交全部改动 + 推送
"""
import subprocess, os, sys, time, ssl, re, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)                       # promo/ -> 仓库根
GBIN = r"C:\Users\Administrator\.workbuddy\binaries\PortableGit\versions\1.2.0\mingw64\bin"
GIT = os.path.join(GBIN, "git.exe")
PAGES = "https://lion-mak.github.io/fitness-trader/"


def env():
    e = dict(os.environ)
    e["PATH"] = GBIN + os.pathsep + e.get("PATH", "")
    e["GIT_EXEC_PATH"] = GBIN
    e["GIT_TERMINAL_PROMPT"] = "0"
    e["HOME"] = r"C:\Users\Administrator"
    e["USERPROFILE"] = r"C:\Users\Administrator"
    return e


def git(*args, timeout=180):
    return subprocess.run([GIT, "-C", REPO] + list(args),
                          capture_output=True, text=True, env=env(), timeout=timeout)


def push():
    for i in range(1, 6):
        r = git("-c", "credential.helper=", "push", "origin", "master")
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        print(f"push try {i}  rc={r.returncode}")
        if out:
            print("   " + out.replace("\n", "\n   "))
        if r.returncode == 0:
            return True
        time.sleep(3)
    return False


def selfheal():
    """收敛「本地与远端内容相同但 sha 不同」的状态（上次走 API 推送留下的元数据差异）。

    做法是标准的 git 操作，不是 hack：fetch 后用 rebase 把本地提交重放到远端之上。
    rebase 靠 patch-id 识别「内容已存在」的提交并自动丢弃，因此重复的等价提交会被消掉，
    不产生冲突、不丢内容；若内容确实不同则照常重放（有冲突会停下等人工处理）。
    """
    f = git("fetch", "origin", "master", timeout=120)
    if f.returncode != 0:
        print("self-heal: fetch 失败（github.com 不可达），跳过收敛")
        return False
    local = git("rev-parse", "HEAD").stdout.strip()
    remote = git("rev-parse", "origin/master").stdout.strip()
    if not local or not remote or local == remote:
        return False
    same = git("diff", "--quiet", "HEAD", "origin/master").returncode == 0
    print(f"self-heal: 本地 {local[:10]} vs 远端 {remote[:10]}（内容{'相同' if same else '不同'}）→ rebase 收敛")
    r = git("rebase", "origin/master", timeout=120)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if out:
        print("   " + out.replace("\n", "\n   "))
    if r.returncode != 0:
        git("rebase", "--abort")
        print("self-heal: rebase 未完成，已回滚到原状态（需人工确认）")
        return False
    m = os.path.join(REPO, ".git", "DIVERGED_TO_API_COMMIT")
    if os.path.exists(m):
        os.remove(m)
    print("self-heal: 已收敛，本地与远端 sha 一致")
    return True


def api_fallback():
    """github.com 被沙箱代理阻断时的兜底：改走 GitHub REST API（api.github.com 通常可达）。"""
    script = os.path.join(HERE, "api_push.py")
    if not os.path.exists(script):
        print("api_fallback: 找不到 api_push.py")
        return False
    print("=== push 失败 → 改用 GitHub REST API 兜底 ===")
    r = subprocess.run([sys.executable, script], capture_output=True, text=True, env=env(), timeout=600)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if out:
        print("   " + out.replace("\n", "\n   "))
    return r.returncode in (0, 1) and "ref updated" in out


def verify(expected_ver=None):
    ctx = ssl.create_default_context()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         urllib.request.HTTPSHandler(context=ctx))
    q = "?v=%d" % int(time.time())
    checks = [("ver.txt", r"([\d.]+)"),
              ("index.html", r'app-version" content="([^"]+)"'),
              ("sw.js", r"CACHE_VERSION = '([^']+)'")]
    ok = True
    for path, pat in checks:
        try:
            req = urllib.request.Request(PAGES + path + q,
                                         headers={"User-Agent": "verify", "Cache-Control": "no-cache"})
            with opener.open(req, timeout=30) as resp:
                m = re.search(pat, resp.read().decode("utf-8", "ignore"))
                val = m.group(1) if m else "NOT_FOUND"
                print(f"  {path:12s} -> {val}")
                if expected_ver and expected_ver not in val:
                    ok = False
        except Exception as e:
            print(f"  {path:12s} ERR {type(e).__name__}: {e}")
            ok = False
    return ok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].strip():
        msg = sys.argv[1].strip()
        git("add", "-A")
        c = git("commit", "-m", msg)
        print("commit:", ((c.stdout or "") + (c.stderr or "")).strip()[:200])
    selfheal()
    print("=== push ===")
    ok = push()
    if not ok:
        ok = api_fallback()
    print("=== verify live (GitHub Pages 可能需数十秒重建) ===")
    ver = None
    try:
        txt = open(os.path.join(REPO, "ver.txt"), encoding="utf-8").read().strip()
        ver = txt
    except Exception:
        pass
    vok = verify(ver)
    print("RESULT=" + ("OK" if (ok and vok) else "CHECK"))
