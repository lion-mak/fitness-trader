# -*- coding: utf-8 -*-
"""操盘手段位 · 升级曲线算表（可复跑，改参数即看效果）

用法：python promo/rank_curve.py
输出：promo/rank_curve.md（表格）+ 终端摘要

经验来源（与 PWA index.html 同源）：
  记录饮食 +1/笔、记录运动 +2/次、涨停 +30/次（每日最多一次）
  涨停条件：dailyNet(day) <= user.target，dailyNet = 摄入 - 运动消耗 - BMR

日均经验的口径：**行为模型**（多少笔记录 × 单价 + 涨停频率 × 30），
不是「总经验 ÷ 天数」——后者会把历史口径混杂进去。

画像：
  轻度 = 每天 2 笔饮食、几乎不运动、涨停 0
  中度 = 每天 3.5 笔 + 0.5 次运动 + 每周 1 次涨停
  重度 = promo/mock.json 演示存档的**实测行为参数**（96 天：饮食 4.04 笔/天、
         运动 0.92 次/天、涨停 52 天 = 0.542 次/天）
"""
RANKS = [
    ('韭菜', 1), ('散户', 2), ('小散', 4), ('中户', 6), ('大户', 8),
    ('牛散', 10), ('游资', 13), ('主力', 16), ('机构', 20), ('庄家', 24), ('股神', 30),
]


# ---------- 曲线 ----------
def cum_old(lv):
    """旧（v2.7.58 及以前）：每级固定 100 ⇒ 累计 100(lv-1)"""
    return (lv - 1) * 100


def cum_new(lv):
    """新（v2.7.59）：升到下一级需「当前等级 ×10」经验 ⇒ 累计 5·lv·(lv-1)"""
    return 5 * lv * (lv - 1)


CURVES = [('旧 100/级', cum_old), ('新 等级×10', cum_new)]

# 名称, 饮食笔/天, 运动次/天, 涨停次/天
PROFILES = [
    ('轻度', 2.00, 0.10, 0.0),
    ('中度', 3.50, 0.50, 1 / 7),
    ('重度', 4.04, 0.92, 52 / 96),
]


def daily_exp(diet, ex, lu):
    return diet * 1 + ex * 2 + lu * 30


def days_to(cum_fn, lv, dep):
    return cum_fn(lv) / dep if dep > 0 else float('inf')


def lv_from_exp(cum_fn, exp, lv_max=300):
    lv = 1
    while lv < lv_max and cum_fn(lv + 1) <= exp:
        lv += 1
    return lv


def migrate_exp(exp):
    """v2.7.59 换代补偿（只升不降）：抬到新曲线上「旧段位」的门槛"""
    lv_old = int(exp) // 100 + 1
    return max(int(exp), cum_new(lv_old))


def fmt_days(d):
    if d == float('inf'):
        return '—'
    if d < 1:
        return '<1 天'
    if d < 30:
        return '%.0f 天' % d
    if d < 365:
        return '%.1f 个月' % (d / 30.0)
    return '%.1f 年' % (d / 365.0)


def rank_of(lv):
    name = RANKS[0][0]
    for n, l in RANKS:
        if lv >= l:
            name = n
    return name


