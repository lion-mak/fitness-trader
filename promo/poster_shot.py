# -*- coding: utf-8 -*-
"""
poster_shot.py —— 复盘海报视觉验收（人眼看的，闸测不了）

为什么需要它：mp_poster_test 的断言**只能验数据与接线**，验不了版面。
历史：第一版 63 项全绿、真浏览器出图一看三处目视问题（底部空块 / 走势显空 / 页脚两段糊成一句）。
⇒ 版面这类「好不好看」必须**出图看**，这是本脚本的职责。

v2.12.0 起出**四张**图（同时验「页面上看到的」与「导出的」是否同构）：
  rv_page_week.png  / rv_page_month.png    页面里 #lb-review 那块（= 用户平时看到的）
  rv_poster_week.png / rv_poster_month.png 走 drawReviewPoster 导出的成品海报
v2.13.0 起追加第五张：rv_poster_week_dd.png（哪天摆一桌火锅 ⇒ 造出回撤，
  肉眼验「峰 / 谷 / 最大回撤」三处标注 —— 全达标的存档里回撤恒为 0，标注根本不出现）。

做法：真浏览器打开本地 index.html → 注入一份存档 → 切到龙虎榜页 → 区块截图 + canvas 出图。
⛔ 只读不写：不改 index.html、不发版，纯本地渲染。
⚠️ 命名刻意**不带 `_` 前缀**：.gitignore 把 `promo/_*.py` 当一次性临时脚本不入库，
   而本脚本是可重跑的长期验收工具，改名才能入库（不入库 = 下次视觉验收要重写一遍）。

用法（必须用带 playwright 的隔离 venv，⛔ 不要往系统 python 装）：
  C:\\Users\\Administrator\\.workbuddy\\binaries\\python\\envs\\default\\Scripts\\python.exe promo/poster_shot.py
输出：promo/_shots/ 下的四张 png（本机产物，按既定口径不入库）
"""
import io, os, sys, json, base64

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
OUT = os.path.join(HERE, '_shots')

# 一份「好看」的存档：盈余、连击、人格、段位
SEED = {
    "exp": 780, "curve": 4, "weight": 80, "height": 175, "age": 30, "sex": "m", "target": 75,
    "diet": [], "exercise": [], "body": {}, "customFoods": [], "history": [],
    "persona": {"code": "KSRA", "name": "K线大师", "fun": 0, "eggName": "",
                "axes": [{"id": 1, "a": 9, "b": 7}, {"id": 2, "a": 9, "b": 7},
                         {"id": 3, "a": 7, "b": 9}, {"id": 4, "a": 9, "b": 7}],
                "answeredAt": "2026-10-01", "history": []},
}
PLAN = [  # (运动kcal, 饮食kcal, 食物名, 运动名, 时长min)
    (900, 1300, '照烧鸡腿饭', '跑步', 45), (700, 1250, '牛肉粉', '力量训练', 60),
    (950, 1200, '三文鱼沙拉', '游泳', 50), (600, 1400, '麻婆豆腐', '快走', 70),
    (900, 1150, '虾仁炒蛋', '跑步', 40), (850, 1300, '照烧鸡腿饭', '骑行', 55),
]
# 第二份存档：第 3 天（i=2）摆一桌火锅 ⇒ 累计缺口出现**回撤**，
# 用来肉眼验「最大回撤」虚线 + 数值标注（Mak 2026-10-03 要求的标注里唯一需要造数据的那个）。
PLAN_DD = PLAN[:2] + [(200, 2400, '火锅局', '散步', 20)] + PLAN[3:]

# 🔴 注入存档的 JS。⚠️ 运动记录**必须写 `duration`**（真源字段，addExercise 写的就是它）——
#    本脚本曾写成 `min:[4]`，那是老档兜底字段 ⇒ 出图永远走兼容分支，
#    「内核把时长读成 0 分钟」这类字段 bug 在视觉验收里**根本看不见**（2026-10-03 修正）。
INJECT_JS = """(args) => {
  const [seed, plan] = args;
  const pad2 = n => String(n).padStart(2,'0');
  const ymd = d => d.getFullYear()+'-'+pad2(d.getMonth()+1)+'-'+pad2(d.getDate());
  const D = n => { const d=new Date(); d.setHours(0,0,0,0); d.setDate(d.getDate()+n); return ymd(d); };
  const s = JSON.parse(JSON.stringify(seed));
  plan.forEach((p,i)=>{ s.diet.push({id:'f'+i,name:p[2],kcal:p[1],date:D(-i),meal:'lunch'});
                         s.exercise.push({id:'e'+i,name:p[3],kcal:p[0],date:D(-i),duration:p[4]}); });
  localStorage.setItem('jianpan_v2', JSON.stringify(s));
}"""

