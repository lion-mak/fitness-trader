/* ============================================================
 * mp_migrate_test.js —— 数据迁移层（lib/migrate.js + lib/store.js）单元测试
 *
 * 为什么要有这条测试：迁移是**唯一会一次性覆盖全部历史记录**的功能，
 * 出错就是数据全丢。所以这里不测「界面好不好看」，只测两件事：
 *   ① 数字对不对（体检、体积、条数）
 *   ② 出问题时**有没有把本机数据留下来**（回滚）
 *
 * 跑法：node promo/mp_migrate_test.js
 * 依赖：promo/mock.json（PWA 侧真实存档：96 天 / 388 饮食 / 88 运动 / 48 体重）
 *
 * ⚠️ mock 的 wx 必须是**同步 + 可注入故障**的（failWrite / dropDiet），
 *    否则「写入失败要回滚」这条根本测不出来 —— 单元测试的价值全在负控上。
 * ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');

const MINI = process.env.MINI_ROOT
  ? path.join(process.env.MINI_ROOT, 'miniprogram')
  : 'E:\\WeChatProjects\\jianpan\\miniprogram';
const MOCK = path.join(__dirname, 'mock.json');

let pass = 0, fail = 0;
const lines = [];
function log(s) { lines.push(s); }
function ok(name, cond, detail) {
  if (cond) { pass++; log('  \u2713 ' + name); }
  else { fail++; log('  \u2717 ' + name + (detail ? '  \u2192 ' + detail : '')); }
}
function eq(name, got, want) {
  ok(name, got === want, '期望 ' + JSON.stringify(want) + '，实际 ' + JSON.stringify(got));
}
function head(s) { log(''); log('=== ' + s + ' ==='); }

/* ---------- 可注入故障的 wx mock ---------- */
function makeWx(opts) {
  const o = opts || {};
  const storage = {};
  const calls = { modal: [], toast: [], clipboardWrite: null };
  const wx = {
    _storage: storage,
    _calls: calls,
    _opts: o,
    getStorageSync(k) { return (k in storage) ? storage[k] : ''; },
    setStorageSync(k, v) {
      if (o.failWrite) throw new Error('setStorageSync:fail exceed storage max size');
      let w = v;
      // 模拟「写进去了，但内容被静默截断」。用计数而不是布尔：
      // importPayload 内部会写两次（原值 + 净化值），要两次都坏才算坏；
      // 而回滚是第 3 次写，必须能成功，否则测的是「回滚也坏」而不是「回滚对不对」。
      if (o.dropDietTimes > 0) {
        o.dropDietTimes--;
        w = JSON.parse(JSON.stringify(v));
        w.diet = [];
      }
      storage[k] = w;
    },
    removeStorageSync(k) { delete storage[k]; },
    showModal(x) { calls.modal.push(x.title); if (x.success) x.success({ confirm: true }); },
    showToast(x) { calls.toast.push(x.title); },
    showLoading() {}, hideLoading() {},
    getClipboardData(x) {
      if (o.clipboardFail) { if (x.fail) x.fail({ errMsg: 'getClipboardData:fail mock' }); return; }
      if (x.success) x.success({ data: o.clipboard === undefined ? '' : o.clipboard });
    },
    setClipboardData(x) {
      if (o.clipboardFail) { if (x.fail) x.fail({ errMsg: 'setClipboardData:fail mock' }); return; }
      calls.clipboardWrite = x.data;
      if (x.success) x.success({});
    },
    chooseMessageFile(x) {
      if (o.cancelPick) { if (x.fail) x.fail({ errMsg: 'chooseMessageFile:fail cancel' }); return; }
      if (x.success) x.success({ tempFiles: [{ path: '/tmp/x.json', name: 'jianpan.json' }] });
    },
    getFileSystemManager() {
      return {
        readFile(x) { if (x.success) x.success({ data: o.fileText === undefined ? '' : o.fileText }); },
        writeFileSync() {},
      };
    },
    env: { USER_DATA_PATH: '/tmp' },
    shareFileMessage(x) { if (x.success) x.success({}); },
  };
  return wx;
}

/* 每次都要全新加载模块树：store.js 有模块级 state / saveWarned，
   复用缓存会让第 2 个用例读到第 1 个的状态。 */
function fresh(opts) {
  global.wx = makeWx(opts);
  Object.keys(require.cache).forEach(k => {
    if (k.indexOf('jianpan') >= 0 || k.indexOf('miniprogram') >= 0) delete require.cache[k];
  });
  const store = require(path.join(MINI, 'lib/store.js'));
  const migrate = require(path.join(MINI, 'lib/migrate.js'));
  const calc = require(path.join(MINI, 'lib/calc.js'));
  return { store, migrate, calc, wx: global.wx };
}

/* ---------- 读真实存档 ---------- */
let MOCK_STATE = null, MOCK_TEXT = null;
try {
  const j = JSON.parse(fs.readFileSync(MOCK, 'utf8'));
  MOCK_STATE = j.state;
  MOCK_TEXT = JSON.stringify({ __app: 'fitness-trader', __schema: 1, state: MOCK_STATE });
} catch (e) {
  console.error('读不到 promo/mock.json：' + e.message);
  process.exit(2);
}

