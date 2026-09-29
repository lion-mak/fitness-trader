# 成就徽章 · 像素搞怪版 · 生图提示词（v1）

> 30 个成就图标：从「24×24 单色矢量剪影」换成「像素搞怪徽章」。
> 风格宇宙与段位卡同一套（惨 / 土 / 疯，**不要可爱**），但尺寸约束完全不同 —— 见第 1 节，先读它。
> 本文件由 `promo/make_ach_prompts.py` 生成（成就名/条件直读 `index.html`，⛔ 不要手改本文件）。

---

## 1. ⚠️ 生图前必须先定的一件事：显示尺寸

现量数据（不是估的）：

| 位置 | 容器 | 图标渲染尺寸 | 出处 |
|---|---|---|---|
| 成就格 `.badge .b` | 48×48 圆角块 | **26×26** | `achievements.wxss` / 两端口径一致 |
| 分类头 `.ach-cat-ic` | 34×34 块 | **20×20** | 同上 |
| 近期目标 `.prog-row .ic` | — | **26×26** | 同上 |

**问题**：26px 只够承载一个单色剪影。像素搞怪的「傻表情 + 一处惨细节」在 26px 下会糊成一坨 ——
这正是段位卡的镜像反例（那边是 122×171 大图，像素风成立；这边 26px，像素风不成立）。

**建议（配套改动，极小）**：

| 项 | 现在 | 改成 | 依据 |
|---|---|---|---|
| `.badge .b` 方块 | 48×48 | **64×64** | 三列网格列宽 (430−28−20)/3 ≈ **127px**，方块去掉 `.badge` 左右 padding 16 后可用 **111px**，64 绰绰有余 |
| 图标 `ic-img` | 26×26 | **44×44** | 44px 下「22 像素块横跨」= 每块 2px，清晰可辨 |

**本文档全部提示词按「缩到 44px 可辨」写**。若坚持保留 26px，提示词要再砍（只留一个形状、去掉表情），
请说一声我另出一版。

---

## 2. 出图规格

| 项 | 值 | 说明 |
|---|---|---|
| 尺寸 | **512×512** | 44px 显示 = 11.6 倍图，超采样远够 |
| 格式 | PNG | 不要 JPG（描边会糊） |
| 背景 | **纯洋红 `#FF00FF`** | ⛔ 不要传 `background=transparent`（不生效，会被渲染成棋盘格） |
| 抠图判据 | `R>140 & G<125 & R−G>70 & B−G>15` | 一次抠净，不羽化（像素画羽化即毁） |
| 主体占比 | 画布 **78~84%** | 四周留均匀洋红边，抠完正好贴进方块 |
| 命名 | `ach-<代号>.png` | 代号见下表，与代码里的 `icon` 字段**逐字一致** |

**⚠️ 图是我们抠成透明底的**，不是自带底板的徽章 —— 底色由页面的 `.b` 提供（已解锁=分类色，未解锁=灰+`opacity:.35`）。
所以每张图必须有**极厚近黑描边**，贴在彩色底上才不糊。

---

## 3. 通用前缀（30 张一字不改）

```
Goofy low-res pixel art game badge, one single chunky object or creature, weird and ridiculous, absurd lopsided proportions, one comic face with an exaggerated expression, chunky pixels, big square pixel blocks, roughly 22 pixel blocks across the canvas, extra thick near-black outline on every shape, flat solid color blocks with light dithering, hard pixel edges, no gradients, no anti-aliasing, no blur, limited 8-color palette, very high contrast, big bold simple silhouette filling 80% of the frame, centered, at most 3 large shapes, no fine detail, no thin lines, no tiny texture, no small decoration, stays instantly readable when shrunk to 44px, flat solid magenta background #FF00FF edge to edge, even margin around the subject, no text, no letters, no numbers, no watermark, no signature, no frame, no border, no ground shadow, no drop shadow, no scenery, no background pattern, no cute, no kawaii, no chibi, no glossy shine, no sparkly eyes, no pastel colors, no mascot style. Subject:
```

四行不是装饰：

- `chunky pixels, roughly 22 pixel blocks across` —— 把「低分辨率」翻译成模型能执行的量化约束。
  不写这句，模型会给 512px 的精细插画，缩到 44px 直接糊。
- `at most 3 large shapes, no fine detail, no small decoration` —— 44px 的硬约束前置到提示词，
  逼模型砍掉小尺寸必糊的碎细节。
- `stays instantly readable when shrunk to 44px` —— 把最终显示尺寸写进提示词（段位卡同套路，那句是 `130px`）。
- `flat solid magenta background #FF00FF` + `no cute, no kawaii, no chibi, no sparkly eyes, no pastel` ——
  洋红一次抠净；**反向约束必须写**，不写模型必滑回可爱吉祥物（段位卡上一版就是这么翻车的）。

