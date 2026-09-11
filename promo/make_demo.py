# -*- coding: utf-8 -*-
"""
健身交易员 · 宣传图数据工厂
生成一套 96 天、内部自洽的虚拟用户案例，注入真实 index.html 渲染后截图。

自洽口径（全部乘加闭合，不是编的数字）：
  BMR = 1660（Katch-McArdle：男 29 岁 176cm / 72.3kg / 体脂 17.4%）
  日净 = 摄入 − 运动 − BMR；涨停判定 = 日净 ≤ −500 且 < 0（与 App 一致）
  涨停日  52 天 × 均值 −700 = −36 400
  接近达标 35 天 × 均值 −420 = −14 700
  放纵日   6 天 × 均值 +430 =  +2 580
  累计净缺口 ≈ −48 500 kcal ÷ 7700 ≈ 6.3 kg 脂肪
  体重轨迹 78.6 → 72.3 kg（−6.3 kg），与累计缺口吻合
"""
import json, random, datetime, os

random.seed(20260911)

OUT = os.path.dirname(os.path.abspath(__file__))
DAYS = 96
END = datetime.date(2026, 9, 11)
START = END - datetime.timedelta(days=DAYS - 1)

BMR = 1660
TARGET_NET = -500
START_W, END_W = 78.6, 72.3
N_LIMITUP = 52
LONGEST_WIN = (38, 53)
CUR_STREAK = 8

BREAKFAST = [(280, "小米粥 + 水煮蛋"), (320, "燕麦牛奶碗"), (340, "全麦吐司 + 煎蛋"),
             (360, "菜肉包 2 个"), (380, "全麦三明治"), (450, "豆浆 + 油条"), (520, "牛肉粉")]
LUNCH     = [(430, "藜麦沙拉 + 鸡胸"), (480, "番茄鸡蛋荞麦面"), (520, "糙米饭 + 鸡胸 + 西兰花"),
             (550, "三文鱼寿司 8 贯"), (620, "轻食牛肉碗"), (680, "扬州炒饭"), (700, "日式咖喱饭")]
DINNER    = [(380, "鸡胸肉蔬菜沙拉"), (400, "豆腐青菜 + 杂粮饭"), (420, "蒸蛋 + 凉拌黄瓜 + 米饭"),
             (480, "清蒸鲈鱼 + 杂粮饭"), (560, "番茄牛腩 + 米饭"), (620, "红烧牛肉面"), (660, "烤肉拌饭")]
SNACK     = [(95, "苹果"), (105, "香蕉"), (120, "无糖希腊酸奶"), (150, "黑咖啡 + 全麦饼干"),
             (180, "混合坚果一小把"), (200, "蛋白棒"), (380, "奶茶 三分糖")]
SPORT     = [(210, "快走", 45), (260, "力量训练", 40), (280, "HIIT", 20), (300, "游泳", 30),
             (320, "慢跑", 30), (340, "羽毛球", 45), (380, "骑行", 60), (450, "越野跑", 45)]

MEAL_TIME = {'早餐': '08:00', '午餐': '12:00', '晚餐': '18:30', '加餐': '15:00'}
POOL = {'早餐': BREAKFAST, '午餐': LUNCH, '晚餐': DINNER, '加餐': SNACK}
WSHARE = {'早餐': 0.26, '午餐': 0.36, '晚餐': 0.29, '加餐': 0.09}


def pick(pool, target):
    return min(pool, key=lambda x: abs(x[0] - target))


def ts_of(d, hm):
    h, m = hm.split(':')
    return int(datetime.datetime(d.year, d.month, d.day, int(h), int(m)).timestamp() * 1000)


def build_flags():
    f = [False] * DAYS
    for i in range(LONGEST_WIN[0], LONGEST_WIN[1]):
        f[i] = True
    for i in range(DAYS - CUR_STREAK, DAYS):
        f[i] = True
    need = N_LIMITUP - sum(f)
    if need > 0:
        isolated = [i for i in range(DAYS)
                    if not f[i] and not f[i - 1] and (i + 1 >= DAYS or not f[i + 1])]
        random.shuffle(isolated)
        for i in isolated[:need]:
            f[i] = True
    short = N_LIMITUP - sum(f)
    if short > 0:
        rest = [i for i in range(DAYS) if not f[i]]
        random.shuffle(rest)
        for i in rest[:short]:
            f[i] = True
    return f


