# -*- coding: utf-8 -*-
"""
make_ach_prompts.py —— 生成「成就徽章 · 像素搞怪版」生图提示词（md 文档 + 纯文本清单）。

为什么要脚本生成而不是手写文档：
  ① 30 个成就的**名称 / 描述 / 解锁条件**全部从 index.html 的 ACHIEVEMENTS / ACH_CATS 直读
     ⇒ 条件文案与代码永远一致，改数值不用回来改文档（复刻铁律：不手抄两份）。
  ② md 与 txt 共用同一份 SUBJECT 数据 ⇒ 不可能出现两份提示词不一致。
  ③ 断言兜底：ACHIEVEMENTS 里每个 id 必须有对应 Subject，漏了直接报错（防生成漏图）。

产出（LF 行尾）：
  promo/ach_prompts.md   —— 中文施工文档（规格 + 落位 + 流程）
  promo/ach_prompts.txt  —— 30 条完整提示词（前缀已拼好，一次复制一条去生图）

改动 SUBJECT 或风格前缀后重跑本脚本即可。⛔ 不要手改产出文件。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "index.html"))
OUT_MD = os.path.join(HERE, "ach_prompts.md")
OUT_TXT = os.path.join(HERE, "ach_prompts.txt")

# ---------------------------------------------------------------------------
# 1) 从 index.html 直读成就与分类（不手抄）
# ---------------------------------------------------------------------------
html = io.open(SRC, encoding="utf-8", errors="replace").read()


def grab(anchor):
    i = html.find(anchor)
    if i < 0:
        sys.exit("找不到 %s（index.html 被重构了？）" % anchor)
    j = html.find("];", i)
    if j < 0:
        sys.exit("%s 没有闭合的 `];`" % anchor)
    return html[i:j + 2]


ach_block = grab("const ACHIEVEMENTS")
cat_block = grab("const ACH_CATS")

# 每条成就都是一行：`  { id:'leek', cat:'hold', name:'韭菜入场', desc:'记下人生第一笔', icon:'leek', reward:20, target:1, prog:s=>... },`
rows = []
for line in ach_block.split("\n"):
    s = line.strip()
    if not s.startswith("{ id:'"):
        continue
    def f(key, pat=r"'([^']*)'"):
        m = re.search(key + r"\s*:\s*" + pat, s)
        return m.group(1) if m else None
    d = {
        "id": f("id"),
        "cat": f("cat"),
        "name": f("name"),
        "desc": f("desc"),
        "icon": f("icon"),
        "target": f("target", r"([\d.]+)"),
        "unit": f("unit"),
    }
    if not (d["id"] and d["icon"]):
        sys.exit("解析失败的行：%s" % s[:120])
    rows.append(d)

cats = []
for line in cat_block.split("\n"):
    s = line.strip()
    if not s.startswith("{ id:'"):
        continue
    def g(key):
        m = re.search(key + r"\s*:\s*'([^']*)'", s)
        return m.group(1) if m else None
    cats.append({"id": g("id"), "name": g("name"), "icon": g("icon"),
                 "color": (re.search(r"color\s*:\s*'(#[0-9a-fA-F]{6})'", s) or [None, None])[1],
                 "desc": g("desc")})

if len(rows) < 25:
    sys.exit("只解析出 %d 条成就，明显不对（期望 30）" % len(rows))
if len(cats) != 6:
    sys.exit("分类数 %d ≠ 6" % len(cats))

cat_of = {c["id"]: c for c in cats}

# ---------------------------------------------------------------------------
# 2) 30 条画面描述（唯一的创作源，md/txt 共用）
#    套路与段位卡一致：一个荒诞主体 + 夸张表情 + 一处惨/土/疯的细节。
#    ⚠️ 44px 显示尺寸是硬约束 ⇒ 每条最多 3 个大形状、不写小道具细节。
# ---------------------------------------------------------------------------
SUBJECT = {
    # —— 持仓与套牢 ——
    "leek":      "a chive sprout with its top leaves sliced off flat, a pale flat cut surface showing two growth rings, both eyes wide open in panic, a stiff gritted-teeth fake smile, one huge sweat drop on its side",
    "untie":     "a thick rope knotted in a tight ball that has just snapped apart, both frayed broken ends flying outward, a tiny relieved grinning face on the knot, one torn band-aid stuck on the rope",
    "wave":      "a rising staircase of three chunky stacked bars climbing up to the right, a tiny smug face on the top bar, a small triangular flag planted on the highest step",
    "bull":      "a chunky furious bull head with a gold nose ring, one bulging bloodshot eye and one squinting eye, thick steam blasting out of both nostrils, a tiny flag tangled on one horn",
    "exit":      "a fat bulging money bag tied shut with a thick rope, one coin squeezing out of the knot, a deadpan satisfied face on the bag, a small round stamp mark on its side",

    # —— 盘中操作 ——
    "pen":       "a chewed pencil standing upright with two tiny stub arms, a small torn notebook page tucked behind it, a nervous crooked open mouth on the pencil body, one bite mark on the eraser",
    "half":      "a rice bowl filled exactly half full, a pair of chopsticks stuck in at a crooked angle, a pair of tiny worried eyes on the bowl rim",
    "allin":     "a chunky stack of casino chips pushed forward off a table edge, the top chip tilted and about to fall, a pair of tiny manic bloodshot eyes on the top chip",
    "lightning": "a jagged lightning bolt with a tiny manic grinning face, both tips frayed and throwing off sparks, one small bent paper clip tangled around its middle",
    "whale":     "a chunky whale with a tiny laptop balanced on top of its head, one eye half closed in total boredom, a spout of water that turns into a small pile of coins",

    # —— 资本游戏 ——
    "coin":      "a single chunky gold coin with a big bite taken out of its edge, two crumbs falling, a smug tiny face in the middle of the coin",
    "bag":       "a small bulging money bag bursting at the seams, one coin resting on its top knot, an arrogant little face with a single gold tooth",
    "vault":     "a round bank vault door slightly ajar, a fat stack of banknotes poking out of the gap, two tiny eyes on the door handle, one hinge cracked",
    "dice":      "a single chunky six-sided die tilted on one corner, its top face showing one big glowing star instead of pips, an overjoyed tiny face on the side face",
    "cards":     "a fan of three playing cards held open, the front card showing a blank face with a dealer's smirk, one small chip balanced on top of the fan",

    # —— 交易员图鉴 ——
    "spark":     "a single trading card bursting with a bright radiating spark from its middle, two halves opening like a book, a tiny awe-struck face on the card corner",
    "gem":       "a chunky faceted gemstone in a rhombus shape with three big flat facets, a tiny proud face on the front facet, one small chip missing from a corner",
    "chosen":    "a small smug face wearing a chunky golden halo ring, straight chunky rays radiating outward, a tiny cape fluttering behind it, both eyes shaped like stars",
    "stamps":    "a small album page holding six crooked stamps in two rows, one stamp glued on upside down, a pair of crazed wide-open eyes peeking over the top edge",
    "crown":     "a chunky gold crown tilted to one side, all five points topped with a star, one point slightly bent, a tiny tired but proud face on the crown band",

    # —— 涨停板敢死队 ——
    "board":     "a single chunky rectangular board nailed to a short post, the nail bent sideways, a tiny shocked face on the board, one small confetti flake floating above it",
    "second":    "two identical rectangular boards stacked one on top of the other, the top board tilting off balance, a tiny dizzy face on the lower board",
    "pro":       "a chunky rubber stamp with a thick handle slammed down hard, a splash of ink bursting from the impact point, a tiny confident smirk on the stamp body",
    "demon":     "a small green horned imp with a torn red cape, both arms raised high, three tiny flames floating around it, a wide insane grin with sharp teeth",
    "god":       "a small stone shrine statue with a golden plaque floating above its head, one thin incense stick on each side, two tiny closed serene eyes, one chipped ear",

    # —— 散户的自我修养 ——
    "threeday":  "three identical small round suns in a diagonal row, the last one melting and drooping, a tiny exhausted face on the middle one",
    "weekline":  "a chunky calendar page with one single big circled mark in the middle, a bent paper clip holding the page, a tiny proud face on the corner",
    "cut":       "a pair of chunky scissors slicing through a thick sausage-like segment, the cut end wobbling, a tiny tearful face on the scissors handle, one drop falling",
    "bomb":      "a round cartoon bomb with a lit burning fuse, a jagged crack across its bulging body, a tiny panicked wide-open mouth, both eyes popped wide",
    "diamond":   "a chunky diamond with three big flat facets, a tiny patient half-closed eye on the front facet, one small pickaxe leaning against its base",
}

missing = [r["icon"] for r in rows if r["icon"] not in SUBJECT]
if missing:
    sys.exit("这些成就图标缺画面描述：%s" % ", ".join(sorted(set(missing))))
unused = sorted(set(SUBJECT) - set(r["icon"] for r in rows))
extra_note = ("（另有 %d 条描述未被成就引用：%s）" % (len(unused), ", ".join(unused))) if unused else ""

# ---------------------------------------------------------------------------
# 3) 风格前缀（30 张一字不改）—— 与段位卡同宇宙，但按「小尺寸可辨」重写
# ---------------------------------------------------------------------------
PREFIX = (
    "Goofy low-res pixel art game badge, one single chunky object or creature, weird and ridiculous, "
    "absurd lopsided proportions, one comic face with an exaggerated expression, "
    "chunky pixels, big square pixel blocks, roughly 22 pixel blocks across the canvas, "
    "extra thick near-black outline on every shape, flat solid color blocks with light dithering, "
    "hard pixel edges, no gradients, no anti-aliasing, no blur, limited 8-color palette, very high contrast, "
    "big bold simple silhouette filling 80% of the frame, centered, at most 3 large shapes, "
    "no fine detail, no thin lines, no tiny texture, no small decoration, "
    "stays instantly readable when shrunk to 44px, "
    "flat solid magenta background #FF00FF edge to edge, even margin around the subject, "
    "no text, no letters, no numbers, no watermark, no signature, no frame, no border, "
    "no ground shadow, no drop shadow, no scenery, no background pattern, "
    "no cute, no kawaii, no chibi, no glossy shine, no sparkly eyes, no pastel colors, no mascot style. "
    "Subject: "
)

# ---------------------------------------------------------------------------
# 4) 产出 md
# ---------------------------------------------------------------------------
def cond(r):
    """把 target/unit 还原成人话条件（与页面显示口径同源：target 是达成阈值）。"""
    unit = r["unit"] or "次"
    t = r["target"]
    if unit == "kg" or unit == "kcal":
        return "达到 %s%s" % (t, unit)
    return "达到 %s %s" % (t, unit)


md = []
w = md.append
w("# 成就徽章 · 像素搞怪版 · 生图提示词（v1）")
w("")
w("> 30 个成就图标：从「24×24 单色矢量剪影」换成「像素搞怪徽章」。")
w("> 风格宇宙与段位卡同一套（惨 / 土 / 疯，**不要可爱**），但尺寸约束完全不同 —— 见第 1 节，先读它。")
w("> 本文件由 `promo/make_ach_prompts.py` 生成（成就名/条件直读 `index.html`，⛔ 不要手改本文件）。")
w("")
w("---")
w("")
w("## 1. ⚠️ 生图前必须先定的一件事：显示尺寸")
w("")
w("现量数据（不是估的）：")
w("")
w("| 位置 | 容器 | 图标渲染尺寸 | 出处 |")
w("|---|---|---|---|")
w("| 成就格 `.badge .b` | 48×48 圆角块 | **26×26** | `achievements.wxss` / 两端口径一致 |")
w("| 分类头 `.ach-cat-ic` | 34×34 块 | **20×20** | 同上 |")
w("| 近期目标 `.prog-row .ic` | — | **26×26** | 同上 |")
w("")
w("**问题**：26px 只够承载一个单色剪影。像素搞怪的「傻表情 + 一处惨细节」在 26px 下会糊成一坨 ——")
w("这正是段位卡的镜像反例（那边是 122×171 大图，像素风成立；这边 26px，像素风不成立）。")
w("")
w("**建议（配套改动，极小）**：")
w("")
w("| 项 | 现在 | 改成 | 依据 |")
w("|---|---|---|---|")
w("| `.badge .b` 方块 | 48×48 | **64×64** | 三列网格列宽 (430−28−20)/3 ≈ **127px**，方块去掉 `.badge` 左右 padding 16 后可用 **111px**，64 绰绰有余 |")
w("| 图标 `ic-img` | 26×26 | **44×44** | 44px 下「22 像素块横跨」= 每块 2px，清晰可辨 |")
w("")
w("**本文档全部提示词按「缩到 44px 可辨」写**。若坚持保留 26px，提示词要再砍（只留一个形状、去掉表情），")
w("请说一声我另出一版。")
w("")
w("---")
w("")
w("## 2. 出图规格")
w("")
w("| 项 | 值 | 说明 |")
w("|---|---|---|")
w("| 尺寸 | **512×512** | 44px 显示 = 11.6 倍图，超采样远够 |")
w("| 格式 | PNG | 不要 JPG（描边会糊） |")
w("| 背景 | **纯洋红 `#FF00FF`** | ⛔ 不要传 `background=transparent`（不生效，会被渲染成棋盘格） |")
w("| 抠图判据 | `R>140 & G<125 & R−G>70 & B−G>15` | 一次抠净，不羽化（像素画羽化即毁） |")
w("| 主体占比 | 画布 **78~84%** | 四周留均匀洋红边，抠完正好贴进方块 |")
w("| 命名 | `ach-<代号>.png` | 代号见下表，与代码里的 `icon` 字段**逐字一致** |")
w("")
w("**⚠️ 图是我们抠成透明底的**，不是自带底板的徽章 —— 底色由页面的 `.b` 提供（已解锁=分类色，未解锁=灰+`opacity:.35`）。")
w("所以每张图必须有**极厚近黑描边**，贴在彩色底上才不糊。")
w("")
w("---")
w("")
w("## 3. 通用前缀（30 张一字不改）")
w("")
w("```")
w(PREFIX.rstrip())
w("```")
w("")
w("四行不是装饰：")
w("")
w("- `chunky pixels, roughly 22 pixel blocks across` —— 把「低分辨率」翻译成模型能执行的量化约束。")
w("  不写这句，模型会给 512px 的精细插画，缩到 44px 直接糊。")
w("- `at most 3 large shapes, no fine detail, no small decoration` —— 44px 的硬约束前置到提示词，")
w("  逼模型砍掉小尺寸必糊的碎细节。")
w("- `stays instantly readable when shrunk to 44px` —— 把最终显示尺寸写进提示词（段位卡同套路，那句是 `130px`）。")
w("- `flat solid magenta background #FF00FF` + `no cute, no kawaii, no chibi, no sparkly eyes, no pastel` ——")
w("  洋红一次抠净；**反向约束必须写**，不写模型必滑回可爱吉祥物（段位卡上一版就是这么翻车的）。")
w("")
w("---")
w("")
w("## 4. 30 条画面描述（每张只换 `Subject:` 后面这一段）")
w("")
for c in cats:
    lst = [r for r in rows if r["cat"] == c["id"]]
    w("### %s（%s）· %d 个" % (c["name"], c["desc"], len(lst)))
    w("")
    w("| # | 代号 | 成就名 | 解锁条件 | 画面要点 |")
    w("|---|---|---|---|---|")
    for i, r in enumerate(lst, 1):
        w("| %d | `%s` | %s | %s | %s |" % (i, r["icon"], r["name"], cond(r), r["desc"]))
    w("")
    # 英文逐条列出（便于对照复制）
    for r in lst:
        w("**`%s` · %s** —— %s" % (r["icon"], r["name"], r["desc"]))
        w("")
        w("```")
        w(SUBJECT[r["icon"]])
        w("```")
        w("")
w("---")
w("")
w("## 5. 落位与命名")
w("")
w("| 项 | 值 |")
w("|---|---|")
w("| 临时落位（生图产物） | `E:\\WorkBuddy\\jianpan-ghpages\\promo\\ach_src\\ach-<代号>.png` |")
w("| 抠图后 | 同上目录，`-cut.png` 后缀，供人眼逐张复核 |")
w("| 上传 | 走云存储 `ach/ach-<代号>.webp`（复用段位卡那条 `uploadRankAssets` 云函数通道） |")
w("| 页面引用 | 现在：`/images/ach/ach-{{icon}}.png`；将来：`lib/ach_assets.js` manifest 的 `cloud://` |")
w("")
w("⚠️ 代号 = `index.html` 里 `ACHIEVEMENTS[].icon`，**逐字一致**。写错一个字母 = 卡面缺图。")
w("")
w("---")
w("")
w("## 6. 你出图之后，我接这些（不用你动手）")
w("")
w("1. 抠洋红 → 裁切居中 → 512→**132px**（44×3 的 3 倍图）→ WebP q88")
w("2. 上传云存储 `ach/`，回填 `lib/ach_assets.js`（顺序锁死对齐 `ACHIEVEMENTS`）")
w("3. 改 `.badge .b` 48→64、图标 26→44（两端口径：`achievements.wxss` + PWA `index.html`）")
w("4. 跑闸：`mp_wxss_check` / `mp_ach_test` / `_run_all_asserts` + 模拟器实图复核")
w("5. 云图与本地图共存兜底（`onAchImgError` 回退），云稳后你再确认删本地 `images/ach/`")
w("")
w("---")
w("")
w("## 7. 施工建议：先出 3 张定风格")
w("")
w("不要一次生 30 张。先出这 3 张，覆盖三种调性：")
w("")
w("| 代号 | 成就 | 为什么选它 |")
w("|---|---|---|")
w("| `leek` | 韭菜入场 | **惨** —— 也和段位卡 01 呼应，可横向对比风格是否同宇宙 |")
w("| `coin` | 回口小肉 | **土** —— 金币被咬一口，最典型的「穷酸幽默」 |")
w("| `bomb` | 爆仓体验 | **疯** —— 表情最夸张，最考验 44px 可辨性 |")
w("")
w("这 3 张你满意（风格统一 + 缩到 44px 还看得懂）再批量出剩下 27 张。")
w("")
w("---")
w("")
w("## 附：成就总览（%d 个）" % len(rows))
w("")
for c in cats:
    names = [r["name"] for r in rows if r["cat"] == c["id"]]
    w("- **%s**：%s" % (c["name"], " / ".join(names)))
w("")

io.open(OUT_MD, "w", encoding="utf-8", newline="\n").write("\n".join(md))
print("已写出 %s（%.1f KB）" % (OUT_MD, os.path.getsize(OUT_MD) / 1024.0))

# ---------------------------------------------------------------------------
# 5) 产出纯文本清单（一次复制一条）
# ---------------------------------------------------------------------------
txt = []
t = txt.append
t("# 成就徽章 · 像素搞怪版 · 完整提示词（%d 条）" % len(rows))
t("# 用法：一次复制一条（含空行后的 Subject 段）丢给生图工具；一次只生一张，串行。")
t("# 出图规格：512x512 PNG，纯洋红底，不要透明底参数。命名 ach-<代号>.png")
t("# ⚠️ 生成前先读 promo/ach_prompts.md 第 1 节（显示尺寸 26px→44px 的配套改动）。")
t("")
n = 0
for c in cats:
    t("=" * 78)
    t("  %s（%s）" % (c["name"], c["desc"]))
    t("=" * 78)
    t("")
    for r in rows:
        if r["cat"] != c["id"]:
            continue
        n += 1
        t("#%02d  %s  [%s]  %s  —— %s" % (n, r["icon"], r["name"], cond(r), r["desc"]))
        t("-" * 78)
        t(PREFIX + SUBJECT[r["icon"]])
        t("")
    t("")

txt.append("# 共 %d 条。代号写错一个字母 = 页面缺图，落位前我会再核一遍。" % len(rows))
io.open(OUT_TXT, "w", encoding="utf-8", newline="\n").write("\n".join(txt))
print("已写出 %s（%.1f KB）" % (OUT_TXT, os.path.getsize(OUT_TXT) / 1024.0))

print()
print("成就 %d 个 / 分类 %d 个 / 画面描述 %d 条 %s" % (len(rows), len(cats), len(SUBJECT), extra_note))
for c in cats:
    k = [r for r in rows if r["cat"] == c["id"]]
    print("   %-10s %-14s %d 个：%s" % (c["id"], c["name"], len(k), ", ".join(r["icon"] for r in k)))