/* ---------- 导入后的「成就补发额」——独立算，不调 progress.js ----------
 * importPayload 会**补判成就**（导入的是别处的历史，本机从没为它判过）⇒ 健康币 = 存档币 + 补发额。
 * 差额本身可以独立算出来：把「存档里没标 true、导入后标了 true」的成就挑出来，
 * 按 `ACHIEVEMENTS` 的 reward 求和 —— 只读数据表，不调被测实现（progress.sync）。
 * ⚠️ 别把 `eq(got.coins, MOCK_STATE.coins)` 改回写死的 10850：那样只能证明「今天恰好是这个数」；
 *    算出来的差额还能顺带管住「补发项集合是否变了」。
 * 📌 PWA 侧实测真值（playwright，见 promo/_probe_pwa_state.py）：同一份 mock 灌进 PWA
 *    ⇒ 8640 → **10850**、ach 真值 26 ⇒ 两端同值（补发额 2210）。 */
function achGain(calcMod, beforeAch, afterAch) {
  let sum = 0;
  Object.keys(afterAch || {}).forEach((k) => {
    if (afterAch[k] && !(beforeAch || {})[k]) {
      const a = calcMod.ACHIEVEMENTS.find((x) => x.id === k);
      if (a) sum += a.reward;
    }
  });
  return sum;
}
const PWA_COINS_AFTER_IMPORT = 10850;

log('数据迁移单元测试 —— lib/migrate.js / lib/store.js');
log('='.repeat(78));
log('工程：' + MINI);
log('样本：promo/mock.json（' + MOCK_STATE.diet.length + ' 饮食 / '
  + MOCK_STATE.exercise.length + ' 运动 / ' + MOCK_STATE.weightLog.length + ' 体重）');

/* 独立算期望值（不用被测代码自己的 survey，避免自证） */
const expectDates = new Set();
[MOCK_STATE.diet, MOCK_STATE.exercise, MOCK_STATE.weightLog].forEach(l =>
  l.forEach(r => { if (r && r.date) expectDates.add(r.date); }));
const EXPECT_DAYS = expectDates.size;

/* ============================================================
 * 1. 纯函数：体积与体检
 * ============================================================ */
head('1. 纯函数 —— 字节数与体检');
{
  const m = fresh().migrate;
  eq('utf8Bytes ASCII 1 字符 = 1 字节', m.utf8Bytes('abc'), 3);
  eq('utf8Bytes 中文 1 字符 = 3 字节', m.utf8Bytes('中'), 3);
  eq('utf8Bytes emoji（代理对）= 4 字节', m.utf8Bytes('\u{1F600}'), 4);
  eq('utf8Bytes 混合串', m.utf8Bytes('a中\u{1F600}'), 1 + 3 + 4);
  eq('bytesOf 与 Buffer.byteLength 同口径',
    m.bytesOf(MOCK_STATE), Buffer.byteLength(JSON.stringify(MOCK_STATE), 'utf8'));

  const sv = m.survey(MOCK_STATE);
  eq('体检 · 饮食条数', sv.diet, MOCK_STATE.diet.length);
  eq('体检 · 运动条数', sv.exercise, MOCK_STATE.exercise.length);
  eq('体检 · 体重条数', sv.weight, MOCK_STATE.weightLog.length);
  eq('体检 · 记录天数（独立实现对照）', sv.days, EXPECT_DAYS);
  ok('体检 · 跨度起止都非空', !!sv.from && !!sv.to, sv.from + ' ~ ' + sv.to);
  ok('体检 · 跨度顺序正确', sv.from <= sv.to, sv.from + ' > ' + sv.to);
  eq('体检 · 体积 KB 与字节数自洽', sv.kb, Math.round(sv.bytes / 102.4) / 10);
  ok('体检 · 体积在 1 MB 上限的 15% 以内（真实存档实测 ~108 KB）',
    sv.bytes < 153600, sv.kb + ' KB');

  log('     实际体检：' + m.summary(sv));
  log('     存档体积：' + sv.kb + ' KB  段位：' + sv.rank + ' Lv' + sv.level);
  eq('摘要 · 空存档措辞', m.summary({ days: 0 }), '空存档（无任何记录）');
  ok('摘要 · 含天数与条数', m.summary(sv).indexOf(String(sv.days) + ' 天') === 0);
}

/* ============================================================
 * 2. 解析：正控
 * ============================================================ */
