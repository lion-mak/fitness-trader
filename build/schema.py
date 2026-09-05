# -*- coding: utf-8 -*-
"""
统一食物数据模型

口径约定（重要）：
    所有营养数值均以「每 100 克（固体）或 100 毫升（液体）可食部」为基准。
    kcal  千卡 / 100g
    p     蛋白质 克 / 100g
    f     脂肪   克 / 100g
    c     碳水化合物 克 / 100g
    fb    膳食纤维 克 / 100g

来源标记 src：
    table  《中国食物成分表》第 6 版 / USDA FoodData Central 等权威成分表
    calc   按配方组成加权推算（含烹饪用油，已按出品重量归一）
    brand  市售包装食品营养标签典型值
    custom 用户自建
"""

BASIS_G = '100g'
BASIS_ML = '100ml'

SRC_TABLE = 'table'
SRC_CALC = 'calc'
SRC_BRAND = 'brand'
SRC_CUSTOM = 'custom'

FOODS = []    # 直接给出营养值的条目
DISHES = []   # 以配方形式录入、由构建脚本推算的条目

# 分类默认宏量营养素供能比（用于缺省字段兜底推算）
# 顺序：蛋白 / 脂肪 / 碳水 的供能占比
MACRO_SPLIT_DEFAULT = {
    '主食':   (0.12, 0.10, 0.78),
    '肉蛋':   (0.40, 0.55, 0.05),
    '水产':   (0.60, 0.35, 0.05),
    '蔬果':   (0.15, 0.05, 0.80),
    '豆奶':   (0.30, 0.40, 0.30),
    '坚果':   (0.14, 0.75, 0.11),
    '油脂':   (0.01, 0.99, 0.00),
    '调味':   (0.10, 0.20, 0.70),
    '家常':   (0.25, 0.45, 0.30),
    '外卖':   (0.20, 0.50, 0.30),
    '早餐':   (0.15, 0.35, 0.50),
    '饮品':   (0.05, 0.10, 0.85),
    '零食':   (0.08, 0.45, 0.47),
    '包装':   (0.10, 0.40, 0.50),
}
MACRO_SPLIT_FALLBACK = (0.15, 0.30, 0.55)

# 分类默认膳食纤维（克/100g）
FIBER_DEFAULT = {
    '主食': 1.5, '肉蛋': 0.0, '水产': 0.0, '蔬果': 2.0, '豆奶': 0.6,
    '坚果': 6.0, '油脂': 0.0, '调味': 1.0, '家常': 1.0, '外卖': 0.8,
    '早餐': 1.0, '饮品': 0.2, '零食': 1.5, '包装': 1.0,
}

# 分类默认一份重量（克），用于兜底
SERVING_DEFAULT = {
    '主食': 150, '肉蛋': 100, '水产': 100, '蔬果': 150, '豆奶': 200,
    '坚果': 25, '油脂': 10, '调味': 10, '家常': 250, '外卖': 350,
    '早餐': 150, '饮品': 250, '零食': 50, '包装': 100,
}

# 分类默认单位
UNIT_DEFAULT = {
    '主食': '碗', '肉蛋': '份', '水产': '份', '蔬果': '份', '豆奶': '杯',
    '坚果': '把', '油脂': '勺', '调味': '勺', '家常': '份', '外卖': '份',
    '早餐': '份', '饮品': '杯', '零食': '份', '包装': '份',
}


def _norm_alias(alias):
    """别名统一成列表：支持 空格 / 逗号 / 顿号 / 斜杠 分隔。"""
    if not alias:
        return []
    import re
    parts = re.split(r'[ ,，、/|]+', str(alias))
    return [x.strip() for x in parts if x.strip()]


def F(name, alias, kcal, p, f, c, fb, cat,
      unit=None, qty=1, gram=None, conv=None, src=SRC_TABLE, basis=BASIS_G, alc=0):
    """
    直接录入一条食物（数值为每 100g/100ml 口径）。

    name  名称
    alias 别名串（空格/逗号分隔）
    kcal/p/f/c/fb  每 100g 的 热量/蛋白质/脂肪/碳水/膳食纤维，None 表示缺失（构建时兜底推算）
    cat   分类
    unit  默认份量单位（克/毫升/份/个/碗/杯/片/块/根/勺/把/袋/罐/支/只）
    qty   默认份量数量
    gram  1 个 unit 对应的克重（称重基准）
    conv  常见规格换算 [(标签, 克重), ...]
    """
    FOODS.append(dict(
        kind='food', name=name, alias=_norm_alias(alias),
        kcal=kcal, p=p, f=f, c=c, fb=fb, cat=cat,
        unit=unit, qty=qty, gram=gram, conv=conv or [],
        src=src, basis=basis, alc=alc,
    ))


def D(name, alias, cat, items, yield_g,
      unit='份', gram=None, conv=None, src=SRC_CALC):
    """
    以配方录入一道菜/外卖/加工食品，构建脚本按配方加权推算每 100g 营养。

    items   [(食材名, 克重), ...]  食材名须能在 FOODS 中找到
    yield_g 出品总重量（克）。已考虑烹饪失水/吸油后的实际可食重量。
    unit    默认份量单位；gram 为一份的克重，缺省等于 yield_g
    """
    DISHES.append(dict(
        kind='dish', name=name, alias=_norm_alias(alias), cat=cat,
        items=items, yield_g=yield_g,
        unit=unit, qty=1, gram=(gram if gram else yield_g), conv=conv or [],
        src=src, basis=BASIS_G,
    ))
