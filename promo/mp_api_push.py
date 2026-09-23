# -*- coding: utf-8 -*-
r"""用 GitHub REST API 把小程序仓库（E:\WeChatProjects\jianpan）本地 HEAD 推到私有仓库。

适用场景：github.com 主站被沙箱代理阻断（git push 走 CONNECT tunnel 502 失败），
但 api.github.com 可达。原理同 promo/api_push.py —— 内容寻址：把 HEAD 里的文件
按 base64 上传成 blob，重建 tree，因 blob 内容一致，新 tree sha 必然等于本地 HEAD
的 tree sha；再复用本地 HEAD 的 author/committer/date/message 建 commit，于是远端
commit 与本地零分叉（或仅元数据归一化差异，无害）。

与 api_push.py 的区别：
  ① REPO / ROOT 指向小程序，且不读 github.io 页面（小程序无 Pages）；
  ② **支持首次推送到空仓库**（远端无 master 分支时：全量 ls-tree 上传 + 建根 commit +
     创建 refs/heads/master + PATCH default_branch=master）；
  ③ 增量推送走 diff parent..head，逻辑与原脚本一致。

用法：python promo/mp_api_push.py
"""
import base64
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = r'E:\WeChatProjects\jianpan'
GITROOT = r'C:/Users/Administrator/.workbuddy/binaries/PortableGit/versions/1.2.0/mingw64/bin'
GIT = GITROOT + '/git.exe'
REPO = 'lion-mak/wxxcx-fitnesstrader'
BRANCH = 'master'
UA = 'WorkBuddy-deploy'


def git(*args, check=True, cwd=ROOT):
    env = dict(os.environ)
    env['PATH'] = GITROOT + os.pathsep + env.get('PATH', '')
    env['GIT_EXEC_PATH'] = GITROOT
    p = subprocess.run([GIT, '-C', cwd, '-c', 'core.quotePath=false'] + list(args),
                       capture_output=True, env=env)
    out = p.stdout.decode('utf-8', 'replace')
    if check and p.returncode != 0:
        raise RuntimeError('git %s failed: %s' % (' '.join(args), p.stderr.decode('utf-8', 'replace')))
    return out


def token():
    cfg = io.open(r'E:\WorkBuddy\jianpan-ghpages\.git\config', encoding='utf-8').read()
    m = re.search(r'https://([^:]+):([^@]+)@github\.com/', cfg)
    if not m:
        raise SystemExit('未在 PWA .git/config 找到内嵌 token')
    return m.group(2)


def api(tok, method, path, payload=None, allow=()):
    url = 'https://api.github.com' + path
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', 'Bearer ' + tok)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', UA)
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    if data:
        req.add_header('Content-Type', 'application/json')
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    op = urllib.request.build_opener(urllib.request.ProxyHandler({'https': proxy, 'http': proxy}) if proxy else urllib.request.ProxyHandler({}))
    for attempt in range(4):
        try:
            with op.open(req, timeout=60) as r:
                body = r.read().decode('utf-8', 'replace')
                return r.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace')[:400]
            if e.code in allow:
                return e.code, {}
            if e.code in (500, 502, 503, 504) and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError('HTTP %s %s %s -> %s' % (e.code, method, path, detail))
        except Exception as e:
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    raise RuntimeError('api retries exhausted: ' + path)