head('2. 解析 —— 正控（这些都必须成功）');
{
  const m = fresh().migrate;
  const a = m.parse(MOCK_TEXT);
  eq('完整存档（带 __app/__schema）解析出 state', a.diet.length, MOCK_STATE.diet.length);

  const b = m.parse(JSON.stringify(MOCK_STATE));
  eq('裸 state（无元信息，视为 __schema=0）也能解析', b.exercise.length, MOCK_STATE.exercise.length);

  const c = m.parse('\uFEFF' + MOCK_TEXT);
  eq('带 BOM 前缀（记事本另存）能解析', c.diet.length, MOCK_STATE.diet.length);

  // PWA「导出备份」写出的 .json 文件 = pretty JSON（带缩进）+ __app 元信息
  const d = m.parse('  \n\t' + JSON.stringify({
    __app: 'fitness-trader', __schema: 1, __exportedAt: '2026-09-11T00:00:00.000Z',
    __appVersion: '2.7.56', state: MOCK_STATE,
  }, null, 2) + '\n  ');
  eq('格式化 JSON（带缩进/换行，即 .json 文件内容）能解析', d.diet.length, MOCK_STATE.diet.length);

  const e = m.parse(JSON.stringify({ __app: 'fitness-trader', __schema: 0, state: { diet: [] } }));
  ok('__schema=0 且只有 diet 的极简存档放行', !!e);
}

/* ============================================================
 * 3. 解析：负控（每一条都必须被拦下，且错误要说得出原因）
 * ============================================================ */
head('3. 解析 —— 负控（这些必须被拦下）');
function mustThrow(name, fn, keyword) {
  try {
    fn();
    fail++; log('  \u2717 ' + name + '  \u2192 竟然没抛错！');
  } catch (e) {
    const msg = (e && e.message) || '';
    const hit = !keyword || msg.indexOf(keyword) >= 0;
    if (hit) { pass++; log('  \u2713 ' + name + '  \u2192 「' + msg.slice(0, 60) + '」'); }
    else { fail++; log('  \u2717 ' + name + '  \u2192 抛了错但措辞不含「' + keyword + '」：' + msg.slice(0, 80)); }
  }
}
{
  const m = fresh().migrate;
  mustThrow('空文本被拦下', () => m.parse(''), '内容为空');
  mustThrow('纯空白被拦下', () => m.parse('   \n  '), '内容为空');
  mustThrow('null 被拦下', () => m.parse(null), '内容为空');
  mustThrow('坏 JSON 被拦下', () => m.parse('{"diet":[}'), '不是合法的 JSON');
  mustThrow('被聊天软件截断的 JSON 被拦下',
    () => m.parse(MOCK_TEXT.slice(0, Math.floor(MOCK_TEXT.length * 0.6))), '不是合法的 JSON');
  // ⚠️ 数组是 calc.migratePayload 的漏洞（Array 的 typeof 也是 object），migrate.parse 必须补严
  mustThrow('数组 [] 被拦下（migratePayload 会放行，parse 不能）', () => m.parse('[]'), '格式不正确');
  mustThrow('数组 [1,2] 被拦下', () => m.parse('[1,2]'), '格式不正确');
  mustThrow('字符串字面量被拦下', () => m.parse('"hello"'), '格式不正确');
  mustThrow('数字被拦下', () => m.parse('123'), '格式不正确');
  mustThrow('空对象 {} 被拦下（不能「导入成功但什么都没进来」）',
    () => m.parse('{}'), '没有任何已知字段');
  mustThrow('无关对象 {"foo":1} 被拦下', () => m.parse('{"foo":1}'), '没有任何已知字段');
  mustThrow('选错文件（别的 App 的 JSON）被拦下',
    () => m.parse('{"name":"张三","phone":"13800000000"}'), '没有任何已知字段');
  mustThrow('更高 __schema 被拒绝', () => m.parse(JSON.stringify({
    __app: 'fitness-trader', __schema: 99, state: MOCK_STATE,
  })), '更高版本');
  // 裸壳 {state:{...}}：PWA 从不产出这种格式（裸存档就是 state 本身，不是套一层 state）
  mustThrow('只套了一层 state 的裸壳被拦下（不是本应用的存档格式）',
    () => m.parse(JSON.stringify({ state: MOCK_STATE })), '没有任何已知字段');
}

/* ============================================================
 * 4. 体积闸
 * ============================================================ */
head('4. 体积闸 —— 小程序 storage 单键 1 MB，超了必须提前拦');
{
  const ctx = fresh();
  const m = ctx.migrate;
  eq('安全线 = 900 KB', m.SAFE_BYTES, 900 * 1024);
  eq('微信硬上限 = 1 MB', m.LIMIT_BYTES, 1024 * 1024);

  // 造一份 >900 KB 的存档：每条 ~80 字节，约 12000 条
  const big = { diet: [] };
  const pad = '超长食物名称占位符'.repeat(4);
  for (let i = 0; i < 12000; i++) big.diet.push({ date: '2026-01-01', name: pad, kcal: 100 });
  const bigBytes = m.bytesOf(big);
  ok('构造的超大存档确实 > 900 KB（' + m.kb(bigBytes) + ' KB）', bigBytes > m.SAFE_BYTES);

  ctx.store.init();
  const beforeRaw = JSON.stringify(ctx.store.snapshotRaw());
  mustThrow('超大存档被体积闸拦下', () => m.applyImport(big), '超过小程序单机可存上限');
  eq('体积闸拦下后**没有**动本机存储',
    JSON.stringify(ctx.store.snapshotRaw()), beforeRaw);
}

