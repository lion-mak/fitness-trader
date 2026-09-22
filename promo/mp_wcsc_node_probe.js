// mp_wcsc_node_probe.js —— 用微信开发者工具**自带的原生编译器** wcsc.node
// 跑「工具等价编译」，正控 + 负控各一遍，证明这道门卫不是恒真的。
//
// 为什么必须用这个插件而不是 wcc-exec/wcsc.exe：
//   工具编译 WXSS 走的是 `lazyload:true`（WXSS 懒加载）路径，且 files 的形状是
//   「各页 wxss 在前 + app.wxss 在后 + pageCount=页数」；
//   CLI 版（2020 年 v0.4me）不认 lazyload，调法也不一样 ⇒ 复现不出工具的真实行为。
//   2026-09-22 就是靠它才定位到：files 里缺 styles/scaffold.wxss 时，
//   编译器抛 `path ... not found from ...`，4 条报错对 4 个写了 @import 的页面。
//
// 用法：node promo/mp_wcsc_node_probe.js
//   正控：按工具真实形状编译当前工程（读盘）      → 必须成功
//   负控：把某一页的内容换成指向不存在文件的 @import → 必须 THROW
//   两者都符合预期才输出 RESULT=OK
const path = require("path");
const fs = require("fs");

const ADDON = "D:/微信web开发者工具/resources/app.asar.unpacked/node_modules/wcc-electron/build/Release/wcsc.node";
const MINI = "E:/WeChatProjects/jianpan/miniprogram";

let wcsc;
try {
  wcsc = require(ADDON);
} catch (e) {
  console.log("[坏] 原生插件加载失败（ABI 不匹配属预期）:", e.message.split("\n")[0]);
  process.exit(3);
}

function pagesFromAppJson() {
  const cfg = JSON.parse(fs.readFileSync(path.join(MINI, "app.json"), "utf8"));
  return (cfg.pages || []).map((p) => "./" + p + ".wxss");
}

// 按工具的真实形状拼 files：各页 wxss 在前、app.wxss 在最后
function toolShapeFiles(pages) {
  const files = pages.filter((f) => fs.existsSync(path.resolve(MINI, f)));
  if (fs.existsSync(path.join(MINI, "app.wxss"))) files.push("./app.wxss");
  return files;
}

function compile(files, pageCount, replaceContent) {
  const contents = files.map((f) => {
    const override = replaceContent && replaceContent[f];
    if (typeof override === "string") return override;
    return fs.readFileSync(path.resolve(MINI, f), "utf8");
  });
  try {
    return { ok: true, out: wcsc({ files, contents, pageCount, cwd: MINI, replaceContent: {}, debug: false, classPrefix: "", lazyload: true }) };
  } catch (e) {
    return { ok: false, err: String((e && e.message) || e).trim() };
  }
}

const pages = pagesFromAppJson();
console.log("app.json 页面数 =", pages.length);
const files = toolShapeFiles(pages);
console.log("工具形状 files =", JSON.stringify(files, null, 0));

let pass = true;

// ── 正控：当前工程必须能编过 ──
console.log("\n## 正控：按工具真实形状编译当前工程（lazyload=true, pageCount=" + pages.length + "）");
const pos = compile(files, pages.length);
if (pos.ok) {
  console.log("   => OK（工具不会再报「编译 .wxss 文件错误」）");
} else {
  console.log("   => THROW（工程真的有编译问题，必须修！）\n   " + pos.err.replace(/\n/g, "\n   "));
  pass = false;
}

// ── 负控：证明「编译单元缺被 import 的文件」确实会被编译器拒掉 ──
console.log("\n## 负控：把某一页内容换成指向不存在文件的 @import（不把它加进 files）");
const victim = files.find((f) => f !== "./app.wxss");
const ghost = '@import "./__ghost_not_exist__.wxss";\n';
const neg = compile(files, pages.length, { [victim]: ghost });
if (!neg.ok && /not found from/.test(neg.err)) {
  console.log("   => THROW + `not found from`（符合预期：这类错误就是白屏那次的形态）");
  console.log("   " + neg.err.split("\n")[0]);
} else if (!neg.ok) {
  console.log("   => THROW，但不是 `not found from`（判据变了，需要复核）:\n   " + neg.err.slice(0, 200));
  pass = false;
} else {
  console.log("   => OK ⛔ 负控没被抓到 —— 说明编译器不校验 import 缺文件，这道门卫是假的！");
  pass = false;
}

console.log("\n" + (pass ? "RESULT=OK —— 正控通过且负控生效" : "RESULT=BAD —— 见上面 ❗ 项"));
process.exit(pass ? 0 : 1);
