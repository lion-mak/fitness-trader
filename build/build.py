# -*- coding: utf-8 -*-
"""食物数据库构建脚本

流程：
    1. 汇总各数据模块（食材 / 菜品配方 / 包装饮品零食 / 烹饪方式派生）
    2. 按配方加权推算菜品每 100g 营养
    3. 缺失字段按分类供能比兜底推算，并在 est 字段标记（UI 可提示"估算值"）
    4. 用 pypinyin 生成全拼与首字母，支持拼音检索
    5. 去重（手工录入优先于派生）
    6. 一致性抽检：宏量营养素折算热量 vs 标注热量
    7. 输出 ../data/foods.json

用法：
    python build.py
"""
import io
import json
import os
import sys
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pypinyin import lazy_pinyin, Style

import schema
# 导入顺序即优先级：手工录入在前，派生在后（重名时保留先出现的）
import data_ing_1
import data_ing_2
import data_ing_3
import data_dish_1
import data_dish_2
import data_dish_3
import data_brand
import data_methods

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'foods.json')


def r1(v):
    return round(float(v), 1)


def pinyin_of(text):
    """返回 (全拼, 首字母)。非中文字符原样保留在首字母里。"""
    if not text:
        return '', ''
    full = ''.join(lazy_pinyin(text))
    ini = ''.join(lazy_pinyin(text, style=Style.FIRST_LETTER))
    return full, ini


def build_food_index():
    """按名称建索引，重名保留先出现的。"""
    idx = OrderedDict()
    dup = []
    for f in schema.FOODS:
        n = f['name']
        if n in idx:
            dup.append(n)
            continue
        idx[n] = f
    return idx, dup


def fill_defaults(rec, cat):
    """补齐缺失字段，返回被估算的字段名列表。"""
    est = []
    kcal = rec.get('kcal')

    if kcal is None:
        # 无热量则用宏量折算；仍无则给 0 并标记
        p, f, c = rec.get('p'), rec.get('f'), rec.get('c')
        if None not in (p, f, c):
            kcal = 4 * p + 9 * f + 4 * c
            est.append('kcal')
        else:
            kcal = 0
            est.append('kcal')

    pk, pf, pc = schema.MACRO_SPLIT_DEFAULT.get(cat, schema.MACRO_SPLIT_FALLBACK)
    if rec.get('p') is None:
        rec['p'] = r1(kcal * pk / 4)
        est.append('p')
    if rec.get('f') is None:
        rec['f'] = r1(kcal * pf / 9)
        est.append('f')
    if rec.get('c') is None:
        rec['c'] = r1(kcal * pc / 4)
        est.append('c')
    if rec.get('fb') is None:
        rec['fb'] = r1(schema.FIBER_DEFAULT.get(cat, 1.0))
        est.append('fb')

    if not rec.get('unit'):
        rec['unit'] = schema.UNIT_DEFAULT.get(cat, '份')
    if not rec.get('gram'):
        rec['gram'] = schema.SERVING_DEFAULT.get(cat, 150)
    if not rec.get('qty'):
        rec['qty'] = 1
    # 热量统一取整（界面不显示小数）；宏量保留 1 位（营养标签惯例，低含量食材取整会丢失信息）
    rec['kcal'] = int(round(kcal))
    rec['p'] = r1(rec['p'])
    rec['f'] = r1(rec['f'])
    rec['c'] = r1(rec['c'])
    rec['fb'] = r1(rec['fb'])
    return est


def normalize_base(f):
    return dict(
        kind='food', name=f['name'], alias=f['alias'], cat=f['cat'],
        kcal=f['kcal'], p=f['p'], f=f['f'], c=f['c'], fb=f['fb'],
        unit=f['unit'], qty=f['qty'], gram=f['gram'],
        conv=[{'label': a, 'gram': b} for a, b in (f['conv'] or [])],
        src=f['src'], basis=f['basis'], alc=f.get('alc', 0),
    )


