# -*- coding: utf-8 -*-
r"""提交小程序仓库（E:\WeChatProjects\jianpan）的全部改动，并打印 HEAD。

为什么单独抽出来（原先每轮都临时写一个 _mp_git_commit.py 再删掉）：
  ① 本沙箱的 PATH 是坏的 ⇒ git 必须用绝对路径 + 手动补 GIT_EXEC_PATH
     （与 mp_api_push.py 同款；⛔ 不要用裸 `git`，也不要加管道/重定向）；
  ② git 的提交信息里有中文 ⇒ 走 `-F 临时文件`，避免命令行编码问题
     （临时文件用 UTF-8，提交后立即删除）；
  ③ 每完成一个「单元工作」都要 commit + push（用户口径：改完就发）⇒ 这是稳定复用的收尾动作。

用法：
    python promo/mp_commit.py "v2.7.61 复刻身体成分详情子页 + 录入弹层"
    python promo/mp_commit.py            # 只打印当前状态，不提交（干跑）

退出码：0=成功（含「没有改动」）；非 0=git 出错。
"""
import io
import os
import subprocess
import sys
import tempfile

ROOT = r'E:\WeChatProjects\jianpan'
GITROOT = r'C:/Users/Administrator/.workbuddy/binaries/PortableGit/versions/1.2.0/mingw64/bin'
GIT = GITROOT + '/git.exe'


def git(*args, check=True):
    env = dict(os.environ)
    env['PATH'] = GITROOT + os.pathsep + env.get('PATH', '')
    env['GIT_EXEC_PATH'] = GITROOT
    p = subprocess.run([GIT, '-C', ROOT, '-c', 'core.quotePath=false'] + list(args),
                       capture_output=True, env=env)
    out = p.stdout.decode('utf-8', 'replace')
    err = p.stderr.decode('utf-8', 'replace')
    if check and p.returncode != 0:
        raise RuntimeError('git %s failed:\n%s' % (' '.join(args), err))
    return out + (('\n[stderr] ' + err) if err.strip() else '')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    msg = (sys.argv[1] if len(sys.argv) > 1 else '').strip()

    print('=' * 74)
    print('工作树状态')
    print('=' * 74)
    status = git('status', '--porcelain')
    print(status.rstrip() or '(干净，无改动)')

    if not msg:
        print()
        print('（干跑：未给出提交信息 ⇒ 不提交）')
        return 0

    if not status.strip():
        print()
        print('没有改动 ⇒ 无需提交。HEAD: ' + git('rev-parse', 'HEAD').strip())
        return 0

    print()
    print('=' * 74)
    print('提交')
    print('=' * 74)
    git('add', '-A')
    fd, tmp = tempfile.mkstemp(suffix='.txt')
    os.close(fd)
    io.open(tmp, 'w', encoding='utf-8', newline='\n').write(msg + '\n')
    try:
        print(git('commit', '-F', tmp).rstrip())
    finally:
        os.remove(tmp)

    head = git('rev-parse', 'HEAD').strip()
    print()
    print('HEAD  = ' + head)
    print('提交数 = ' + git('rev-list', '--count', 'HEAD').strip())
    # 改动统计（便于回顾这一批到底动了多少）
    print('本批统计：')
    print(git('show', '--stat', '--oneline', 'HEAD').rstrip())
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeError as e:
        print('ERR ' + str(e))
        sys.exit(1)