def longest_true(f):
    best = cur = 0
    for x in f:
        cur = cur + 1 if x else 0
        best = max(best, cur)
    return best


def tail_true(f):
    n = 0
    for x in reversed(f):
        if x:
            n += 1
        else:
            break
    return n


def build():
    flags = build_flags()
    diet, ex, wlog, rows = [], [], [], []
    fid = eid = 0

    # ---------- 体重轨迹：向理想线收敛 + 日波动（真实称重视律）----------
    prev = START_W
    for i in range(DAYS):
        d = START + datetime.timedelta(days=i)
        ideal = START_W + (END_W - START_W) * (i / float(DAYS - 1))
        if i == 0:
            w = START_W
        elif i == DAYS - 1:
            w = END_W
        else:
            pull = random.uniform(0.25, 0.60)
            noise = random.uniform(-0.42, 0.46)
            w = round(prev + (ideal - prev) * pull + noise, 1)
            w = max(END_W - 0.7, min(START_W + 0.2, w))
        prev = w
        step = 1 if i < 14 else (2 if random.random() < 0.62 else 3)
        if i % step == 0 or i in (0, DAYS - 1):
            wlog.append({'date': d.isoformat(), 'weight': w})

    # ---------- 每日记录 ----------
    for i in range(DAYS):
        d = START + datetime.timedelta(days=i)
        ds = d.isoformat()
        weekend = d.weekday() >= 5
        early = i < 12

        # 运动
        sport = 0
        if random.random() < (0.80 if weekend else 0.72):
            n = 2 if random.random() < (0.16 if weekend else 0.10) else 1
            for _ in range(n):
                base = random.choice(SPORT)
                kcal = int(base[0] * random.uniform(0.88, 1.12))
                sport += kcal
                hm = random.choice(['18:00', '19:00', '19:30', '20:00', '06:40', '07:10'])
                eid += 1
                ex.append({'id': 'ex%d' % eid, 'date': ds, 'name': base[1],
                           'duration': base[2], 'intensity': random.choice(['中', '中', '低', '高']),
                           'kcal': kcal, 'avgHr': random.randint(118, 152),
                           'method': 'met', 'manualKcal': None,
                           'time': hm, 'ts': ts_of(d, hm)})

        # 净额 → 反推摄入（这是数据自洽的关键）
        limit = flags[i]
        if limit:
            net = round(random.uniform(-850, -560))          # 全天在 ≤ −500 一侧
        elif random.random() < 0.854:
            net = round(random.uniform(-495, -310))          # 有缺口但差一口气，不能越过 −500
        else:
            net = round(random.uniform(180, 680))            # 放纵日
        intake = max(1100, min(2500, int(net + BMR + sport)))

        # 拆分到餐次
        n_meals = 3 if early else random.choice([4, 4, 5, 5, 3])
        meals = ['早餐', '午餐', '晚餐'] + ['加餐'] * (n_meals - 3)
        raw = {m: WSHARE[m] * random.uniform(0.82, 1.18) for m in meals}
        ssum = sum(raw.values())
        items = []
        for m in meals:
            share = intake * raw[m] / ssum
            base = pick(POOL[m], share)
            items.append([m, base[1], max(60, int(base[0] * random.uniform(0.9, 1.1)))])
        actual = sum(x[2] for x in items)
        diff = intake - actual
        mi = max(range(len(items)), key=lambda j: items[j][2])
        items[mi][2] = max(80, min(780, items[mi][2] + diff))

        day_total = 0
        for (m, nm, kcal) in items:
            hm = MEAL_TIME[m]
            hh, mm = hm.split(':')
            jit = random.randint(-25, 25)
            hh = max(0, min(23, int(hh) + (1 if int(mm) + jit >= 60 else 0)))
            hm2 = '%02d:%02d' % (hh, (int(mm) + jit) % 60)
            fid += 1
            day_total += kcal
            diet.append({'id': 'f%d' % fid, 'date': ds, 'name': nm, 'unit': '份', 'qty': 1,
                         'kcal': kcal, 'p': round(kcal * 0.25 / 4),
                         'f': round(kcal * 0.28 / 9), 'c': round(kcal * 0.47 / 4),
                         'meal': m, 'time': hm2, 'ts': ts_of(d, hm2), 'mode': '份',
                         'gram': None, 'displayQty': '1 份', 'src': 'lib', 'manualKcal': None})
        rows.append({'date': ds, 'skip': False, 'sport': sport, 'intake': day_total, 'limit': limit})

    # ---------- 统计校验（口径与 App 一致）----------
    intake_by, burn_by = {}, {}
    for x in diet:
        intake_by[x['date']] = intake_by.get(x['date'], 0) + x['kcal']
    for x in ex:
        burn_by[x['date']] = burn_by.get(x['date'], 0) + x['kcal']
    valid = [r for r in rows if not r['skip']]
    total_net = 0
    limit_cnt = 0
    for r in valid:
        ds = r['date']
        n = intake_by.get(ds, 0) - burn_by.get(ds, 0) - BMR
        total_net += n
        if n <= TARGET_NET and n < 0:
            limit_cnt += 1

    state = {
        'user': {'gender': 'male', 'age': 29, 'height': 176, 'weight': END_W,
                 'target': TARGET_NET, 'startWeight': START_W, 'targetWeight': 68.0,
                 'avatar': None, 'userId': 'FT_2026', 'bodyFat': 17.4, 'restingHr': 62,
                 'activity': 'light'},
        'body': {'bmi': round(END_W / (1.76 ** 2), 1), 'bodyFat': 17.4, 'muscleRate': 45.1,
                 'waterRate': 56.4, 'bodyAge': 27, 'visceralFat': 7, 'source': 'demo',
                 'syncedAt': '07:40'},
        'diet': diet, 'exercise': ex, 'exerciseCustom': [], 'weightLog': wlog,
        'limitUpCount': limit_cnt,
        'limitUpStreak': tail_true(flags), 'lastLimitUpDate': END.isoformat(),
        'streakDays': len(valid), 'maxStreak': max(len(valid), longest_true(flags) * 2),
        'lastRecordDate': END.isoformat(), 'everBroke': True, 'maxOverage': 640,
        'coins': 8640, 'exp': 2610, 'coinsEarnedTotal': 13260, 'totalDraws': 47,
        'cards': {'sanhu': 9, 'xiaosan': 9, 'zhuigao': 4, 'chaodi': 3, 'mancang': 9,
                  'gerou': 6, 'zhonghu': 9, 'dahu': 7, 'youzi': 5, 'duanxian': 3,
                  'jiazhi': 2, 'jigou': 3, 'zhuangjia': 1, 'kongcang': 0, 'gushen': 1},
        'collectRewards': {'30': True, '50': True, '70': True},
        'ach': {'leek': True, 'untie': True, 'wave': True, 'bull': True, 'tryorder': True,
                'halfpos': True, 'allin': True, 'hft': True},
        'usuals': [], 'foodFreq': {}, 'usualsHidden': [], 'usualsGuideSeen': True,
        'celebFired': True, 'gapToday': False,
        'coinToday': 45, 'coinDate': END.isoformat(), 'lastDate': END.isoformat()
    }
    summary = {'days': DAYS, 'recorded_days': len(valid), 'diet_n': len(diet), 'ex_n': len(ex),
               'weight_log_n': len(wlog),
               'total_intake': sum(intake_by.values()), 'total_burn': sum(burn_by.values()),
               'bmr_total': BMR * len(valid), 'total_net': total_net,
               'kg_from_net': round(-total_net / 7700.0, 2),
               'limit_ups': limit_cnt, 'limit_ups_planned': N_LIMITUP,
               'longest_streak': longest_true(flags), 'cur_streak': tail_true(flags),
               'start': START.isoformat(), 'end': END.isoformat()}
    return state, summary


if __name__ == '__main__':
    st, sm = build()
    with open(os.path.join(OUT, 'mock.json'), 'w', encoding='utf-8') as f:
        json.dump({'state': st, 'summary': sm}, f, ensure_ascii=False, indent=1)
    print(json.dumps(sm, ensure_ascii=False, indent=2))
    print('\n累计净缺口 %d kcal -> 折合脂肪 %.2f kg' % (sm['total_net'], sm['kg_from_net']))
    print('体重轨迹 %.1f -> %.1f kg   共 -%.1f kg' % (START_W, END_W, START_W - END_W))
