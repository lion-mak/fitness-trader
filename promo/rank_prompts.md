# 段位卡 · 像素搞怪版 · 生图提示词与产物（v4：11 张已出）

风格定位：**像素 + 搞怪（惨 / 土 / 疯），不要可爱**。卡上不放等级数字，一级一个称谓。
成品：`assets/ranks/*.png`（@3x 预览）+ `assets/ranks/webp/*.webp`（应用用）。

---

## 一、卡片规格（先定死尺寸，提示词围绕它写）

| 项 | 值 | 出处（量出来的，不是猜的） |
|---|---|---|
| 基准视口 | 430 CSS px | 全项目 rect 闸基准 `VW=430` |
| 页面左右留白 | 14 px | 沿用 `.rank-hero { margin:10px 14px 0 }` |
| 三列间距 | **18 px** | Mak：间距大一点没关系 ⇒ 卡更瘦 |
| **单卡尺寸** | **122×171 px** | (402 − 18×2) / 3 = 122；122:171 ≈ 0.713，与实体交易卡 2.5:3.5 一致 |
| 出图 | **366×513**（@3x PNG）+ **WebP q88** | 122 × 3 |
| 体积 | **210 KB / 11 张** | 主包 2MB 的 **10.3%** |

**卡面三段式**（122×171，内边距 8）：
- **画面区 106×117** —— 淡色渐变面板（白 → 强调色混白 88%），角色贴在里面
- 间隙 4
- **名称条 106×36** —— 底色 = 段位强调色，25px/700 黑体，字距 +2

> ⭐**为什么要给角色一块淡色画面**：11 张里有黑西装（机构）、暗皮衣（牛散）、深绿魔鬼（庄家）——
> 直接摆在深色卡面上会**糊成一坨**（第一版实拍确认）。淡色画面 + 生图自带的 1px 深描边，
> 是唯一能让 11 张**全部**可读的分区方式，也正好等于集换式卡牌「深框 + 画面 + 色条」的经典结构。

**文字：黑体，不用像素字体**
- Mak 定：**像素字体不搭**（试过 Cubic 11 俐方體11號，实拍违和）⇒ 回到 `Microsoft YaHei / PingFang SC`。
- ⭐**字色按对比度最大化取，不按深浅直觉**：对比度公式 `(L1+0.05)/(L2+0.05)`，
  黑字 = `(L+0.05)/0.05`、白字 = `1.05/(L+0.05)` ⇒ 分界在 **L ≈ 0.179**，**不是 0.5**。
  实测韭菜绿 `#3FBF57` 配白字只有 **2.4:1**（发虚），配近黑字 **8.8:1**。
  11 段实算结果：**7 黑（韭菜/散户/小散/中户/牛散/游资/股神）+ 4 白（大户/主力/机构/庄家）**，
  最低对比 5.11:1（中户蓝底）达标。
- 文字加一道 **+2px 无模糊硬阴影**（opacity .40）—— 缩到 96px 时比纯色更抓得住。

---

## 二、通用前缀 —— 11 张一字不改

```
Goofy 16-bit pixel art game sprite, weird and ridiculous cartoon creature, exaggerated ugly-comic
expression, absurd and lopsided proportions, deadpan or manic face, thick 1px dark outline,
flat solid color blocks with dithering shading, hard pixel edges, no gradients, no anti-aliasing,
no blur, limited 12-color palette, high contrast, retro arcade comedy sprite,
single character centered, full body visible with a small margin,
bold simple silhouette close to a square bounding box, arms or props spread out to both sides,
stays readable at 130px wide,
flat solid magenta background #FF00FF edge to edge,
no text, no letters, no numbers, no watermark, no signature, no frame, no border, no ground shadow,
no cute, no kawaii, no chibi, no glossy shine, no sparkly eyes, no pastel colors, no mascot style.
Character: <见下表>
```