/* ============================================================
 * 5. 真实导入（正控）—— 这是用户马上要走的路径
 * ============================================================ */
head('5. 真实导入 —— 用 PWA 真实存档走完整链路');
{
  const ctx = fresh();
  const { store, migrate } = ctx;
  store.init();
  eq('导入前本机是空存档（饮食 0 笔）', migrate.survey(store.get()).diet, 0);

  const data = migrate.parse(MOCK_TEXT);
  const got = migrate.applyImport(data);

  eq('导入后 · 饮食条数 = 388', got.diet, MOCK_STATE.diet.length);
  eq('导入后 · 运动条数 = 88', got.exercise, MOCK_STATE.exercise.length);
  eq('导入后 · 体重条数 = 48', got.weight, MOCK_STATE.weightLog.length);
  eq('导入后 · 天数（独立实现对照）', got.days, EXPECT_DAYS);
  const gain = achGain(ctx.calc, MOCK_STATE.ach, store.get().ach);
  eq('导入后 · 健康币 = 存档 ' + MOCK_STATE.coins + ' + 成就补发 ' + gain,
    got.coins, MOCK_STATE.coins + gain);
  eq('导入后 · 补发额与 PWA 实测一致（' + PWA_COINS_AFTER_IMPORT + '）',
    got.coins, PWA_COINS_AFTER_IMPORT);
  eq('导入后 · 段位（exp ' + MOCK_STATE.exp + ' → Lv'
    + (Math.floor(MOCK_STATE.exp / 100) + 1) + '）', got.rank,
    (function () {
      const lv = Math.floor(MOCK_STATE.exp / 100) + 1;
      const R = require(path.join(MINI, 'lib/calc.js')).RANKS;
      let r = R[0]; R.forEach(x => { if (lv >= x.minLv) r = x; }); return r.name;
    })());

  // 落盘了吗（不是只在内存里）
  const onDisk = store.snapshotRaw();
  eq('storage 落盘 · 饮食条数', onDisk.diet.length, MOCK_STATE.diet.length);
  eq('storage 落盘 · 运动条数', onDisk.exercise.length, MOCK_STATE.exercise.length);

  // 净化链有没有跑到（导入的数据要走和冷启动一样的兜底）
  ok('净化链已跑 · coinDate 归一为今天（跨天重置生效）',
    store.get().coinDate === require(path.join(MINI, 'lib/calc.js')).todayStr(),
    'coinDate=' + store.get().coinDate);
  ok('净化链已跑 · lastDate 归一为今天', store.get().lastDate === require(path.join(MINI, 'lib/calc.js')).todayStr());
  ok('净化链已跑 · 老记录都补上了 date',
    store.get().diet.every(d => !!d.date));
  ok('净化链已跑 · kcal 已取整',
    store.get().diet.every(d => typeof d.kcal === 'number' && d.kcal === Math.round(d.kcal)));
  ok('用户档案跟着进来了（体重 ' + (store.get().user && store.get().user.weight) + ' kg）',
    !!(store.get().user && store.get().user.weight));

  // 替换语义：本机的旧记录不能残留在里面
  const oldLeftover = store.get().diet.filter(d => d.__fromOld !== undefined).length;
  eq('本机旧数据未混入（替换语义生效）', oldLeftover, 0);
}

/* ============================================================
 * 6. 替换语义 vs 合并语义（用「本机已有数据」验证）
 * ============================================================ */
head('6. 替换语义 —— 本机有数据时导入，结果只由存档决定');
{
  const ctx = fresh();
  const { store, migrate } = ctx;
  store.init();
  // 先让本机有一批「脏」记录 + 一个自定义常吃
  const s = store.get();
  s.diet.push({ date: '2026-09-20', name: '本机脏数据A', kcal: 111 });
  s.diet.push({ date: '2026-09-21', name: '本机脏数据B', kcal: 222 });
  s.usuals.push({ name: '本机常吃', cat: '主食', kcal: 100 });
  s.coins = 99999;
  store.save();

  eq('导入前本机饮食 2 笔', migrate.survey(store.get()).diet, 2);
  const got = migrate.applyImport(migrate.parse(MOCK_TEXT));
  eq('导入后饮食 = 存档的 388 笔（不是 390）', got.diet, MOCK_STATE.diet.length);
  /* ⚠️ 「不是本机 99999」这条不变（那才是本测试的意图）；
     但「= 存档的 8640」不再成立 —— 导入会补判成就（见 achGain 注释）。 */
  eq('导入后健康币 ≠ 本机 99999（本机余额没残留）', got.coins !== 99999, true);
  eq('导入后健康币 = 存档 ' + MOCK_STATE.coins + ' + 成就补发 '
    + achGain(ctx.calc, MOCK_STATE.ach, store.get().ach),
    got.coins, MOCK_STATE.coins + achGain(ctx.calc, MOCK_STATE.ach, store.get().ach));
  eq('本机自定义常吃未残留', (store.get().usuals || []).filter(u => u.name === '本机常吃').length, 0);
  eq('本机脏数据未残留', (store.get().diet || []).filter(d => /本机脏数据/.test(d.name)).length, 0);
}