def main():
    L = []
    w = L.append

    w('# 操盘手段位 · 升级曲线算表\n')
    w('> 由 `promo/rank_curve.py` 生成，改参数重跑即可。\n')
    w('> 经验来源：饮食 +1/笔、运动 +2/次、涨停 +30/次（每日限一次）。\n')

    # 1 日均经验
    w('## 1. 日均经验（行为模型：笔数 × 单价 + 涨停频率 × 30）\n')
    w('| 画像 | 饮食 | 运动 | 涨停频率 | 记录所得 | 涨停所得 | **日均合计** | 涨停占比 |')
    w('|---|---|---|---|---|---|---|---|')
    for name, diet, ex, lu in PROFILES:
        base = daily_exp(diet, ex, 0)
        lu_exp = lu * 30
        tot = base + lu_exp
        w('| %s | %.2f 笔 | %.2f 次 | %s | %.1f | %.1f | **%.1f** | %.0f%% |' % (
            name, diet, ex, ('0' if lu == 0 else '%.2f 次/天（每周 %.1f 次）' % (lu, lu * 7)),
            base, lu_exp, tot, 100 * lu_exp / tot))
    w('')
    w('⚠️ 涨停是经验的主力（重度画像里占七成）—— 经验体系奖励的其实是「热量达标」，不是「记录动作」本身。\n')

    # 2 每级成本
    w('## 2. 每级升级成本（升到 lv N+1 需要多少经验）\n')
    show = [1, 2, 3, 4, 5, 6, 8, 10, 13, 16, 20, 24, 29]
    w('| 曲线 | ' + ' | '.join('lv%d→%d' % (l, l + 1) for l in show) + ' |')
    w('|---' * (len(show) + 1) + '|')
    for cname, fn in CURVES:
        w('| %s | ' % cname + ' | '.join(str(fn(l + 1) - fn(l)) for l in show) + ' |')
    w('')
    w('旧曲线每级恒 100（第 1 级和第 29 级同价）；新曲线 10 / 20 / 30 … / 290 线性递增。\n')

    # 3 段位门槛
    w('## 3. 各段位累计经验门槛\n')
    w('| 段位 | lv | 旧门槛 | 新门槛 | 倍数 |')
    w('|---|---|---|---|---|')
    for n, lv in RANKS:
        o, nw = cum_old(lv), cum_new(lv)
        w('| %s | lv%d | %d | %d | %.2f× |' % (n, lv, o, nw, nw / o if o else 0))
    w('')

    # 4 天数对比
    w('## 4. 到达各段位所需时间（旧 → 新）\n')
    for cname, fn in CURVES:
        w('### 曲线：%s\n' % cname)
        w('| 段位 | lv | 门槛 | ' + ' | '.join(p[0] for p in PROFILES) + ' |')
        w('|---' * (len(PROFILES) + 3) + '|')
        for n, lv in RANKS:
            row = [fmt_days(days_to(fn, lv, daily_exp(p[1], p[2], p[3]))) for p in PROFILES]
            w('| %s | lv%d | %d | ' % (n, lv, fn(lv)) + ' | '.join(row) + ' |')
        w('')

    w('### 首段（韭菜 → 散户）快了多少 / 顶段（股神）慢了多少\n')
    w('| 画像 | 旧·到散户 | 新·到散户 | 旧·到股神 | 新·到股神 |')
    w('|---|---|---|---|---|')
    for pname, diet, ex, lu in PROFILES:
        dep = daily_exp(diet, ex, lu)
        w('| %s | %s | %s | %s | %s |' % (
            pname, fmt_days(days_to(cum_old, 2, dep)), fmt_days(days_to(cum_new, 2, dep)),
            fmt_days(days_to(cum_old, 30, dep)), fmt_days(days_to(cum_new, 30, dep))))
    w('')

    # 5 迁移对照
    w('## 5. 存量 exp 换代补偿对照（只升不降）\n')
    w('交点 = lv20 / exp1900：低于它新曲线更便宜（白赚），高于它新曲线更贵（会被补偿托住）。\n')
    w('| 旧 exp | 旧 lv | 旧段位 | 补偿后 exp | 新 lv | 新段位 | 等级变化 |')
    w('|---|---|---|---|---|---|---|')
    for e in [0, 250, 500, 1000, 1500, 1900, 2000, 2610, 3000, 5000, 9000]:
        lo = lv_from_exp(cum_old, e)
        me = migrate_exp(e)
        ln = lv_from_exp(cum_new, me)
        d = ln - lo
        tag = '持平' if d == 0 else ('**+%d 级**（白赚）' % d if d > 0 else '%d 级（⚠️不该出现）' % d)
        w('| %d | lv%d | %s | %d | lv%d | %s | %s |' % (
            e, lo, rank_of(lo), me, ln, rank_of(ln), tag))
    w('')
    w('⚠️ 补偿会抬高老存档的 exp 数字（如 2610 → 3510）。这是换取「段位不倒退」付的代价；\n')
    w('   若选择不补偿，同一份存档会从庄家掉到机构（lv27 → lv23）。\n')

    open('promo/rank_curve.md', 'w', encoding='utf-8').write('\n'.join(L))

    print('日均经验：' + '  '.join(
        '%s=%.1f' % (p[0], daily_exp(p[1], p[2], p[3])) for p in PROFILES))
    print('')
    print('%-14s %s' % ('到段位', '  '.join('%s' % p[0] for p in PROFILES)))
    for n, lv in RANKS:
        o = [fmt_days(days_to(cum_old, lv, daily_exp(p[1], p[2], p[3]))) for p in PROFILES]
        nw = [fmt_days(days_to(cum_new, lv, daily_exp(p[1], p[2], p[3]))) for p in PROFILES]
        print('%-6s lv%-3d 旧 %-28s 新 %s' % (n, lv, ' / '.join(o), ' / '.join(nw)))
    print('')
    print('迁移补偿：exp2610(旧 lv27 庄家) → %d → lv%d %s'
          % (migrate_exp(2610), lv_from_exp(cum_new, migrate_exp(2610)),
             rank_of(lv_from_exp(cum_new, migrate_exp(2610)))))
    print('→ 已写 promo/rank_curve.md')


if __name__ == '__main__':
    main()