四行不是装饰：
- `no cute, no kawaii, no chibi, no sparkly eyes, no pastel` —— **反向约束必须写**。不写模型一定滑回可爱吉祥物（上一版就是这么翻车的）。
- `flat solid magenta background #FF00FF` —— `background=transparent` 参数**不生效**（上一轮被渲染成棋盘格，抠图两轮才收拾干净）；洋红纯底**一次抠净、无粉边**，且洋红不出现在任何角色配色里。
- `bold simple silhouette close to a square bounding box, arms or props spread out` —— 逼轮廓偏远、张开道具，11 张摆一起才齐（纯细高角色在方框里会显小）。
- `stays readable at 130px wide` —— 把最终显示尺寸写进提示词，逼模型砍掉小尺寸必糊的碎细节。

---

## 三、11 段角色提示词（每张只换这一段）

统一套路：**身份道具（1 个）+ 表情（夸张）+ 一个惨/土/疯的细节**。表情词是搞怪感的总开关。

| # | 称谓 | 代号 | 角色段（替换 `Character:` 后面的内容） |
|---|---|---|---|
| 01 | 韭菜 | LEEK | `a chive sprout whose top leaves are cut off in one clean horizontal slice, the flat cut surface is a pale cream-colored rectangle with visible rings, a big metal guillotine blade hanging right above its head, a worn band-aid stuck on the cut, both eyes wide open and bloodshot in pure panic, stiff gritted-teeth fake smile, one huge sweat drop, tiny stick arms clutching a tiny phone showing a single red candle, white root hairs as trembling legs, bald, self-deprecating loser energy` |
| 02 | 散户 | RETAIL | `a hunched sleep-deprived retail investor, worn hoodie, enormous purple eye bags, messy hair, both hands gripping a glowing phone, phone light glowing on his face, an instant noodle cup balanced on top of his head, blank thousand-yard stare, flat deadpan mouth, one slipper missing, bare foot` |
| 03 | 小散 | MINOR | `a scrawny tiny gremlin kid with a bowl haircut, wearing an adult suit jacket several sizes too big that drags on the floor, clutching one single shiny gold coin in both hands, one eye squinting suspiciously and the other bulging wide, tongue sticking out of the corner of the mouth, pockets turned inside out, threadbare and shabby` |
| 04 | 中户 | MID | `a chubby middle-aged man in a cheap untucked shirt with rolled-up sleeves, arms crossed confidently while huge sweat drops pour down his face, smug wobbly smile, half-closed self-satisfied eyes, a thick worn account book tucked under one arm, a cheap fake-leather briefcase in the other hand` |
| 05 | 大户 | BIG | `a fat balding nouveau-riche man in a shiny silk bathrobe, thick gold chain necklace, fuzzy slippers, lounging deep in a recliner chair, cigar in the mouth, one hand flicking a fat wad of cash, sunglasses pushed up on his forehead, complacent smug grin, hairy legs` |
| 06 | 牛散 | PRO | `a muscular bull standing upright like a person, hairy chest, black leather vest, gold nose ring, black sunglasses, a toothpick in the corner of the mouth, one fist pumped up in the air, the other hand holding a smartphone, steam puffing from the nostrils, sweat drops, a scar on one shoulder` |
| 07 | 游资 | HOT MONEY | `a manic grinning shark in a pinstripe suit with a gold chain, huge sharp teeth, wide crazy bloodshot eyes, riding a rocket made of a giant golden candlestick, a briefcase bursting with money bills, necktie blown back by the wind, speed lines behind it` |
| 08 | 主力 | MAIN FORCE | `a giant calm octopus wearing a general's military cap and a monocle, narrow sly half-lidded eyes, a tiny evil smirk, one tentacle twirling a cigar, the other tentacles holding puppet strings that control small candlestick-chart puppets dangling below, butter-smooth and unbothered` |
| 09 | 机构 | INSTITUTION | `a stiff cold bureaucrat, black suit, bald head, thick square glasses, no mouth at all, holding a huge red rubber stamp, a stack of documents under one arm, standing perfectly straight with zero expression, unnervingly neat, cold and faceless` |
| 10 | 庄家 | DEALER | `a devil in a tuxedo with two small horns, slicked-back hair, cigarette in the corner of the mouth, half-lidded wicked eyes, dealing playing cards that have candlestick chart faces, one hoof resting on a stack of casino chips, forked tail, smug` |
| 11 | 股神 | STOCK GOD | `an old sage with a long white beard and a pixel halo floating cross-legged on top of a giant golden candlestick shaped like a mountain peak, round dark sunglasses, sipping tea from a tiny cup, smug closed eyes, self-satisfied smile, golden pixel aura, ridiculous serenity` |