/* ============================================================
 * 7. 写入失败必须回滚（🔴 本次最关键的数据安全测试）
 * ============================================================ */
head('7. 写入失败 → 必须回滚，本机数据一条不能少');
{
  const ctx = fresh();
  const { store, migrate } = ctx;
  store.init();
  const s = store.get();
  s.diet.push({ date: '2026-09-20', name: '唯一的宝贵记录', kcal: 500 });
  s.coins = 1234;
  store.save();
  /* ⚠️ 基线取在 save() **之后**：save() 会顺带补判成就并发币（那条饮食记录已满足 leek/tryorder），
     1234 会变成 1234+140。「回滚」要保证的是**回到导入前的那一刻**，不是回到某个写死的数字；
     下一条「与导入前逐字节一致」才是真正的主断言。 */
  const coinsBeforeImport = store.get().coins;
  const beforeText = JSON.stringify(store.snapshotRaw());

  // 让下一次 setStorageSync 抛错（模拟存储配额满）
  ctx.wx.setStorageSync = () => { throw new Error('setStorageSync:fail exceed storage max size'); };

  mustThrow('写入失败时 importPayload 抛错', () => {
    migrate.applyImport(migrate.parse(MOCK_TEXT));
  }, '写入本地存储失败');

  // 回滚验证：把 setStorageSync 恢复正常后读回
  ctx.wx.setStorageSync = function (k, v) { ctx.wx._storage[k] = v; };
  const after = store.snapshotRaw();
  eq('回滚后本机饮食仍是 1 笔', (after.diet || []).length, 1);
  eq('回滚后那条宝贵记录还在', (after.diet || [])[0].name, '唯一的宝贵记录');
  eq('回滚后健康币仍是导入前的 ' + coinsBeforeImport, after.coins, coinsBeforeImport);
  eq('回滚后 storage 与导入前逐字节一致', JSON.stringify(after), beforeText);
}

/* ============================================================
 * 8. 回读校验：写入「静默丢数据」也要能发现并回滚
 * ============================================================ */
head('8. 回读校验 —— 写入静默丢数据时发现并回滚');
{
  const ctx = fresh();
  const { store, migrate } = ctx;
  store.init();
  const s = store.get();
  s.diet.push({ date: '2026-09-20', name: '导入前的记录', kcal: 300 });
  store.save();

  // 模拟「写进去了，但内容被静默截断」：不抛错，只把 diet 清空。
  // 设 2 次 —— importPayload 内部写两次（原值 + 净化值），两次都坏才算真的写坏；
  // 第 3 次是回滚写，必须成功，这样测的才是「回滚对不对」而不是「回滚也坏」。
  ctx.wx._opts.dropDietTimes = 2;

  mustThrow('回读校验发现条数不符并抛错', () => {
    migrate.applyImport(migrate.parse(MOCK_TEXT));
  }, '写入校验失败');

  eq('注入的 2 次截断已用尽（回滚那次是正常写入）', ctx.wx._opts.dropDietTimes, 0);
  const after = store.snapshotRaw();
  eq('校验失败后已回滚（那条记录还在）', (after.diet || []).length, 1);
  eq('回滚内容正确', (after.diet || [])[0].name, '导入前的记录');
}

/* ============================================================
 * 9. 剪贴板 / 文件通道
 * ============================================================ */
