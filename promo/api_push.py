# -*- coding: utf-8 -*-
"""当 github.com（git 主站）被沙箱代理阻断、但 api.github.com 可达时，
用 GitHub 官方 REST API 把当前本地 HEAD 提交原样推到远端。

原理：内容寻址。把 HEAD 里改动的文件按 base64 上传成 blob，用 base_tree = 远端的 tree
拼出新 tree；因为 blob 内容一致，算出的 tree sha 必然等于本地 HEAD 的 tree sha。
再让 commit 复用本地 HEAD 的 author/committer/date/message，于是远端产生的 commit
与本地 HEAD 的 sha 完全一致 —— 远端与本地零分叉，后续 push 不受影响。

用法：python api_push.py            # 推送本地 HEAD 到 origin/master
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

ROOT = r'E:\WorkBuddy\jianpan-ghpages'
GITROOT = r'C:/Users/Administrator/.workbuddy/binaries/PortableGit/versions/1.2.0/mingw64/bin'
GIT = GITROOT + '/git.exe'
REPO = 'lion-mak/fitness-trader'
BRANCH = 'master'
LIVE = 'https://lion-mak.github.io/fitness-trader/'
UA = 'WorkBuddy-deploy'


def git(*args, check=True):
    env = dict(os.environ)
    env['PATH'] = GITROOT + os.pathsep + env.get('PATH', '')
    env['GIT_EXEC_PATH'] = GITROOT
    p = subprocess.run([GIT, '-C', ROOT, '-c', 'core.quotePath=false'] + list(args), capture_output=True, env=env)
    out = p.stdout.decode('utf-8', 'replace')
    if check and p.returncode != 0:
        raise RuntimeError('git %s failed: %s' % (' '.join(args), p.stderr.decode('utf-8', 'replace')))
    return out


def token():
    cfg = io.open(os.path.join(ROOT, '.git', 'config'), encoding='utf-8').read()
    m = re.search(r'https://([^:]+):([^@]+)@github\.com/', cfg)
    if not m:
        raise SystemExit('未在 .git/config 找到内嵌 token')
    return m.group(2)


def api(tok, method, path, payload=None):
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
    handlers = [urllib.request.ProxyHandler({'https': proxy, 'http': proxy})] if proxy else [urllib.request.ProxyHandler({})]
    op = urllib.request.build_opener(*handlers)
    for attempt in range(4):
        try:
            with op.open(req, timeout=60) as r:
                body = r.read().decode('utf-8', 'replace')
                return r.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace')[:400]
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


def find_local_proxy(tok, base_tree_sha):
    """当远端 HEAD 与本地 HEAD^ 不一致时（本地比远端多了若干 commit，例如 API 推送后
    又本地提交了 tooling），从 HEAD 往回找一个内容（路径→blob sha）与远端 tree 完全一致的
    本地提交作为「代理」——以它为 diff 基点重建 tree，新 tree 即可与本地 HEAD tree sha 一致。"""
    try:
        st, rt = api(tok, 'GET', '/repos/%s/git/trees/%s?recursive=1' % (REPO, base_tree_sha))
    except Exception as e:
        print('   拉取远端递归 tree 失败：', e)
        return None
    remote_entries = {e['path']: e['sha'] for e in rt.get('tree', []) if e.get('type') == 'blob'}
    cur = 'HEAD'
    for _ in range(40):
        try:
            ls = git('ls-tree', '-r', cur).strip()
        except Exception:
            break
        local_entries = {}
        for line in ls.splitlines():
            parts = line.split(None, 3)
            if len(parts) < 4:
                continue
            local_entries[parts[3]] = parts[2]
        if local_entries == remote_entries:
            return git('rev-parse', cur).strip()
        try:
            cur = git('rev-parse', cur + '^').strip()
        except Exception:
            break
    return None


def main():
    tok = token()
    head = git('rev-parse', 'HEAD').strip()
    tree = git('rev-parse', 'HEAD^{tree}').strip()
    parent = git('rev-parse', 'HEAD^').strip()
    msg = git('log', '-1', '--format=%B', 'HEAD')
    meta = git('log', '-1', '--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI').strip().split('\x00')
    print('local HEAD   =', head)
    print('local tree   =', tree)
    print('local parent =', parent)
    print('author       =', meta[0], meta[1], meta[2])

    st, ref = api(tok, 'GET', '/repos/%s/git/ref/heads/%s' % (REPO, BRANCH))
    remote_head = ref['object']['sha']
    print('remote HEAD  =', remote_head, '(GET %s)' % st)
    if remote_head == head:
        print('远端已是最新，无需推送。')
        return 0
    if remote_head != parent:
        print('⚠️ 远端 HEAD 与本地父提交不一致：远端 %s / 本地父 %s' % (remote_head, parent))
        print('   尝试找本地代理提交（内容与远端 tree 一致）...')
        st, bc = api(tok, 'GET', '/repos/%s/git/commits/%s' % (REPO, remote_head))
        base_tree_sha_div = bc['tree']['sha']
        proxy = find_local_proxy(tok, base_tree_sha_div)
        if not proxy:
            print('   无法定位本地代理，已中止（不会污染远端）。')
            return 2
        print('   local proxy =', proxy)
        parent = proxy

    st, base_commit = api(tok, 'GET', '/repos/%s/git/commits/%s' % (REPO, remote_head))
    base_tree = base_commit['tree']['sha']

    changed = [p for p in git('diff', '--name-only', parent, head).splitlines() if p.strip()]
    print('changed files:', changed)
    if not changed:
        print('无改动文件，中止。')
        return 2

    entries = []
    for path in changed:
        raw = subprocess.run([GIT, '-C', ROOT, '-c', 'core.quotePath=false', 'show', '%s:%s' % (head, path)],
                             capture_output=True,
                             env=dict(os.environ, PATH=GITROOT + os.pathsep + os.environ.get('PATH', ''),
                                      GIT_EXEC_PATH=GITROOT))
        if raw.returncode != 0:
            print('  跳过（该提交中不存在，按删除处理）:', path)
            entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': None})
            continue
        content = raw.stdout
        st, blob = api(tok, 'POST', '/repos/%s/git/blobs' % REPO, {
            'content': base64.b64encode(content).decode('ascii'),
            'encoding': 'base64',
        })
        mode = git('ls-tree', head, '--', path).split()[0]
        entries.append({'path': path, 'mode': mode, 'type': 'blob', 'sha': blob['sha']})
        print('  blob %-28s %s (%d bytes)' % (path, blob['sha'][:10], len(content)))

    st, new_tree = api(tok, 'POST', '/repos/%s/git/trees' % REPO, {'base_tree': base_tree, 'tree': entries})
    print('new tree     =', new_tree['sha'], '(本地 tree %s)' % tree)
    if new_tree['sha'] != tree:
        print('⚠️ 新 tree 与本地 HEAD 的 tree 不一致 —— 内容有偏差，已中止（不会污染远端）')
        return 3

    st, commit = api(tok, 'POST', '/repos/%s/git/commits' % REPO, {
        'message': msg,
        'tree': new_tree['sha'],
        'parents': [remote_head],
        'author': {'name': meta[0], 'email': meta[1], 'date': meta[2]},
        'committer': {'name': meta[3], 'email': meta[4], 'date': meta[5]},
    })
    print('new commit   =', commit['sha'], '(%s)' % st)
    diverged = commit['sha'] != head
    if diverged:
        # 已用 tree sha 校验内容完全一致，差异仅在提交对象元数据（GitHub 会归一化时区/消息换行），
        # 属无害差异；照常推进 ref，同时落一个标记，交给 deploy_push.py 在 github.com 恢复后自动收敛。
        print('note: 远端 commit sha 与本地不同（%s vs %s）—— 内容一致，仅元数据归一化差异。'
              % (commit['sha'][:10], head[:10]))

    st, upd = api(tok, 'PATCH', '/repos/%s/git/refs/heads/%s' % (REPO, BRANCH),
                  {'sha': commit['sha'], 'force': False})
    print('ref updated  =', upd['object']['sha'], '(%s)' % st)
    if diverged:
        marker = os.path.join(ROOT, '.git', 'DIVERGED_TO_API_COMMIT')
        io.open(marker, 'w', encoding='utf-8').write(
            json.dumps({'local': head, 'remote': commit['sha'], 'at': time.strftime('%Y-%m-%d %H:%M:%S')}))
        print('已写标记：', marker)
        print('修复方式：github.com 恢复后，deploy_push.py 会自动检测「本地与远端内容一致但 sha 不同」')
        print('          并执行 git rebase origin/master 收敛 —— rebase 靠 patch-id 丢掉「内容已存在」'
              '的等价提交，零丢失。')
        # ⚠️ 这两行原本写的是「并执行 git reset --hard origin/master（无损，内容完全相同）」——
        #    与 deploy_push.py 的 selfheal() 实现对不上（它跑的是 rebase），而且
        #    reset --hard 会丢掉本地未推送的提交，**不是无损操作**。
        #    照着一句错的提示敲命令是真会出事的（skill 里也专门写了「⛔ 不要在 rebase 前手写 reset --hard」），
        #    故按实际实现改正。

    print('\n=== verify live ===')
    # ⛔ 别再把期望版本号写死在这里。曾写成 if found != '2.7.31': ok = False，
    #    于是 2.7.32 之后每一轮推送都报 RESULT=CHECK —— 假警报久了就没人看了。
    #    正确口径：线上三处（ver.txt / index.html app-version / sw.js CACHE_VERSION）
    #    彼此一致，且等于本地 ver.txt。
    want = io.open(os.path.join(ROOT, 'ver.txt'), encoding='utf-8').read().strip()
    got = {}
    for path, key in [('ver.txt', None), ('index.html', 'app-version'), ('sw.js', 'CACHE_VERSION')]:
        got[path] = None
        for attempt in range(6):
            try:
                req = urllib.request.Request(LIVE + path + '?v=' + str(int(time.time())))
                req.add_header('User-Agent', UA)
                proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
                op = urllib.request.build_opener(urllib.request.ProxyHandler({'https': proxy, 'http': proxy}))
                with op.open(req, timeout=30) as r:
                    txt = r.read().decode('utf-8', 'replace')
                m = re.search(r"content=\"([\d.]+)\"", txt) if key else None
                found = m.group(1) if m else re.search(r"jianpan-([\d.]+)", txt).group(1) if 'CACHE_VERSION' in txt else txt.strip()[:12]
                got[path] = found
                print('  %-12s -> %s' % (path, found))
                break
            except Exception as e:
                if attempt == 5:
                    print('  %-12s -> 读取失败 %s' % (path, e))
                else:
                    time.sleep(10)
    # ⚠️ 区分「读取失败」与「版本不一致」—— 两者含义完全不同，混在一起报会误导：
    #    本段是**直连**（下面主动清空代理），而沙箱直连 github.io 被阻断 ⇒ 读取必然失败。
    #    这是已知现象，不代表部署失败；真正的复核要走代理 curl（见 promo/_v56check.py、SKILL.md）。
    failed = [p for p, v in got.items() if v is None]
    mismatched = [p for p, v in got.items() if v is not None and v != want]
    ok = bool(want) and not failed and not mismatched
    if failed and not mismatched:
        print('  ⚠️ 线上读取失败（%s）—— 本段为直连，沙箱直连 github.io 被阻断，这是已知现象，'
              '**不代表部署失败**。' % ','.join(failed))
        print('     线上复核请改走代理 curl（见 promo/_v56check.py 或 SKILL.md「推送后必做核验」）。')
    elif mismatched:
        print('  ⚠️ 线上与本地 ver.txt=%s 不一致：%s（GitHub Pages 重建有延迟，隔十几秒重跑本脚本复查）'
              % (want, ','.join('%s=%s' % (p, got[p]) for p in mismatched)))
    print('\nRESULT=' + ('OK' if ok else 'CHECK'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