生图参数：`size=1024x1024, quality=high`，**不要传 `background`**（透明不生效，靠洋红底）。

---

## 四、11 段阶梯与配色

PWA 现状 `RANKS` 是 **8 段**，要改成 **11 段**（新增 韭菜 / 牛散 / 主力）。等级口径 `lv = floor(exp/100) + 1`。

| # | 称谓 | EN | 建议 minLv | 卡框 / 名称条色 | 名称条字色 | 定位 |
|---|---|---|---|---|---|---|
| 01 | 韭菜 | LEEK | 1 | `#3FBF57` 韭菜绿 | 黑 8.8:1 | 起点，被割 |
| 02 | 散户 | RETAIL | 2 | `#7C8DA6` 灰蓝 | 黑 6.2:1 | 刚入市 |
| 03 | 小散 | MINOR | 4 | `#33A6B8` 青 | 黑 7.3:1 | 有点本金 |
| 04 | 中户 | MID | 6 | `#3D7BE0` 蓝 | 黑 5.1:1 | 稳住了 |
| 05 | 大户 | BIG | 8 | `#5B4BC4` 靛 | 白 6.5:1 | 有仓位 |
| 06 | 牛散 | PRO | 10 | `#C08A2E` 暗金 | 黑 6.9:1 | 个人高手 |
| 07 | 游资 | HOT MONEY | 13 | `#E8781E` 橙 | 黑 7.1:1 | 短线猛 |
| 08 | 主力 | MAIN FORCE | 16 | `#C43A2E` 红 | 白 5.3:1 | 能影响走势 |
| 09 | 机构 | INSTITUTION | 20 | `#8E44AD` 紫 | 白 5.9:1 | 体系化 |
| 10 | 庄家 | DEALER | 24 | `#4A4A57` 铁灰 | 白 8.7:1 | 发牌的 |
| 11 | 股神 | STOCK GOD | 30 | `#D4AF37` 亮金 | 黑 10.0:1 | 封顶 |

⚠️ 原表颜色**有重复**（小散/中户同 `#5ac8fa`，大户/游资同 `#00c896`），11 档挤一起分不出档位 ⇒ 用上面这套单调递进。

---

## 五、后处理管线（`promo/make_rank_card_v3.py`，已跑通）

1. **抠洋红底** —— 判据 `R>140 & G<125 & R−G>70 & B−G>15`，11 张一次命中（命中率 66~76%）。
   硬边二值化（`MinFilter(3)` 收缩 1px 去抗锯齿混色边再取阈值）—— 像素画**不能羽化**，一模糊像素块就毁。
2. **水印区强制划为背景** —— 右下角 `y≥880, x≥840` 实测每张 1800~2600 px 非洋红，直接置背景，顺带避免撑大包围盒。
3. **等比缩放、不做量化** —— 原计划降到 64/96 统一颗粒度，**实测反向**：生图自带的像素块与网格不对齐，NEAREST 降采样产生满边毛刺。等比 LANCZOS 最干净（长边 480）。
4. **合成卡框** —— 切角像素框 + 淡色画面 + 彩色名称条；文字走代码（生图写中文必糊、11 张必漂）。
5. **名称条自动居中** —— 渲完量墨迹重心，偏 >0.34px 就回调基线（最多 4 趟）。本次 11 张**第 1 趟即 0.00**。
6. **出 PNG(@3x) + WebP q88**。

