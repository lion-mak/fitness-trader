import re, os, urllib.request
d = r'E:\WorkBuddy\jianpan-ghpages'
ver = open(os.path.join(d, 'ver.txt'), encoding='utf-8').read().strip()
h = open(os.path.join(d, 'index.html'), encoding='utf-8').read()
s = open(os.path.join(d, 'sw.js'), encoding='utf-8').read()
meta = re.search(r'app-version"\s+content="([^"]+)"', h).group(1)
cache = re.search(r"CACHE_VERSION\s*=\s*'([^']+)'", s).group(1)
print('ver.txt      :', ver)
print('index meta   :', meta)
print('sw.js CACHE  :', cache)
print('index.html KB:', round(len(h.encode('utf-8')) / 1024, 1))
checks = {
  '底图 src': 'trading-floor-full.png' in h,
  '底图无 -empty': 'trading-floor-empty.png' not in h,
  '无 tf-ticker HTML': '.tf-ticker' not in h,
  '无 .tf-ticker CSS': '.tf-ticker' not in s,
  '无 @keyframes tf-scroll': 'tf-scroll' not in s,
  '有 tfDrawBigScreen': 'function tfDrawBigScreen' in h,
  '有 tfDrawSteam': 'function tfDrawSteam' in h,
  '有 tfDrawCheerPulse': 'function tfDrawCheerPulse' in h,
  '无 tfDrawTrader': 'tfDrawTrader' not in h,
  '无 TF.traders': "TF.traders" not in h and "traders:" not in h.split('const TF')[1].split('};')[0],
  'window.TF 暴露': 'window.TF = TF' in h,
  'aspect-ratio 3/2': 'aspect-ratio:3/2' in h,
}
for k, v in checks.items():
    print(('OK  ' if v else 'FAIL'), k)

# 资产
ap = os.path.join(d, 'assets', 'trading-floor-full.png')
print('asset full   :', os.path.exists(ap), os.path.getsize(ap), 'bytes')

# 线上核验
print('--- LIVE ---')
for url, pat in [
    ('https://lion-mak.github.io/fitness-trader/ver.txt', r'(.+)'),
    ('https://lion-mak.github.io/fitness-trader/index.html', r'app-version"\s+content="([^"]+)"'),
    ('https://lion-mak.github.io/fitness-trader/sw.js', r"CACHE_VERSION\s*=\s*'([^']+)'"),
]:
    try:
        t = urllib.request.urlopen(url, timeout=30).read().decode('utf-8', 'ignore')
        m = re.search(pat, t)
        print(url.split('/')[-1], '->', m.group(1).strip() if m else 'NO MATCH')
    except Exception as e:
        print(url.split('/')[-1], 'ERR', e)