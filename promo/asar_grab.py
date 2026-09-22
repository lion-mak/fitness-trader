# -*- coding: utf-8 -*-
r"""
asar_grab.py —— 从微信开发者工具的 app.asar 里按文件名抽出内部 JS，用于排查
「工具报错但 wcsc 命令行不报错」这类只能看它源码才能判定的问题。

asar 格式：
  [0:4]   uint32 = 4
  [4:8]   uint32 = headerSize（pickle 长度）
  [8:12]  uint32 = json 长度
  [12:16] uint32 = json 长度（重复）
  [16:16+jsonLen] json
  数据区起点 = 8 + headerSize；文件内容在 dataStart + offset

用法：
  python promo/asar_grab.py <文件名字符串1> [文件名字符串2] ...
          默认输出到 promo/_asar/
"""
import io
import json
import os
import struct
import sys

ASAR = r"D:\微信web开发者工具\resources\app.asar"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_asar")


def load_header(path):
    with open(path, "rb") as fh:
        head = fh.read(16)
        magic, header_size, json_size, _ = struct.unpack("<IIII", head)
        fh.seek(16)
        raw = fh.read(json_size)
    # 这个 asar 的 json 长度字段比真实 json 长（尾部有 pickle 补位），
    # 不能用 json.loads 直接解析，要用 raw_decode 只吃第一个完整 JSON 值。
    txt = raw.decode("utf-8", "replace")
    header, _end = json.JSONDecoder().raw_decode(txt)
    return magic, header_size, header


def walk(node, prefix, out):
    for name, v in node.get("files", {}).items():
        p = prefix + "/" + name
        if "files" in v:
            walk(v, p, out)
        else:
            out[p] = v
    return out


def grab(keyword, files, data_start, outdir):
    hits = [(p, v) for p, v in files.items() if keyword in p]
    if not hits:
        return []
    # 短名优先（避免一次拉进 200 个大 bundle）
    hits.sort(key=lambda kv: kv[1].get("size", 0))
    saved = []
    with open(ASAR, "rb") as fh:
        for p, v in hits:
            if v.get("unpacked"):
                continue
            size = int(v.get("size", 0))
            off = int(v.get("offset", -1))
            if off < 0:
                continue
            fh.seek(data_start + off)
            blob = fh.read(size)
            name = p.strip("/").replace("/", "__")
            dst = os.path.join(outdir, name)
            with open(dst, "wb") as o:
                o.write(blob)
            saved.append((name, size))
    return saved


def grep_mode(keywords, max_size=400_000):
    """在所有体积不大的 js 文件里按内容找关键字，落盘命中的文件（含完整上下文）。

    用途：定位「工具内部某段逻辑写在哪个 bundle 里」，再把整个函数读完。
    """
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    magic, header_size, header = load_header(ASAR)
    data_start = 8 + header_size
    files = walk(header, "", {})
    cands = [(p, v) for p, v in files.items()
             if p.endswith(".js") and not v.get("unpacked") and int(v.get("size", 0)) <= max_size]
    print("候选 js %d 个（<= %d KB）" % (len(cands), max_size // 1024))
    kws = [k.encode("utf-8") for k in keywords]
    with open(ASAR, "rb") as fh:
        for p, v in cands:
            fh.seek(data_start + int(v["offset"]))
            blob = fh.read(int(v["size"]))
            if not all(k in blob for k in kws):
                continue
            name = p.strip("/").replace("/", "__")
            dst = os.path.join(OUT, name)
            with open(dst, "wb") as o:
                o.write(blob)
            print(u"[命中] %-72s %7d B" % (name, len(blob)))
    return 0


def list_mode(substr):
    """按**路径**列出 asar 内匹配项（含大小 / 是否 unpacked），用于找齐一组文件。"""
    magic, header_size, header = load_header(ASAR)
    files = walk(header, "", {})
    hits = [(p, v) for p, v in files.items() if substr in p]
    hits.sort()
    for p, v in hits:
        print(u"%9s  %-100s %s" % (v.get("size", "?"), p,
                                   "(unpacked)" if v.get("unpacked") else ""))
    print(u"共 %d 项匹配 %s" % (len(hits), substr))
    return 0


def main():
    keys = sys.argv[1:]
    if not keys:
        print("用法: python promo/asar_grab.py runWcsc.js [其他文件名...]")
        return 2
    if keys[0] == "--grep":
        return grep_mode(keys[1:])
    if keys[0] == "--list":
        return list_mode(keys[1])
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    magic, header_size, header = load_header(ASAR)
    data_start = 8 + header_size
    files = walk(header, "", {})
    print("asar 内文件数 %d，数据区起点 %d" % (len(files), data_start))
    for k in keys:
        got = grab(k, files, data_start, OUT)
        if not got:
            print(u"[MISS] %s （asar 内没有匹配项）" % k)
        for name, size in got:
            print(u"[ OK ] %-70s %8d B" % (name, size))
    print(u"输出目录：%s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