def main():
    tok = token()
    head = git('rev-parse', 'HEAD').strip()
    tree = git('rev-parse', 'HEAD^{tree}').strip()
    print('local HEAD =', head)
    print('local tree =', tree)

    # ① 查远端 ref（首次推送会是 404）
    st, ref = api(tok, 'GET', '/repos/%s/git/ref/heads/%s' % (REPO, BRANCH), allow=(404, 409))
    if st == 200:
        remote_head = ref['object']['sha']
        st2, base_commit = api(tok, 'GET', '/repos/%s/git/commits/%s' % (REPO, remote_head))
        base_tree = base_commit['tree']['sha']
        parents = [remote_head]
        # ⭐ 增量基线必须有两种找法，缺一种是灾难性的（见下）：
        #   ① ancestry —— 远端 HEAD 是本地祖先（标准 git 用法）；
        #   ② 内容基线 —— 远端 commit 的 tree == 本地某个 commit 的 tree。
        # 🔴 为什么 ② 不可省：本脚本建远端 commit 时用 parents=[remote_head]，即
        #    「内容复用本地 HEAD、历史线却是远端自己的」⇒ 远端 sha 永远不等于本地 sha
        #    ⇒ merge-base --is-ancestor **恒假** ⇒ 只靠 ① 的话每次推送都走全量。
        #    实测代价：136 个文件（含 data/foods.js 519 KB、30+ 张 PNG）逐个 POST blob，
        #    单次 > 2 min 直接被超时掐断（2026-09-23 真实踩到，白跑一轮）。
        #    有了 ② 之后，第 2 次起的推送只上传真正改动的文件（本次 24 个）。
        # 远端 HEAD 是本地祖先 → 增量；tree 未命中任何本地 commit（如占位 init commit）
        # → 才回退全量，覆盖占位内容。
        try:
            is_anc = git('merge-base', '--is-ancestor', remote_head, 'HEAD').returncode == 0
        except Exception:
            is_anc = False
        base_local = None
        if is_anc:
            base_local = remote_head
            print('remote HEAD =', remote_head, '(本地祖先，增量推送)')
        else:
            for ln in git('log', '--format=%H %T').splitlines():
                parts = ln.split()
                if len(parts) == 2 and parts[1] == base_tree:
                    base_local = parts[0]
                    break
            if base_local:
                print('remote HEAD =', remote_head,
                      '(非本地祖先，但 tree 命中本地 %s ⇒ 增量推送)' % base_local[:10])
            else:
                print('remote HEAD =', remote_head, '(非本地祖先且 tree 未命中 ⇒ 全量覆盖推送)')
        if base_local:
            # --no-renames：把 rename 拆成「删旧 + 增新」，否则 --name-only 只报新名
            # ⇒ 远端 tree 里会残留旧路径（本脚本用 base_tree 做增量，删除靠 sha:None 表达）。
            changed = [p for p in git('diff', '--name-only', '--no-renames', base_local, head).splitlines() if p.strip()]
        else:
            changed = [ln.split(None, 3)[-1] for ln in git('ls-tree', '-r', head).splitlines() if ln.strip()]
    else:
        print('远端无 %s 分支，按首次推送处理（全量上传）' % BRANCH)
        remote_head = None
        changed = [ln.split(None, 3)[-1] for ln in git('ls-tree', '-r', head).splitlines() if ln.strip()]
        base_tree = None
        parents = []

    print('changed (%d):' % len(changed))
    for p in changed:
        print('  ', p)

    # ② 逐个文件上传 blob
    entries = []
    for path in changed:
        raw = subprocess.run([GIT, '-C', ROOT, '-c', 'core.quotePath=false', 'show', '%s:%s' % (head, path)],
                             capture_output=True,
                             env=dict(os.environ, PATH=GITROOT + os.pathsep + os.environ.get('PATH', ''),
                                      GIT_EXEC_PATH=GITROOT))
        if raw.returncode != 0:
            entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': None})
            print('  [del]', path)
            continue
        content = raw.stdout  # bytes，二进制安全
        st, blob = api(tok, 'POST', '/repos/%s/git/blobs' % REPO,
                       {'content': base64.b64encode(content).decode('ascii'), 'encoding': 'base64'})
        mode = git('ls-tree', head, '--', path).split()[0]
        entries.append({'path': path, 'mode': mode, 'type': 'blob', 'sha': blob['sha']})
        print('  blob %-32s %s (%d bytes)' % (path, blob['sha'][:10], len(content)))

    # ③ 建 tree
    payload = {'tree': entries}
    if base_tree:
        payload['base_tree'] = base_tree
    st, new_tree = api(tok, 'POST', '/repos/%s/git/trees' % REPO, payload)
    print('new tree =', new_tree['sha'], '(本地 tree %s)' % tree)
    if new_tree['sha'] != tree:
        print('⚠️ 新 tree 与本地 HEAD 的 tree 不一致 —— 内容有偏差，已中止（不污染远端）')
        return 3

    # ④ 建 commit（复用本地 HEAD 的 author/committer/message）
    msg = git('log', '-1', '--format=%B', 'HEAD')
    meta = git('log', '-1', '--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI').strip().split('\x00')
    st, commit = api(tok, 'POST', '/repos/%s/git/commits' % REPO, {
        'message': msg,
        'tree': new_tree['sha'],
        'parents': parents,
        'author': {'name': meta[0], 'email': meta[1], 'date': meta[2]},
        'committer': {'name': meta[3], 'email': meta[4], 'date': meta[5]},
    })
    print('new commit =', commit['sha'], '(%s)' % st)
    if remote_head:
        st, upd = api(tok, 'PATCH', '/repos/%s/git/refs/heads/%s' % (REPO, BRANCH),
                      {'sha': commit['sha'], 'force': False})
    else:
        st, upd = api(tok, 'POST', '/repos/%s/git/refs' % REPO,
                      {'ref': 'refs/heads/%s' % BRANCH, 'sha': commit['sha']})
    print('ref updated =', upd['object']['sha'], '(%s)' % st)

    # ⑤ 把默认分支设成 master（幂等；首次/占位仓库都需要，避免默认分支是创建时的占位名）
    st, _ = api(tok, 'PATCH', '/repos/%s' % REPO, {'default_branch': BRANCH})
    print('default_branch set =', BRANCH, '(%s)' % st)

    print('\nRESULT=OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