head('9. 通道 —— 剪贴板与聊天文件');
const pending = [];
{
  const ctx = fresh({ clipboard: MOCK_TEXT });
  const { store, migrate } = ctx;
  store.init();
  pending.push(migrate.importFromClipboard().then(r => {
    eq('剪贴板通道 · 解析出饮食条数', r.sv.diet, MOCK_STATE.diet.length);
    eq('剪贴板通道 · 来源标记', r.src, '剪贴板');
  }).catch(e => { fail++; log('  \u2717 剪贴板通道抛错：' + e.message); }));
}
{
  const ctx = fresh({ clipboard: '' });
  const migrate = ctx.migrate;
  pending.push(migrate.importFromClipboard().then(() => {
    fail++; log('  \u2717 空剪贴板竟然没抛错');
  }).catch(e => {
    pass++; log('  \u2713 空剪贴板被拦下  \u2192 「' + e.message.slice(0, 44) + '」');
  }));
}
{
  const ctx = fresh({ clipboard: '这不是迁移码，是从聊天里复制的一句话' });
  const migrate = ctx.migrate;
  pending.push(migrate.importFromClipboard().then(() => {
    fail++; log('  \u2717 垃圾剪贴板竟然没抛错');
  }).catch(e => {
    pass++; log('  \u2713 剪贴板里是普通聊天文本被拦下  \u2192 「' + e.message.slice(0, 40) + '」');
  }));
}
{
  const ctx = fresh({ fileText: '\uFEFF' + MOCK_TEXT });
  const migrate = ctx.migrate;
  pending.push(migrate.importFromFile().then(r => {
    eq('聊天文件通道 · 解析出饮食条数', r.sv.diet, MOCK_STATE.diet.length);
    eq('聊天文件通道 · 来源是文件名', r.src, 'jianpan.json');
  }).catch(e => { fail++; log('  \u2717 文件通道抛错：' + e.message); }));
}
{
  const ctx = fresh({ cancelPick: true });
  const migrate = ctx.migrate;
  pending.push(migrate.importFromFile().then(() => {
    fail++; log('  \u2717 取消选文件竟然没抛错');
  }).catch(e => {
    ok('用户取消选文件时报可识别的 __CANCEL__（UI 可静默忽略）',
      e.message === '__CANCEL__', e.message);
  }));
}
{
  const ctx = fresh();
  const migrate = ctx.migrate;
  ctx.store.init();
  // 先灌入真实存档再导出 —— 这才代表用户实际会复制的迁移码体积
  migrate.applyImport(migrate.parse(MOCK_TEXT));
  pending.push(migrate.exportToClipboard().then(r => {
    ok('导出迁移码 · 全量体积落在 ~109 KB（实测真实存档）',
      r.kb > 90 && r.kb < 140, r.kb + ' KB');
    const back = JSON.parse(ctx.wx._calls.clipboardWrite);
    eq('导出内容带 __app 标记', back.__app, 'fitness-trader');
    eq('导出内容带 __schema 版本', back.__schema, 1);
    eq('导出的 state 饮食条数 = 388', back.state.diet.length, MOCK_STATE.diet.length);
    // 反向：小程序导出的迁移码必须能被 parse 读回（将来迁回 PWA 靠这条）
    const again = migrate.parse(ctx.wx._calls.clipboardWrite);
    eq('小程序导出的迁移码可被反向解析', again.exercise.length, MOCK_STATE.exercise.length);
  }).catch(e => { fail++; log('  \u2717 导出抛错：' + e.message); }));
}

/* ============================================================
 * 10. 往返一致性：导出 → 导入 → 数据不漂移
 * ============================================================ */
head('10. 往返一致性 —— 导入后导出，条数与内容不漂移');
{
  const ctx = fresh();
  const { store, migrate } = ctx;
  store.init();
  migrate.applyImport(migrate.parse(MOCK_TEXT));

  const p1 = store.exportPayload();
  const r1 = migrate.survey(p1.state);
  eq('导出 · 饮食条数', r1.diet, MOCK_STATE.diet.length);
  eq('导出 · 运动条数', r1.exercise, MOCK_STATE.exercise.length);
  eq('导出 · 体重条数', r1.weight, MOCK_STATE.weightLog.length);
  eq('导出 · 健康币 = 导入后的值（含成就补发）',
    r1.coins, MOCK_STATE.coins + achGain(ctx.calc, MOCK_STATE.ach, store.get().ach));
  eq('导出 · 段位', r1.rank, migrate.survey(MOCK_STATE).rank);

  // 再把导出的东西导回去，条数必须不变（幂等）
  // ⚠️ 必须经 parse()：applyImport 只吃「已解析的 state」，直接喂 payload 会被防线拦下
  const got = migrate.applyImport(migrate.parse(JSON.stringify(store.exportPayload())));
  eq('二次导入 · 饮食条数不漂移', got.diet, MOCK_STATE.diet.length);
  eq('二次导入 · 运动条数不漂移', got.exercise, MOCK_STATE.exercise.length);
  eq('二次导入 · 体重条数不漂移', got.weight, MOCK_STATE.weightLog.length);

  // 防的就是「传错参数 → 静默导入 0 条 → 本机记录被清空」
  mustThrow('把未解析的 payload 直接喂给 applyImport 会被拦下',
    () => migrate.applyImport(store.exportPayload()), '不是 state');
  eq('被拦下后本机记录一条没少', migrate.survey(store.get()).diet, MOCK_STATE.diet.length);

  // 逐字节比对：字段内容不能因为往返而改变
  const same = JSON.stringify(store.get().diet) === JSON.stringify(store.get().diet);
  ok('二次导入后 diet 内容稳定', same);
}

/* ============================================================
 * 12. 自建食物的行李位 —— 导出/导入必须把它一起搬
 *
 * 起因（2026-09-24 Mak 真机反馈）：「json 导出的存档里为何没有自建的食物？」
 * 根因：自建食物存在**另一个 storage 键**（jianpan_custom_foods_v1，见 lib/food-store.js），
 *       而 calc.buildExportPayload() 只装 state ⇒ 导出的 JSON 天然不含它，换机就丢。
 * 修法：在 PWA 的 payload 之上补一个顶层 customFoods 行李位（不改 PWA 内核）。
 *
 * 🔴 本节最要紧的一条不是「能搬」，而是**「没带 ≠ 空」**：
 *    PWA 导出的存档里根本没有 customFoods 这个键。若把它当成「空数组」去替换，
 *    用户导入一份 App 备份就会当场清空本机所有自建食物 —— 且全程无报错。
 * ============================================================ */
