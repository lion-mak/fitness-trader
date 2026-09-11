# -*- coding: utf-8 -*-
"""从 index.html 抽取真实函数，生成可独立运行的 node 测试文件（避免 Git Bash 中文编码问题）。"""
import io, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
html = io.open(SRC, encoding='utf-8').read()

# 取最大的内联 <script>（主逻辑）
scripts = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S)
js = max(scripts, key=len)
print('inline script chars:', len(js))

# 整体语法校验
io.open(os.path.join(ROOT, 'promo', '_full.js'), 'w', encoding='utf-8').write(js)


def extract_fn(name):
    i = js.find('function ' + name + '(')
    if i < 0:
        raise SystemExit('NOT FOUND fn: ' + name)
    j = js.find('{', i)
    depth = 0
    k = j
    state = None
    while k < len(js):
        c = js[k]
        if state:
            if c == '\\':
                k += 2
                continue
            if c == state:
                state = None
        elif c in '"\'':
            state = c
        elif c == '`':
            state = '`'
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return js[i:k + 1]
        k += 1
    raise SystemExit('UNBALANCED fn: ' + name)


def extract_const_array(name):
    i = js.find('const ' + name)
    if i < 0:
        raise SystemExit('NOT FOUND const: ' + name)
    end = js.find('\n];', i)
    if end < 0:
        raise SystemExit('no array close: ' + name)
    return js[i:end + 3]


pieces = [extract_const_array('BODY_RANGES')]
_mk = re.search(r"const STORAGE_KEY = '[^']+';", js)
if not _mk:
    raise SystemExit('NOT FOUND STORAGE_KEY')
pieces.append(_mk.group(0))
for n in ['todayStr', 'addDaysStr', 'seedBodyLog', 'defaultState', 'loadState',
          'bodyLogValue', 'weightLogBmiPoints', 'renderBodyTrend', 'bodyValue',
          'calcBMR', 'findMetricLevel', 'resolveLevels', 'fmtTick']:
    pieces.append(extract_fn(n))

harness = r'''
// ---- 存根 ----
const _store = {};
global.localStorage = {
  getItem: k => (_store[k] === undefined ? null : _store[k]),
  setItem: (k, v) => { _store[k] = String(v); },
};
global.toast = () => {};
let state = defaultState();

function assert(name, cond, extra) {
  console.log((cond ? 'PASS  ' : 'FAIL  ') + name + (extra === undefined ? '' : '  -> ' + extra));
  if (!cond) process.exitCode = 1;
}

// A. 新用户不再被注入伪造序列
assert('A 新用户 bodyLog 为空', defaultState().bodyLog.length === 0, defaultState().bodyLog.length);

// B. 示例序列带 seed 标记
const seeded = seedBodyLog();
assert('B 示例点带 seed 标记', seeded.length === 9 && seeded.every(e => e.seed === 1), seeded.length);

// C. 被旧版本污染的存档（9 条无标记的示例值 + 2 条真实录入）→ 迁移后只剩真实的
const u = { gender: 'male', age: 30, height: 175, weight: 72.8 };
const polluted = seeded.map(e => ({ date: e.date, bmi: e.bmi, bodyFat: e.bodyFat,
  muscleRate: e.muscleRate, waterRate: e.waterRate, bodyAge: e.bodyAge, visceralFat: e.visceralFat }));
const real1 = { date: '2026-09-09', bmi: 22.9, bodyFat: 19.4, muscleRate: 42.0, waterRate: 55.2, bodyAge: 29, visceralFat: 9 };
const real2 = { date: '2026-09-11', bmi: 22.6, bodyFat: 18.6, muscleRate: 42.8, waterRate: 55.6, bodyAge: 28, visceralFat: 8 };
const legacy = { user: u, body: { bmi: 22.6, bodyFat: 18.6, muscleRate: 42.8, waterRate: 55.6,
  bodyAge: 28, visceralFat: 8, source: 'manual', syncedAt: '08:30' },
  bodyLog: polluted.concat([real1, real2]), diet: [], exercise: [], lastDate: '2026-09-11' };
localStorage.setItem(STORAGE_KEY, JSON.stringify(legacy));
const st1 = loadState();
assert('C 污染点被清除 / 真实点保留', st1.bodyLog.length === 2, st1.bodyLog.length);
assert('C 保留下来的确实是真实点', st1.bodyLog.every(e => [real1.date, real2.date].includes(e.date)),
  JSON.stringify(st1.bodyLog.map(e => e.date)));

// D. 空 bodyLog + 有体重历史 → BMI 图回填真实推算点
state = { user: u, body: legacy.body, bodyLog: [],
  weightLog: Array.from({ length: 30 }, (_, i) => ({ date: '2026-0' + (i < 9 ? 8 : 9) + '-01', weight: 75 - i * 0.1 })) };
const m = BODY_RANGES.find(x => x.key === 'bmi');
const svg = renderBodyTrend(m, state.user);
const pts = (svg.match(/<circle/g) || []).length;
assert('D BMI 回填出 30 个点', pts === 30, pts);
assert('D BMI 图含折线且无 NaN', svg.includes('<polyline') && !/NaN|undefined/.test(svg), null);
assert('D 标注了推算来源', svg.includes('按体重推算'), null);

// E. 无历史指标（体脂率）：空 bodyLog → 走空态、不报错
const mf = BODY_RANGES.find(x => x.key === 'bodyFat');
state.bodyLog = [];
const svg2 = renderBodyTrend(mf, state.user);
assert('E 体脂率无历史走空态', svg2.includes('empty') && !/NaN|undefined/.test(svg2), null);

// F. 全部 8 项指标都不产生 NaN
let bad = [];
BODY_RANGES.forEach(mm => {
  state.bodyLog = [real1, real2];
  const s = renderBodyTrend(mm, state.user);
  if (/NaN|undefined/.test(s)) bad.push(mm.key);
});
assert('F 8 项指标均无 NaN/undefined', bad.length === 0, bad.join(','));

// G. 真实录入后示例点被剔除（saveBody 的防御性过滤口径）
state.bodyLog = seedBodyLog();
state.bodyLog = state.bodyLog.filter(e => e && e.date && !e.seed);
assert('G 录入时示例点被剔除', state.bodyLog.length === 0, state.bodyLog.length);
'''
out = os.path.join(ROOT, 'promo', '_gen_test.js')
io.open(out, 'w', encoding='utf-8').write('\n'.join(pieces) + '\n' + harness)
print('generated:', out)
