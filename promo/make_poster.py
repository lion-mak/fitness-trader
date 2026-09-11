# -*- coding: utf-8 -*-
"""合成 1920x1080 宣传海报（2 张）"""
import os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px;overflow:hidden;background:#0a0e1a}
body{font-family:"PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif;color:#fff;-webkit-font-smoothing:antialiased}
.poster{position:relative;width:1920px;height:1080px;overflow:hidden;background:#0a0e1a}
.glow{position:absolute;border-radius:50%;pointer-events:none}
.g1{width:900px;height:900px;left:-320px;top:-360px;background:radial-gradient(circle,rgba(255,59,71,.16),rgba(255,59,71,0) 68%)}
.g2{width:1000px;height:1000px;right:-380px;bottom:-460px;background:radial-gradient(circle,rgba(0,200,150,.14),rgba(0,200,150,0) 68%)}
.grid{position:absolute;inset:0;opacity:.5;background-image:linear-gradient(rgba(31,38,56,.55) 1px,transparent 1px),linear-gradient(90deg,rgba(31,38,56,.55) 1px,transparent 1px);background-size:64px 64px}
.phone{position:relative;border-radius:26px;border:1px solid #2a3348;overflow:hidden;background:#0a0e1a;box-shadow:0 24px 60px rgba(0,0,0,.6)}
.phone img{display:block;width:100%;height:auto}
.phone::after{content:"";position:absolute;inset:0;border-radius:26px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.05)}
/* ---- 海报 1 ---- */
.p1 .left{position:absolute;left:96px;top:118px;width:790px}
.tag{display:inline-block;font-size:15px;letter-spacing:.14em;color:#ffb800;border:1px solid rgba(255,184,0,.4);border-radius:999px;padding:7px 18px;margin-bottom:30px}
.p1 h1{font-size:76px;font-weight:600;letter-spacing:.02em;line-height:1.06}
.p1 h1 em{font-style:normal;color:#ff3b47}
.p1 .sub{margin-top:22px;font-size:27px;font-weight:400;color:#9aa8be;letter-spacing:.01em}
.p1 .sub b{color:#fff;font-weight:500}
.points{margin-top:52px;list-style:none}
.points li{display:flex;align-items:center;font-size:18px;color:#cdd6e4;margin-bottom:19px;letter-spacing:.01em}
.points .dot{width:9px;height:9px;border-radius:50%;margin-right:15px;flex:none}
.dot.red{background:#ff3b47;box-shadow:0 0 12px rgba(255,59,71,.75)}
.dot.green{background:#00c896;box-shadow:0 0 12px rgba(0,200,150,.75)}
.dot.amber{background:#ffb800;box-shadow:0 0 12px rgba(255,184,0,.75)}
.kpis{margin-top:60px;display:flex;gap:58px;padding-top:34px;border-top:1px solid #1f2638}
.kpis div{min-width:150px}
.kpis b{display:block;font-size:52px;font-weight:600;line-height:1;letter-spacing:-.01em}
.kpis b span{font-size:22px;font-weight:400;margin-left:5px;color:#9aa8be}
.kpis i{display:block;margin-top:12px;font-size:15px;font-style:normal;color:#5a6478;letter-spacing:.05em}
.kpis .r b{color:#ff3b47}.kpis .g b{color:#00c896}.kpis .a b{color:#ffb800}
.p1 .right{position:absolute;left:890px;top:198px;display:flex;gap:60px}
.p1 .right .phone{width:460px}
/* ---- 海报 2 ---- */
.p2 .hd{position:absolute;left:0;right:0;top:78px;text-align:center}
.p2 h2{font-size:44px;font-weight:600;letter-spacing:.01em}
.p2 h2 em{font-style:normal;color:#00c896}
.p2 .hd p{margin-top:16px;font-size:19px;color:#5a6478;letter-spacing:.06em}
.p2 .row{position:absolute;left:173px;top:180px;display:flex;gap:52px}
.p2 figure{width:490px}
.p2 .phone img{display:block}
.p2 figcaption{margin-top:20px;text-align:center;font-size:17px;color:#9aa8be;letter-spacing:.03em}
.p2 figcaption b{display:block;color:#fff;font-weight:500;font-size:19px;margin-bottom:6px}
"""

P1 = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>%s</style></head><body>
<div class="poster p1">
  <div class="grid"></div><div class="glow g1"></div><div class="glow g2"></div>
  <div class="left">
    <div class="tag">微信小程序 · 内测中</div>
    <h1>健身<em>交易员</em></h1>
    <div class="sub">把一个减肥计划，做成一座<b>属于你的交易所</b></div>
    <ul class="points">
      <li><span class="dot red"></span>每笔饮食 = 做多，热量实时打进体重 K 线</li>
      <li><span class="dot green"></span>每次运动 = 做空，消耗计入成交量与缺口</li>
      <li><span class="dot amber"></span>每日缺口达标 = 涨停，连板天数可攀比</li>
    </ul>
    <div class="kpis">
      <div class="g"><b>-6.3<span>kg</span></b><i>累计减重</i></div>
      <div class="r"><b>52<span>次</span></b><i>累计涨停</i></div>
      <div class="a"><b>15<span>天</span></b><i>最长连板</i></div>
    </div>
  </div>
  <div class="right">
    <div class="phone"><img src="card_market.png"></div>
    <div class="phone"><img src="card_trade.png"></div>
  </div>
</div></body></html>""" % CSS

P2 = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>%s</style></head><body>
<div class="poster p2">
  <div class="grid"></div><div class="glow g1"></div><div class="glow g2"></div>
  <div class="hd">
    <h2>数据看板 · <em>游戏化激励</em></h2>
    <p>持仓评级　·　龙虎榜　·　成就殿堂</p>
  </div>
  <div class="row">
    <figure><div class="phone"><img src="card_holdings.png"></div>
      <figcaption><b>持仓</b>每日缺口评级 · 净热量趋势</figcaption></figure>
    <figure><div class="phone"><img src="card_leaderboard.png"></div>
      <figcaption><b>龙虎榜</b>热菜榜 · 劳模榜 · 大胃王日</figcaption></figure>
    <figure><div class="phone"><img src="card_achievements.png"></div>
      <figcaption><b>成就殿堂</b>30 项成就 · 段位晋升</figcaption></figure>
  </div>
</div></body></html>""" % CSS

for name, html in (('poster1', P1), ('poster2', P2)):
    p = os.path.join(HERE, name + '.html')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(html)

for name, out in (('poster1', '01_封面主视觉.png'), ('poster2', '02_数据与游戏化.png')):
    src = 'file:///' + os.path.join(HERE, name + '.html').replace('\\', '/')
    dst = os.path.join(HERE, out)
    subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars',
                    '--no-sandbox', '--force-device-scale-factor=1',
                    '--user-data-dir=' + os.path.join(HERE, '_edgeprofile2').replace('\\', '/'),
                    '--virtual-time-budget=6000', '--window-size=1920,1080',
                    '--screenshot=' + dst.replace('\\', '/'), src],
                   capture_output=True, timeout=180)
    print(out, 'ok' if os.path.exists(dst) else 'FAIL', os.path.getsize(dst) // 1024 if os.path.exists(dst) else '')