# 切到龙虎榜页（页面用 .page.active 控制显隐）；每次 reload 后都要重做一次
PAGE_JS = """() => {
  document.querySelectorAll('.page').forEach(x => x.classList.remove('active'));
  const el = document.getElementById('page-leaderboard');
  if (el) el.classList.add('active');
  window.scrollTo(0, 0);
}"""


def launch_browser(pw):
    """与 pwa_gate_state.py 同款回退链：本机没装 playwright 自带 chromium（ms-playwright 目录是空的），
    ⛔ 别去 `playwright install` 下载（几百 MB、这台机器的 C 盘紧张）——直接用系统浏览器。"""
    last = None
    for kw in ({"channel": "msedge"},
               {"executable_path": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"},
               {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"}):
        try:
            return pw.chromium.launch(**kw)
        except Exception as e:      # noqa: BLE001
            last = e
    raise SystemExit(u'找不到可用浏览器内核：%s' % last)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    from playwright.sync_api import sync_playwright
    import http.server, socketserver, threading, functools

    os.makedirs(OUT, exist_ok=True)

    # ⚠️ 必须走 http 而不是 file:// —— canvas 一旦画了 file:// 加载的段位卡图就会被判「跨源污染」，
    #    toDataURL 直接抛 Tainted canvases may not be exported。线上是同源 https，本来就没这问题。
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(u'本地服务 http://127.0.0.1:%d/' % port)
    url = 'http://127.0.0.1:%d/index.html' % port

    with sync_playwright() as p:
        b = launch_browser(p)
        pg = b.new_page(viewport={'width': 430, 'height': 932}, device_scale_factor=2)
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(url)
        pg.wait_for_timeout(600)
        pg.evaluate(INJECT_JS, [SEED, PLAN])
        pg.reload(); pg.wait_for_timeout(700)
        # 切到龙虎榜页（页面用 .page.active 控制显隐）
        pg.evaluate("""() => {
          document.querySelectorAll('.page').forEach(x => x.classList.remove('active'));
          const el = document.getElementById('page-leaderboard');
          if (el) el.classList.add('active');
          window.scrollTo(0, 0);
        }""")
        # 切到龙虎榜页（页面用 .page.active 控制显隐）
        pg.evaluate(PAGE_JS)
        def shoot(rng, tag):
            pg.evaluate("(r) => setLbRange(r)", rng)
            pg.wait_for_timeout(500)
            blk = pg.locator('#lb-review .rvp')
            blk.scroll_into_view_if_needed()
            pg.wait_for_timeout(200)
            blk.screenshot(path=os.path.join(OUT, 'rv_page_%s.png' % tag))
            shot = pg.evaluate("""async (r) => {
              const d = reviewPosterData(r === 'week');
              const im = await loadRankImg(d.rankLv);
              const cv = drawReviewPoster(_posterCanvas(), d, 375, im);
              return JSON.stringify({
                badge: d.badge, roast: d.roast, rank: d.rankName, persona: d.persona,
                total: d.totalTxt, kg: d.kgTxt, hit: d.hitTxt,
                stats: d.stats.map(s => s.n + s.u + '/' + s.l),
                boards: d.boards.map(b => b.k + ':' + b.n + ' ' + b.v),
                tip: d.tip, dd: d.marks ? d.marks.ddTxt : '--',
                W: cv.width / 2, H: cv.height / 2,
                card: !!im, png: cv.toDataURL('image/png')
              });
            }""", rng)
            info = json.loads(shot)
            png = info.pop('png').split(',', 1)[1]
            with io.open(os.path.join(OUT, 'rv_poster_%s.png' % tag), 'wb') as f:
                f.write(base64.b64decode(png))
            print(u'[%s] %s' % (tag, json.dumps(info, ensure_ascii=False)))

        for rng, tag in (('week', 'week'), ('month', 'month')):
            shoot(rng, tag)
        # 第三份样张（week_dd）：把第 3 天换成火锅局 ⇒ 累计缺口出现回撤，
        # 肉眼验「峰 / 谷 / 最大回撤」三处标注与虚线（峰谷一直在，回撤要造数据才有）。
        pg.evaluate(INJECT_JS, [SEED, PLAN_DD])
        pg.reload(); pg.wait_for_timeout(700)
        pg.evaluate(PAGE_JS)
        shoot('week', 'week_dd')
        b.close()
    httpd.shutdown()
    if errs:
        print(u'⚠️ 页面 JS 报错：%s' % ' | '.join(errs[:5]))
        return 1
    print(u'✅ 四张图已出：%s' % OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