head('12. 自建食物 —— 导出/导入行李位（含「没带 ≠ 空」）');
/* 解析兼容口：parse() 只回 state（历史语义，不能改），parsePayload() 才带行李位。
   本节要用的是后者，包一层省得每处都写 parsePayload(...).data。 */
function parse12(migrate, text) { return migrate.parsePayload(text); }
const pending2 = [];
{
  const ctx = fresh();
  const { store, migrate } = ctx;
  store.init();
  /* A 机先有真实历史：else 往返一趟两边都是空表，「state 也跟着搬」就成了同义反复 */
  migrate.applyImport(migrate.parse(MOCK_TEXT));
  const FoodStore = require(path.join(MINI, 'lib/food-store.js'));
  /* ⚠️ 必须先 load()：rebuild() 是「自建 + 库里已有的」重排，
     而 foods 要 load()/applyData() 之后才有内容。顺序颠倒不会报错，
     但 rebuild 出来的索引里只有自建食物 —— 「存档搬来了但搜不到」这类断言会失真。 */
  FoodStore.load();

  /* 造两条自建食物。
     ⚠️ py / ini 必须是**字符串**（food-store.buildIndex 会对 f.py 直接调 .replace）——
        写成数字会让 rebuild 抛 TypeError，而那条异常会把整个导入流程打断。 */
  const myFoods = [
    { name: '自制蛋白奶昔', kcal: 310, unit: 'ml', gram: 350, py: 'zzdbnx', ini: 'ZZDBNX', src: 'custom' },
    { name: '妈妈牌红烧肉', kcal: 540, unit: 'g', gram: 200, py: 'm mphsr', ini: 'MMPHSR', src: 'custom' },
  ];
  FoodStore.saveCustom(myFoods);
  FoodStore.rebuild();
  eq('前提 · 本机有 2 条自建食物', FoodStore.loadCustom().length, 2);

  /* ---- 纯函数：键存在性就是口径 ---- */
  const pwaBackup = { __app: 'fitness-trader', __schema: 1, state: MOCK_STATE };
  ok('PWA 备份（没有 customFoods 键）⇒ present=false，一个字节都不动本机',
    migrate.customFoodsOf(pwaBackup).present === false);
  const withEmpty = { __app: 'fitness-trader', __schema: 1, state: MOCK_STATE, customFoods: [] };
  ok('明确带了空数组 ⇒ present=true（这是「这台机器就是 0 条」的权威口径）',
    migrate.customFoodsOf(withEmpty).present === true
    && migrate.customFoodsOf(withEmpty).list.length === 0);
  const nullv = { customFoods: null };
  ok('键在但值是 null ⇒ present=true / list=[]（不是「没带」）',
    migrate.customFoodsOf(nullv).present === true && migrate.customFoodsOf(nullv).list.length === 0);
  const notArr = { customFoods: 'oops' };
  ok('键在但不是数组 ⇒ present=false（形态不对就别拿它去覆盖本机）',
    migrate.customFoodsOf(notArr).present === false);
  const dirty = { customFoods: [{ name: '好的' }, { name: '  ' }, null, 'x', { nope: 1 }] };
  ok('脏条目被滤掉（只留名字非空的）',
    migrate.customFoodsOf(dirty).present === true && migrate.customFoodsOf(dirty).list.length === 1);

  /* ---- 导出必须带上行李位（0 条也要带） ---- */
  const payload = migrate.buildExportPayload();
  ok('导出 payload 带 customFoods 键', Object.prototype.hasOwnProperty.call(payload, 'customFoods'));
  eq('导出的自建食物条数', payload.customFoods.length, 2);
  eq('导出的 state 与 PWA payload 同源（没被改动）',
    payload.state.diet.length, store.exportPayload().state.diet.length);

  /* ---- 负控：清空自建食物后导出，仍然必须有这个键（空就是 []） ---- */
  FoodStore.saveCustom([]);
  FoodStore.rebuild();
  const p0 = migrate.buildExportPayload();
  ok('0 条自建食物时仍照写 customFoods:[]（写成「不带」会把本机旧食物保下来 ⇒ 不是还原）',
    Object.prototype.hasOwnProperty.call(p0, 'customFoods') && p0.customFoods.length === 0);
  FoodStore.saveCustom(myFoods);
  FoodStore.rebuild();

  /* ---- 往返：A 机导出 → B 机导入，自建食物必须跟过去 ---- */
  const text = JSON.stringify(migrate.buildExportPayload());
  const ctxB = fresh();
  ctxB.store.init();
  const FoodStoreB = require(path.join(MINI, 'lib/food-store.js'));
  FoodStoreB.load();
  eq('B 机初始没有自建食物', FoodStoreB.loadCustom().length, 0);
  ok('B 机食物库已装载（不是空索引 —— 否则「搜得到」是白送的）',
    FoodStoreB.all().length > 1000, FoodStoreB.all().length + ' 条');

  const r = parse12(ctxB.migrate, text);
  ok('解析出的行李位 present=true', r.customFoods.present === true);
  eq('解析出的自建食物条数', r.customFoods.list.length, 2);
  const got = ctxB.migrate.applyImport(r.data, r.customFoods);
  eq('导入后 B 机的自建食物条数', FoodStoreB.loadCustom().length, 2);
  eq('import 返回值里带上条数（UI 靠它区分「搬了 0 条」与「没搬」）', got.customFoods, 2);
  eq('名字一起搬过来了', FoodStoreB.loadCustom()[1].name, '妈妈牌红烧肉');
  eq('state 也一起到位（不是只搬了食物）', got.diet, MOCK_STATE.diet.length);

  /* 重建索引后自建食物真的能被搜到（只写 storage 不 rebuild ⇒ 存了但搜不到，
     而「搜不到」正是用户会当成「迁移失败」的那种症状） */
  const names = FoodStoreB.all().map((f) => f.name);
  ok('rebuild 后自建食物进入运行索引（不是只躺在 storage 里）',
    names.indexOf('妈妈牌红烧肉') >= 0, '索引里 ' + names.length + ' 条');
  const hits = FoodStoreB.search('妈妈牌红烧肉');
  ok('走应用的检索入口能搜到它（口径与真机一致）',
    hits.length > 0 && hits[0].name === '妈妈牌红烧肉',
    '搜到 ' + hits.length + ' 条' + (hits[0] ? '，首条 ' + hits[0].name : ''));
  ok('自建食物带 src=custom 标记（否则「我的常吃/自建」分不出来）',
    (hits[0] || {}).src === 'custom', (hits[0] || {}).src);

  /* ---- 反向：PWA 备份导进来 ⇒ 本机自建食物一条不少 ---- */
  ctxB.migrate.applyImport(parse12(ctxB.migrate, MOCK_TEXT).data,
    parse12(ctxB.migrate, MOCK_TEXT).customFoods);
  eq('导入 PWA 备份后自建食物一条没少（「没带」不覆盖本机）', FoodStoreB.loadCustom().length, 2);

  /* ---- 负控：明确带空数组导进来 ⇒ 本机自建食物必须被清空 ---- */
  const emptyPack = JSON.parse(MOCK_TEXT);
  emptyPack.customFoods = [];
  ctxB.migrate.applyImport(parse12(ctxB.migrate, JSON.stringify(emptyPack)).data, { present: true, list: [] });
  eq('负控 · 明确带 0 条 ⇒ 本机被清成 0（证明 present=true 确实是「替换」权威口径）',
    FoodStoreB.loadCustom().length, 0);
}
{
  /* ---- 回滚联动：state 写失败时自建食物必须跟着回到导入前 ---- */
  const ctx = fresh({ failWrite: true });
  const { store, migrate } = ctx;
  const FoodStore = require(path.join(MINI, 'lib/food-store.js'));
  store.init();
  /* failWrite 下写盘一律抛错，所以本机「原有的」1 条只能直接塞进 mock storage */
  ctx.wx._storage['jianpan_custom_foods_v1'] = [{ name: '本机原有的', kcal: 100 }];

  let threw = null;
  try {
    migrate.applyImport(migrate.parse(MOCK_TEXT), { present: true, list: [{ name: '别家的', kcal: 200 }, { name: '也别家的', kcal: 300 }] });
  } catch (e) { threw = e; }
  ok('写出错时抛错（不是静默失败）', !!threw, threw && threw.message.slice(0, 40));
  eq('回滚后自建食物仍是本机原来那 1 条（两部分一起回滚，不是只还 state）',
    FoodStore.loadCustom().length, 1);
  eq('回滚后那 1 条还是原件', FoodStore.loadCustom()[0].name, '本机原有的');
}

