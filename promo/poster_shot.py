# -*- coding: utf-8 -*-
"""
poster_shot.py —— 分享海报视觉验收（人眼看的，闸测不了）

为什么需要它：mp_poster_test 那 63+ 项断言**只能验数据与接线**，验不了版面。
第一版 63 项全绿，真浏览器出图一看三处目视问题（底部空块 / 走势显空 / 页脚两段糊成一句）。
⇒ 版面这类「好不好看」必须**出图看**，这是本脚本的职责。

做法：真浏览器打开本地 index.html → 注入一份好看的存档 → 调 drawReviewPoster
     把海报画到一张真 canvas 上 → toDataURL 落盘 PNG。
⛔ 只读不写：不改 index.html、不发版，纯本地渲染。
⚠️ 命名刻意**不带 `_` 前缀**：.gitignore 把 `promo/_*.py` 当一次性临时脚本不入库，
   而本脚本是可重跑的长期验收工具，改名才能入库（不入库 = 下次视觉验收要重写一遍）。

用法（必须用带 playwright 的隔离 venv，⛔ 不要往系统 python 装）：
  C:\\Users\\Administrator\\.workbuddy\\binaries\\python\\envs\\default\\Scripts\\python.exe promo/poster_shot.py
输出：promo/poster_sample.png（本机产物，按既定口径不入库）
"""
import io, os, sys, json, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
OUT_PNG = os.path.join(HERE, 'poster_sample.png')

# 一份「好看」的存档：盈余、连击、人格、段位
SEED = {
    "exp": 780, "curve": 4, "weight": 80, "height": 175, "age": 30, "sex": "m", "target": 75,
    "diet": [], "exercise": [], "body": {}, "customFoods": [], "history": [],
    "persona": {"code": "KSRA", "name": "K线大师", "fun": 0, "eggName": "",
                "axes": [{"id": 1, "a": 9, "b": 7}, {"id": 2, "a": 9, "b": 7},
                         {"id": 3, "a": 7, "b": 9}, {"id": 4, "a": 9, "b": 7}],
                "answeredAt": "2026-10-01", "history": []},
}
PLAN = [  # (运动kcal, 饮食kcal, 食物名, 运动名)
    (900, 1300, '照烧鸡腿饭', '跑步'), (700, 1250, '牛肉粉', '力量训练'),
    (950, 1200, '三文鱼沙拉', '游泳'), (600, 1400, '麻婆豆腐', '快走'),
    (900, 1150, '虾仁炒蛋', '跑步'), (850, 1300, '照烧鸡腿饭', '骑行'),
]

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

    idx = os.path.join(ROOT, 'index.html')
    url = 'file:///' + idx.replace('\\', '/')
    with sync_playwright() as p:
        b = launch_browser(p)
        pg = b.new_page(viewport={'width': 430, 'height': 932})
        pg.goto(url)
        pg.wait_for_timeout(600)
        # 注入存档：按今天往前铺 6 天
        pg.evaluate("""(args) => {
          const [seed, plan] = args;
          const pad2 = n => String(n).padStart(2,'0');
          const ymd = d => d.getFullYear()+'-'+pad2(d.getMonth()+1)+'-'+pad2(d.getDate());
          const D = n => { const d=new Date(); d.setHours(0,0,0,0); d.setDate(d.getDate()+n); return ymd(d); };
          const s = JSON.parse(JSON.stringify(seed));
          plan.forEach((p,i)=>{ s.diet.push({id:'f'+i,name:p[2],kcal:p[1],date:D(i),meal:'lunch'});
                                 s.exercise.push({id:'e'+i,name:p[3],kcal:p[0],date:D(i),min:40}); });
          localStorage.setItem('jianpan_v2', JSON.stringify(s));
        }""", [SEED, PLAN])
        pg.reload(); pg.wait_for_timeout(700)
        # 画海报到独立 canvas 并截图
        shot = pg.evaluate("""() => {
          const d = reviewPosterData(true);
          const cv = _posterCanvas();
          drawReviewPoster(cv, d, 340);
          return JSON.stringify({badge:d.badge, roast:d.roast, rank:d.rankName, persona:d.persona,
                                 total:d.totalTxt, col:d.col, rate:d.rate, hit:d.hit, cnt:d.cnt,
                                 bigIn:d.bigIn, bigOut:d.bigOut, kg:d.kgTxt,
                                 png: cv.toDataURL('image/png')});
        }""")
        info = json.loads(shot)
        print(u'布局数据：%s' % json.dumps({k: v for k, v in info.items() if k != 'png'}, ensure_ascii=False))
        # ⚠️ #poster-cv 是 display:none（故意藏着的），playwright 的 element.screenshot()
        #    对不可见元素会一直等「element is not stable」⇒ 改走 toDataURL 拿字节自己落盘。
        import base64
        png_b64 = info.pop('png').split(',', 1)[1]
        with io.open(OUT_PNG, 'wb') as f:
            f.write(base64.b64decode(png_b64))
        b.close()
    print(u'✅ 海报样张已出：%s' % OUT_PNG)

if __name__ == '__main__':
    main()