def compute_dish(d, index):
    """按配方加权推算每 100g 营养；返回 (记录, 未解析食材列表, 未填字段标记)。"""
    tot = {'kcal': 0.0, 'p': 0.0, 'f': 0.0, 'c': 0.0, 'fb': 0.0}
    unresolved = []
    partial = []

    for ing_name, grams in d['items']:
        ing = index.get(ing_name)
        if ing is None:
            unresolved.append(ing_name)
            continue
        k = grams / 100.0
        for key in tot:
            v = ing.get(key)
            if v is None:
                partial.append((ing_name, key))
                v = 0
            tot[key] += v * k

    yield_g = float(d['yield_g'] or sum(g for _, g in d['items']))
    scale = 100.0 / yield_g if yield_g > 0 else 0
    return dict(
        kind='dish', name=d['name'], alias=d['alias'], cat=d['cat'],
        # 配方加权推算会产生 15 位浮点尾数，统一取整：热量取整，宏量保留 1 位（营养标签惯例）
        kcal=int(round(tot['kcal'] * scale)), p=r1(tot['p'] * scale), f=r1(tot['f'] * scale),
        c=r1(tot['c'] * scale), fb=r1(tot['fb'] * scale),
        unit=d['unit'], qty=1, gram=d['gram'] or int(yield_g),
        conv=[{'label': a, 'gram': b} for a, b in (d['conv'] or [])],
        src=d['src'], basis='100g',
        recipe=[{'name': n, 'gram': g} for n, g in d['items']],
        yield_g=int(yield_g),
    ), unresolved, partial