/* ============================================================
 * 11. 边界：foodLog 之类的未知多余字段不能搞崩
 * ============================================================ */
head('11. 边界 —— 存档带多余/未知字段');
{
  const ctx = fresh();
  const { store, migrate } = ctx;
  store.init();
  const odd = JSON.parse(JSON.stringify(MOCK_STATE));
  odd.unknownFutureField = { a: 1, b: [1, 2, 3] };
  odd.bodyLog = [];
  const got = migrate.applyImport(odd);
  eq('带未知字段的存档能导入', got.diet, MOCK_STATE.diet.length);
  ok('未知字段被保留（不丢用户数据）', store.get().unknownFutureField !== undefined);
}

/* ---------- 收尾 ---------- */
Promise.all(pending).then(() => {
  log('');
  log('='.repeat(78));
  log('通过 ' + pass + ' 项 / 失败 ' + fail + ' 项');
  log('');
  log('RESULT=' + (fail === 0 ? 'OK' : 'FAIL'));
  const text = lines.join('\n');
  console.log(text);
  fs.writeFileSync(path.join(__dirname, '_migrate_test_out.txt'), text + '\n', 'utf8');
  process.exit(fail === 0 ? 0 : 1);
}).catch(e => {
  console.error('测试脚本自身异常：' + (e && e.stack));
  process.exit(3);
});