### 🔴 生图工具的两个坑（本批实际踩到，务必记住）

1. **并发调用会让 `output_dir` 参数串**：6 张一起发，全部落进**最后一个**目录。
2. **同一秒完成的两张会互相覆盖**：文件名只到「秒」(`..._T12-28-38.png`)，
   6 并发 → 只落 4 个文件、5 并发 → 只落 3 个。**批量生图必须串行**。
3. 归档只能靠**文件名时间戳 + 人眼逐张复核**：`promo/_pixel3_icons/_organize.py` 生成复核板确认身份后再落名。

---

## 六、产物与素材

| 路径 | 内容 | 入库 |
|---|---|---|
| `assets/ranks/NN_key.png` | 11 张卡 @3x（366×513），预览用 | ✅ |
| `assets/ranks/webp/NN_key.webp` | 11 张卡 WebP q88，应用用（210 KB） | ✅ |
| `promo/rank_src/NN_key.png` | 11 张生图源（512px）—— **改卡框样式重跑合成必需** | ✅ |
| `promo/make_rank_card_v3.py` | 合成器 | ✅ |
| `promo/make_rank_cards.py` | 提供 `matte` / `fit_long_side` / `launch_browser`（v3 复用） | ✅ |
| `promo/_pixel3_icons/orig/` | 1024 原图（9 MB，仅本机留档） | ❌ 已忽略 |
| `promo/_rank_ref/` | 检查图（对照板 / 真机比例 / 尺寸阶梯 / 抠图质检） | ❌ 已忽略 |

⚠️ 源图**必须入库一份**：生图有随机性，重出不会得到同一张脸 —— 想改卡框/改配色时，
只有手里的源图能让 11 张保持原样。

---

## 七、实测记录

**尺寸可读性**（`_rank_ref/rank_sizes.png`，取韭菜/游资/股神三档）：
| 卡宽 | 角色 | 称谓 |
|---|---|---|
| 140px | 五官清楚 | 极清楚 |
| **122px（目标）** | 五官可辨 | **清楚** ✓ |
| 96px | 糊成色块 | **仍完全可读** ✓ |
| 72px | 只剩轮廓 | 认得出字形 |

**真机比例**（`_rank_ref/rank_row_430.png`）：430 视口下 3 列 = 122×3 + 18×2 = **402px**，正好铺满。

**迭代史**：
- v1 六边形 + 卡通角色（照参考图）→ Mak 否：**风格不要像参考图**，改像素风卡片。脚本已删。
- v2 方形 127×127（16-bit 精致像素）→ Mak 否：**不要可爱风，要搞怪**、三横排、卡要瘦长。目录已删。
- v3 122×171 三横排 + 像素字体 → Mak 否：**像素字体不搭**。
- **v4（当前）**：11 张全出、黑体、淡色画面分区、WebP 210 KB。

**下一版提示词的经验**：`head sliced off flat` 这类**"被破坏/负向"描述模型会跳过**（第一版韭菜头顶完好）。
补丁 = 改成正向描述切口 + 给"被割"一个**可见物件**：
> `the flat cut surface is a pale cream-colored rectangle with visible rings, a big metal guillotine blade hanging right above its head`

v4 实测**生效**（韭菜头顶平切露白 + 悬着闸刀）。

---

## 八、下一件事（接入，尚未做）

1. `RANKS` 8 段 → **11 段**（门槛/配色取第四节表），PWA 与小程序两端同步。
2. 「我的」页段位区换成卡图（122×171 三列，`promo/rank_src` 已备好 webp 素材）。
3. ⚠️ 小程序侧 WebP 需 `image` 组件支持（基础库 2.9.0+ 已支持），若担心兼容可退 PNG-8 量化。