---

## 4. 30 条画面描述（每张只换 `Subject:` 后面这一段）

### 持仓与套牢（减脂战绩 · K线人生）· 5 个

| # | 代号 | 成就名 | 解锁条件 | 画面要点 |
|---|---|---|---|---|
| 1 | `leek` | 韭菜入场 | 达到 1 次 | 记下人生第一笔 |
| 2 | `untie` | 解套成功 | 达到 1kg | 好不容易减掉 1kg |
| 3 | `wave` | 主升浪 | 达到 3kg | 连涨三天没反弹（减3kg） |
| 4 | `bull` | 牛市主升 | 达到 5kg | 账户飘红五斤（减5kg） |
| 5 | `exit` | 止盈封板 | 达到 7.5kg | 落袋为安，达成目标（减7.5kg） |

**`leek` · 韭菜入场** —— 记下人生第一笔

```
a chive sprout with its top leaves sliced off flat, a pale flat cut surface showing two growth rings, both eyes wide open in panic, a stiff gritted-teeth fake smile, one huge sweat drop on its side
```

**`untie` · 解套成功** —— 好不容易减掉 1kg

```
a thick rope knotted in a tight ball that has just snapped apart, both frayed broken ends flying outward, a tiny relieved grinning face on the knot, one torn band-aid stuck on the rope
```

**`wave` · 主升浪** —— 连涨三天没反弹（减3kg）

```
a rising staircase of three chunky stacked bars climbing up to the right, a tiny smug face on the top bar, a small triangular flag planted on the highest step
```

**`bull` · 牛市主升** —— 账户飘红五斤（减5kg）

```
a chunky furious bull head with a gold nose ring, one bulging bloodshot eye and one squinting eye, thick steam blasting out of both nostrils, a tiny flag tangled on one horn
```

**`exit` · 止盈封板** —— 落袋为安，达成目标（减7.5kg）

```
a fat bulging money bag tied shut with a thick rope, one coin squeezing out of the knot, a deadpan satisfied face on the bag, a small round stamp mark on its side
```

### 盘中操作（记录频次 · 手速与仓位）· 5 个

| # | 代号 | 成就名 | 解锁条件 | 画面要点 |
|---|---|---|---|---|
| 1 | `pen` | 试单 | 达到 1 次 | 小仓试探，先记一笔 |
| 2 | `half` | 半仓干 | 达到 5 次 | 一天五顿都在记（5笔饮食） |
| 3 | `allin` | 梭哈选手 | 达到 3 次 | 三次运动，满仓出击 |
| 4 | `lightning` | 高频交易员 | 达到 30 次 | 30笔成交，手速惊人 |
| 5 | `whale` | 量化巨鲸 | 达到 100 次 | 100笔，机构级交易量 |

**`pen` · 试单** —— 小仓试探，先记一笔

```
a chewed pencil standing upright with two tiny stub arms, a small torn notebook page tucked behind it, a nervous crooked open mouth on the pencil body, one bite mark on the eraser
```

**`half` · 半仓干** —— 一天五顿都在记（5笔饮食）

```
a rice bowl filled exactly half full, a pair of chopsticks stuck in at a crooked angle, a pair of tiny worried eyes on the bowl rim
```

**`allin` · 梭哈选手** —— 三次运动，满仓出击

```
a chunky stack of casino chips pushed forward off a table edge, the top chip tilted and about to fall, a pair of tiny manic bloodshot eyes on the top chip
```

**`lightning` · 高频交易员** —— 30笔成交，手速惊人

```
a jagged lightning bolt with a tiny manic grinning face, both tips frayed and throwing off sparks, one small bent paper clip tangled around its middle
```

**`whale` · 量化巨鲸** —— 100笔，机构级交易量

```
a chunky whale with a tiny laptop balanced on top of its head, one eye half closed in total boredom, a spout of water that turns into a small pile of coins
```

### 资本游戏（健康币积累与抽卡）· 5 个

| # | 代号 | 成就名 | 解锁条件 | 画面要点 |
|---|---|---|---|---|
| 1 | `coin` | 回口小肉 | 达到 500 次 | 累计赚到 500 币 |
| 2 | `bag` | 小财主 | 达到 2000 次 | 累计赚到 2000 币 |
| 3 | `vault` | 分红大户 | 达到 1000 次 | 持币过千，利息（没有）香 |
| 4 | `dice` | 首抽欧皇 | 达到 1 次 | 第一次打开交易员图鉴 |
| 5 | `cards` | 图鉴庄家 | 达到 20 次 | 抽了 20 次，包场了 |

