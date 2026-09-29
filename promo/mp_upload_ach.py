# -*- coding: utf-8 -*-
"""mp_upload_ach.py —— 成就像素画上传到云存储 → 回填 miniprogram/lib/ach_assets.js

三步，每步都有硬判据（照段位卡那条 A 路线的踩坑经验）：
  1. **对账**：小程序仓库 `assets_src/ach/*.png` 的文件名集合 === 云函数 uploadAchAssets 的 NAMES 集合。
  2. **部署**：开发者工具 CLI `cloud functions deploy`（simulator/控制台通道打不通，见函数头注释）。
  3. **上传**：模拟器里 wx.cloud.callFunction 触发（控制台 scf/Invoke 在本环境恒 ret=-3）；
     再拿返回的 fileID + 字节数与 `assets_src/ach` 对账，全对才回填 manifest。

🔴 素材源在**小程序仓库自己**（`E:\\WeChatProjects\\jianpan\\assets_src\\ach\\`）——
   ⛔ 不再读 PWA 仓库的 `index.html` / `assets/ach`，两个项目互不干涉；
   ⛔ 也不再让云函数出网拉 PWA 线上图（那条通路既耦合上线状态又会超时，见函数头注释）。
   `assets_src/` 在 `miniprogram/` 之外 ⇒ 不进主包、不占体积。
   ⚠️ 本脚本本身住在 PWA 仓库的 promo/（与 40+ 个 mp_*.py 同属一套公共工具链，
      只有取输入/落产出的路径改成小程序仓库）。

用法（必须关沙箱：要连腾讯云；且开发者工具需在运行）：
  <venv>/python.exe promo/mp_upload_ach.py            # 部署 + 上传 + 回填
  <venv>/python.exe promo/mp_upload_ach.py --no-deploy  # 只上传（函数已部署）

⚠️ 上传走**字节直传**：调用方把 png 的 base64 塞进云函数参数（promo/mp_upload_ach_bytes.js），
   云函数不出公网 ⇒ 默认一片 4 张（ACH_BATCH=4）+ 失败自动重试（ACH_TRIES=3）。
   ⛔ 别退回「云函数自己出网拉图」：那条路在默认 3 秒超时下单张都会随机超时。
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MINI = r'E:\WeChatProjects\jianpan'
CLI = r'D:\微信web开发者工具\cli.bat'
ENV_ID = 'cloud1-d1gkkvpez0d48660a'
FN = 'uploadAchAssets'
ART_DIR = os.path.join(MINI, 'assets_src', 'ach')      # 素材源＝小程序仓库自己那份
VENV_PY = r'C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe'


def sh(args, **kw):
    print('$ ' + ' '.join(args))
    return subprocess.run(args, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', **kw)


def read_icons():
    """素材 = 小程序仓库 `assets_src/ach/` 里的文件名（「哪些成就已有像素画」的真源）。
    ⛔ 别改回读 PWA 的 index.html ACH_ART —— 那会让小程序素材链依赖 PWA 的改动。"""
    if not os.path.isdir(ART_DIR):
        sys.exit('❌ 找不到素材目录：%s' % ART_DIR)
    names = []
    for f in sorted(os.listdir(ART_DIR)):
        if f.startswith('ach-') and f.endswith('.png'):
            names.append(f[4:-4])
    if not names:
        sys.exit('❌ %s 里没有 ach-*.png' % ART_DIR)
    return names


def read_fn_names():
    """从云函数的 NAMES 抽（⛔不手抄：两边必须由同一次读取比对）"""
    src = open(os.path.join(MINI, 'cloudfunctions', FN, 'index.js'), encoding='utf-8').read()
    m = re.search(r'const NAMES = \[(.*?)\];', src, re.S)
    if not m:
        sys.exit('❌ 云函数里找不到 NAMES')
    return re.findall(r"'([^']+)'", m.group(1))


def main():
    icons = read_icons()
    names = read_fn_names()
    print('assets_src/ach = %s' % icons)
    print('函数 NAMES     = %s' % names)
    # ⚠️ 判据是**集合相等**、不是逐字同序：上传走字节直传（按名字逐张发），不存在错位问题；
    #    NAMES 的顺序只在函数「通路 B（自己出网拉图）」里当切片下标用，那条路已不启用。
    if set(icons) != set(names):
        sys.exit('❌ 两边不一致 —— 只在素材里 %s / 只在 NAMES 里 %s'
                 % (sorted(set(icons) - set(names)), sorted(set(names) - set(icons))))
    print('✅ 对账通过：%d 项（集合相等）\n' % len(icons))

    # 本地素材（回填后用它核字节数）
    local = {}
    for n in icons:
        p = os.path.join(ART_DIR, 'ach-%s.png' % n)
        if not os.path.exists(p):
            sys.exit('❌ 本地缺图：%s' % p)
        local[n] = os.path.getsize(p)
    print('素材体积：%s\n' % ', '.join('%s %dB' % (k, v) for k, v in local.items()))

    if '--no-deploy' not in sys.argv:
        r = sh([CLI, 'cloud', 'functions', 'deploy', '--env', ENV_ID, '--names', FN,
                '--project', MINI, '--remote-npm-install'])
        out = (r.stdout or '') + (r.stderr or '')
        print(out.strip()[-1200:])
        # ⚠️ 判据必须用**完整输出**：CLI 的 stdout/stderr 会交错，且不同版本把结果打成
        #    JSON 或**表格行**（`│ uploadAchAssets │ true │ 2 │ '3.0 KB' │`）。
        #    只截尾再找 '"success": true' 会**假红** —— 实测部署明明成功（表格行 true +
        #    末尾 `√ deploy cloudfunctions`），脚本却 exit 1 直接跳过上传。
        flat = re.sub(r'\s+', ' ', out)
        ok_json = re.search(r'"success"\s*:\s*true', out) is not None
        ok_table = ('\u221a deploy cloudfunctions' in flat) and ('%s \u2502 true' % FN in flat)
        if not (ok_json or ok_table):
            sys.exit('❌ 云函数部署未报成功（exit=%d，json/表格两种判据都没命中）' % r.returncode)
        print('✅ 云函数已部署（判据：%s）\n' % ('json' if ok_json else 'table'))
    else:
        print('（跳过部署）\n')

    # ── 触发上传：**字节直接塞进调用参数**（云函数通路 A，不出公网） ──
    # ⚠️ 别改成「让云函数自己出网拉 PWA 线上图」（函数里的通路 B）：本环境那条路抖动极大，
    #    默认 3 秒超时下**单张也会随机超时**（实测 10 张、每片 1 张，仍有 4 张撞
    #    FUNCTIONS_TIME_LIMIT_EXCEEDED）。塞字节后云函数不出公网 ⇒ 只剩一次 uploadFile。
    step = int(os.environ.get('ACH_BATCH', '4'))   # 4 张 ≈ 80KB base64，一次调用绰绰有余
    tries = int(os.environ.get('ACH_TRIES', '3'))
    chunks = [(i, icons[i:i + step]) for i in range(0, len(icons), step)]
    got, why = {}, {}
    pending = list(range(len(chunks)))
    for attempt in range(1, tries + 1):
        if not pending:
            break
        if attempt > 1:
            print('── 第 %d 轮重试 %d 片 ──' % (attempt, len(pending)))
        rest = []
        for ci in pending:
            start, names = chunks[ci]
            r = sh([VENV_PY, os.path.join(HERE, '_mp_run.py'),
                    'mp_upload_ach_bytes.js', ','.join(names)],
                   env=dict(os.environ, ACH_DIR=ART_DIR))
            out = (r.stdout or '') + ('\n--- stderr ---\n' + r.stderr if r.stderr else '')
            m = re.search(r'FN_RESULT=(\{.*\})', out)
            if not m:
                for n in names:
                    why[n] = '没拿到 FN_RESULT：%s' % out.strip()[-300:]
                rest.append(ci)
                continue
            res = json.loads(m.group(1))
            if not res.get('ok'):
                for n in names:
                    why[n] = '调用失败：%s' % str(res.get('errMsg'))[:160]
                rest.append(ci)
                continue
            ret = res['result']
            print('   %-34s → ok=%s/%s' % (','.join(names), ret.get('ok'), ret.get('count')))
            for f in ret.get('files', []):
                n, size, fid = f.get('name'), f.get('size'), f.get('fileID')
                if f.get('error'):
                    why[n] = str(f['error'])[:160]
                    rest.append(ci)
                    continue
                if not fid or not str(fid).startswith('cloud://'):
                    why[n] = 'fileID 异常 %r' % (fid,)
                    rest.append(ci)
                    continue
                if size != local.get(n):
                    why[n] = '字节 %s ≠ 本地 %s' % (size, local.get(n))
                    rest.append(ci)
                    continue
                got[n] = fid
                why.pop(n, None)
        pending = sorted(set(rest))

    if len(got) != len(icons):
        miss = [n for n in icons if n not in got]
        sys.exit('❌ 校验失败（成功 %d/%d，重试 %d 轮仍缺）：\n  %s'
                 % (len(got), len(icons), tries,
                    '\n  '.join('%s: %s' % (n, why.get(n, '?')) for n in miss)))
    print('\n✅ %d 张 fileID 全部拿到，且字节数与本地 assets/ach 逐张一致' % len(got))

    # ── 回填 manifest（键序 = ACH_ART 序） ──
    path = os.path.join(MINI, 'miniprogram', 'lib', 'ach_assets.js')
    head = open(path, encoding='utf-8').read().split('module.exports')[0]
    body = 'module.exports = {\n' + '\n'.join(
        "  %s: '%s'," % (n, got[n]) for n in icons) + '\n};\n'
    open(path, 'w', encoding='utf-8', newline='\n').write(head + body)
    print('\n✅ 已回填 %s（%d 键）' % (path, len(got)))
    for n in icons:
        print('   %-10s %s' % (n, got[n]))
    print('\n下一步：跑 mp_ach_test + mp_wxss_check + mp_lint，再看模拟器/真机是否直渲云图')


main()