def main():
    index, base_dup = build_food_index()

    records = []
    unresolved_all = []
    partial_all = []
    derived_names = set()

    # 1) 直接录入的食材/包装/饮品/零食
    for name, f in index.items():
        rec = normalize_base(f)
        est = fill_defaults(rec, rec['cat'])
        rec['est'] = est
        records.append(rec)

    # 2) 配方菜品
    for d in schema.DISHES:
        rec, unresolved, partial = compute_dish(d, index)
        unresolved_all.extend(unresolved)
        partial_all.extend(partial)
        if rec['kcal'] <= 0 and rec['p'] <= 0 and rec['c'] <= 0:
            continue  # 配方完全无法解析，丢弃
        rec['est'] = []
        records.append(rec)
        if d.get('name') and len(d['alias']) == 0:
            derived_names.add(rec['name'])

    # 3) 去重（保留先出现：手工 > 派生）
    seen = {}
    final = []
    dup_names = []
    for rec in records:
        n = rec['name']
        if n in seen:
            dup_names.append(n)
            continue
        seen[n] = True
        final.append(rec)

    # 4) 拼音索引
    for rec in final:
        texts = [rec['name']] + list(rec['alias'])
        fulls, inis = [], []
        for t in texts:
            fu, ini = pinyin_of(t)
            if fu:
                fulls.append(fu)
            if ini:
                inis.append(ini)
        rec['py'] = ' '.join(fulls)
        rec['ini'] = ' '.join(inis)

    # 5) 一致性抽检：宏量折算热量 vs 标注热量
    #    说明：中国食物成分表的"碳水化合物"含膳食纤维，纤维按 2 kcal/g 折算；
    #          酒精、黑咖啡、无糖茶饮等无宏量供能的条目跳过核对。
    outliers = []
    for rec in final:
        p, f, c, fb = rec['p'], rec['f'], rec['c'], rec['fb']
        if p + f + c < 1.0:
            continue
        avail_c = max(c - fb, 0.0)
        calc = 4 * p + 9 * f + 4 * avail_c + 7 * rec.get('alc', 0)
        diff = abs(calc - rec['kcal'])
        tol = max(45.0, 0.35 * rec['kcal']) if fb > 15 else max(30.0, 0.28 * rec['kcal'])
        if rec['kcal'] > 60 and diff > tol:
            outliers.append((rec['name'], round(calc), rec['kcal'], round(diff)))

    # 5.5) 生成「汉字 → 拼音首字母」映射，供前端给「用户自建食物」也做拼音检索
    chars = set()
    for rec in final:
        for ch in rec['name']:
            if '\u4e00' <= ch <= '\u9fff':
                chars.add(ch)
        for a in rec['alias']:
            for ch in a:
                if '\u4e00' <= ch <= '\u9fff':
                    chars.add(ch)
    py_map = {}
    for ch in sorted(chars):
        ini = ''.join(lazy_pinyin(ch, style=Style.FIRST_LETTER))
        if ini:
            py_map[ch] = ini
    py_path = os.path.join(os.path.dirname(OUT_PATH), 'py-initials.json')
    with io.open(py_path, 'w', encoding='utf-8') as fp:
        json.dump(py_map, fp, ensure_ascii=False, separators=(',', ':'))
    print('拼音首字母表: %d 字 -> %s' % (len(py_map), os.path.normpath(py_path)))

    # 6) 排序：分类 → 名称，便于人肉查阅
    cat_order = ['主食', '家常', '外卖', '早餐', '肉蛋', '水产', '蔬果', '豆奶',
                 '坚果', '油脂', '调味', '包装', '饮品', '零食']
    final.sort(key=lambda r: (cat_order.index(r['cat']) if r['cat'] in cat_order else 99, r['name']))

    for i, rec in enumerate(final, 1):
        rec['id'] = 'f%04d' % i

    meta = OrderedDict([
        ('version', '1.0.0'),
        ('generatedBy', 'build/build.py'),
        ('count', len(final)),
        ('basis', '每 100 克（固体）/ 每 100 毫升（液体）可食部'),
        ('units', OrderedDict([
            ('kcal', '千卡'), ('p', '克'), ('f', '克'), ('c', '克'), ('fb', '克'), ('alc', '克'), ('alc', '克'),
            ('gram', '克'), ('qty', rec_unit_note()),
        ])),
        ('sources', OrderedDict([
            ('table', '《中国食物成分表》第 6 版 / USDA FoodData Central'),
            ('calc', '按配方组成加权推算（含烹饪用油，已按出品重量归一），为估算值'),
            ('brand', '市售包装食品营养标签典型值'),
            ('custom', '用户自建'),
        ])),
        ('estNote', 'est 字段列出由分类供能比兜底推算的字段，非实测值'),
        ('energyNote', '热量核对口径：4*蛋白质 + 9*脂肪 + 4*(碳水-膳食纤维) + 7*酒精；膳食纤维在中国食物成分表中不计入能量'),
        ('outlierNote', '少数高纤维食材（海苔/梅干菜/螺旋藻/迷迭香等）成分表热量低于宏量折算值，因部分不可利用碳水不计能，属正常现象'),
        ('errorRange', {
            'table': '±10%～15%（成分表为代表性样品值，品种/产地/季节会有差异）',
            'calc': '±20%～30%（受用油量、火候、出品重量估计影响）',
            'brand': '±5%（标签值，法规允许误差范围）',
        }),
        ('defaults', OrderedDict([
            ('macroSplitByCat', {k: list(v) for k, v in schema.MACRO_SPLIT_DEFAULT.items()}),
            ('note', '缺失字段按上述分类供能比推算，并在 est 标记'),
        ])),
        ('categories', dict(Counter(r['cat'] for r in final))),
        ('sourceCount', dict(Counter(r['src'] for r in final))),
    ])

    out = OrderedDict([('meta', meta), ('foods', final)])

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with io.open(OUT_PATH, 'w', encoding='utf-8') as fp:
        json.dump(out, fp, ensure_ascii=False, separators=(',', ':'))

    # 报告
    print('=' * 60)
    print('构建完成 ->', os.path.normpath(OUT_PATH))
    print('条目总数 :', len(final))
    print('分类分布 :', dict(Counter(r['cat'] for r in final)))
    print('来源分布 :', dict(Counter(r['src'] for r in final)))
    print('重名跳过 :', len(dup_names), dup_names[:12])
    print('估算字段 :', sum(1 for r in final if r.get('est')))
    if unresolved_all:
        print('!! 未解析食材:', len(unresolved_all), sorted(set(unresolved_all)))
    else:
        print('未解析食材: 0')
    if partial_all:
        print('!! 配方中取到空值字段:', len(partial_all), sorted(set(partial_all))[:10])
    if outliers:
        print('!! 热量与宏量折算偏差较大:', len(outliers))
        for o in outliers[:15]:
            print('   ', o)
    else:
        print('热量一致性抽检: 全部通过')
    print('=' * 60)


def rec_unit_note():
    return '默认份量数量（unit 为 碗/个/份/杯/片/勺/把/根/块/张/条/只/罐/瓶/盒/袋/支/串/段/瓣/节/棵/朵/粒）'


if __name__ == '__main__':
    main()