**`coin` · 回口小肉** —— 累计赚到 500 币

```
a single chunky gold coin with a big bite taken out of its edge, two crumbs falling, a smug tiny face in the middle of the coin
```

**`bag` · 小财主** —— 累计赚到 2000 币

```
a small bulging money bag bursting at the seams, one coin resting on its top knot, an arrogant little face with a single gold tooth
```

**`vault` · 分红大户** —— 持币过千，利息（没有）香

```
a round bank vault door slightly ajar, a fat stack of banknotes poking out of the gap, two tiny eyes on the door handle, one hinge cracked
```

**`dice` · 首抽欧皇** —— 第一次打开交易员图鉴

```
a single chunky six-sided die tilted on one corner, its top face showing one big glowing star instead of pips, an overjoyed tiny face on the side face
```

**`cards` · 图鉴庄家** —— 抽了 20 次，包场了

```
a fan of three playing cards held open, the front card showing a blank face with a dealer's smirk, one small chip balanced on top of the fan
```

### 交易员图鉴（集卡与欧气）· 5 个

| # | 代号 | 成就名 | 解锁条件 | 画面要点 |
|---|---|---|---|---|
| 1 | `spark` | 开光 | 达到 1 次 | 首张卡入库 |
| 2 | `gem` | 欧气初显 | 达到 1 次 | 抽到第一张稀有(R) |
| 3 | `chosen` | 天选之子 | 达到 1 次 | 抽到第一张传说(SR) |
| 4 | `stamps` | 集邮狂魔 | 达到 6 次 | 集齐所有普通(N)卡 6 张 |
| 5 | `crown` | 满星收藏家 | 达到 45 次 | 45 星全部点亮 |

**`spark` · 开光** —— 首张卡入库

```
a single trading card bursting with a bright radiating spark from its middle, two halves opening like a book, a tiny awe-struck face on the card corner
```

**`gem` · 欧气初显** —— 抽到第一张稀有(R)

```
a chunky faceted gemstone in a rhombus shape with three big flat facets, a tiny proud face on the front facet, one small chip missing from a corner
```

**`chosen` · 天选之子** —— 抽到第一张传说(SR)

```
a small smug face wearing a chunky golden halo ring, straight chunky rays radiating outward, a tiny cape fluttering behind it, both eyes shaped like stars
```

**`stamps` · 集邮狂魔** —— 集齐所有普通(N)卡 6 张

```
a small album page holding six crooked stamps in two rows, one stamp glued on upside down, a pair of crazed wide-open eyes peeking over the top edge
```

**`crown` · 满星收藏家** —— 45 星全部点亮

```
a chunky gold crown tilted to one side, all five points topped with a star, one point slightly bent, a tiny tired but proud face on the crown band
```

### 涨停板敢死队（涨停仪式 · 打板专业户）· 5 个

| # | 代号 | 成就名 | 解锁条件 | 画面要点 |
|---|---|---|---|---|
| 1 | `board` | 首板 | 达到 1 次 | 第一次涨停，开盘即巅峰 |
| 2 | `second` | 二板换手 | 达到 2 次 | 连续两天涨停，龙头气质 |
| 3 | `pro` | 打板专业户 | 达到 5 次 | 涨停 5 次，手法渐熟 |
| 4 | `demon` | 连板妖股 | 达到 10 次 | 涨停 10 次，市场总龙头 |
| 5 | `god` | 封神榜 | 达到 20 次 | 涨停 20 次，入庙受香火 |

**`board` · 首板** —— 第一次涨停，开盘即巅峰

```
a single chunky rectangular board nailed to a short post, the nail bent sideways, a tiny shocked face on the board, one small confetti flake floating above it
```

**`second` · 二板换手** —— 连续两天涨停，龙头气质

```
two identical rectangular boards stacked one on top of the other, the top board tilting off balance, a tiny dizzy face on the lower board
```

**`pro` · 打板专业户** —— 涨停 5 次，手法渐熟

```
a chunky rubber stamp with a thick handle slammed down hard, a splash of ink bursting from the impact point, a tiny confident smirk on the stamp body
```

**`demon` · 连板妖股** —— 涨停 10 次，市场总龙头

```
a small green horned imp with a torn red cape, both arms raised high, three tiny flames floating around it, a wide insane grin with sharp teeth
```

**`god` · 封神榜** —— 涨停 20 次，入庙受香火

```
a small stone shrine statue with a golden plaque floating above its head, one thin incense stick on each side, two tiny closed serene eyes, one chipped ear
```

### 散户的自我修养（自律与自嘲并存）· 5 个

| # | 代号 | 成就名 | 解锁条件 | 画面要点 |
|---|---|---|---|---|
| 1 | `threeday` | 三日游 | 达到 3 次 | 连打卡 3 天，短线思维 |
| 2 | `weekline` | 周线级别 | 达到 7 次 | 连打卡 7 天，拿成周线 |
| 3 | `cut` | 割肉离场 | 达到 1 次 | 连续打卡断过，含泪止损 |
| 4 | `bomb` | 爆仓体验 | 达到 800 次 | 单日净热量超标 800 kcal |
| 5 | `diamond` | 价值投资 | 达到 100 次 | 连打卡 100 天，时间的朋友 |

**`threeday` · 三日游** —— 连打卡 3 天，短线思维

```
three identical small round suns in a diagonal row, the last one melting and drooping, a tiny exhausted face on the middle one
```

**`weekline` · 周线级别** —— 连打卡 7 天，拿成周线

```
a chunky calendar page with one single big circled mark in the middle, a bent paper clip holding the page, a tiny proud face on the corner
```

**`cut` · 割肉离场** —— 连续打卡断过，含泪止损

```
a pair of chunky scissors slicing through a thick sausage-like segment, the cut end wobbling, a tiny tearful face on the scissors handle, one drop falling
```

**`bomb` · 爆仓体验** —— 单日净热量超标 800 kcal

```
a round cartoon bomb with a lit burning fuse, a jagged crack across its bulging body, a tiny panicked wide-open mouth, both eyes popped wide
```

**`diamond` · 价值投资** —— 连打卡 100 天，时间的朋友

```
a chunky diamond with three big flat facets, a tiny patient half-closed eye on the front facet, one small pickaxe leaning against its base
```

---

## 5. 落位与命名

| 项 | 值 |
|---|---|
| 临时落位（生图产物） | `E:\WorkBuddy\jianpan-ghpages\promo\ach_src\ach-<代号>.png` |
| 抠图后 | 同上目录，`-cut.png` 后缀，供人眼逐张复核 |
| 上传 | 走云存储 `ach/ach-<代号>.webp`（复用段位卡那条 `uploadRankAssets` 云函数通道） |
| 页面引用 | 现在：`/images/ach/ach-{{icon}}.png`；将来：`lib/ach_assets.js` manifest 的 `cloud://` |

⚠️ 代号 = `index.html` 里 `ACHIEVEMENTS[].icon`，**逐字一致**。写错一个字母 = 卡面缺图。

---

## 6. 你出图之后，我接这些（不用你动手）

1. 抠洋红 → 裁切居中 → 512→**132px**（44×3 的 3 倍图）→ WebP q88
2. 上传云存储 `ach/`，回填 `lib/ach_assets.js`（顺序锁死对齐 `ACHIEVEMENTS`）
3. 改 `.badge .b` 48→64、图标 26→44（两端口径：`achievements.wxss` + PWA `index.html`）
4. 跑闸：`mp_wxss_check` / `mp_ach_test` / `_run_all_asserts` + 模拟器实图复核
5. 云图与本地图共存兜底（`onAchImgError` 回退），云稳后你再确认删本地 `images/ach/`

---

## 7. 施工建议：先出 3 张定风格

不要一次生 30 张。先出这 3 张，覆盖三种调性：

| 代号 | 成就 | 为什么选它 |
|---|---|---|
| `leek` | 韭菜入场 | **惨** —— 也和段位卡 01 呼应，可横向对比风格是否同宇宙 |
| `coin` | 回口小肉 | **土** —— 金币被咬一口，最典型的「穷酸幽默」 |
| `bomb` | 爆仓体验 | **疯** —— 表情最夸张，最考验 44px 可辨性 |

这 3 张你满意（风格统一 + 缩到 44px 还看得懂）再批量出剩下 27 张。

---

## 附：成就总览（30 个）

- **持仓与套牢**：韭菜入场 / 解套成功 / 主升浪 / 牛市主升 / 止盈封板
- **盘中操作**：试单 / 半仓干 / 梭哈选手 / 高频交易员 / 量化巨鲸
- **资本游戏**：回口小肉 / 小财主 / 分红大户 / 首抽欧皇 / 图鉴庄家
- **交易员图鉴**：开光 / 欧气初显 / 天选之子 / 集邮狂魔 / 满星收藏家
- **涨停板敢死队**：首板 / 二板换手 / 打板专业户 / 连板妖股 / 封神榜
- **散户的自我修养**：三日游 / 周线级别 / 割肉离场 / 爆仓体验 / 价值投资
