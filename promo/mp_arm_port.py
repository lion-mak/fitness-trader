# -*- coding: utf-8 -*-
"""
mp_arm_port.py —— 确保开发者工具的自动化端口处于「已 arm 且会话就绪」状态。

逻辑全部在 mp_ws.ensure_port()（共享给 _probe_sel.py / mp_rect_market.py 等），
本文件只是命令行入口，方便手工排查。

用法：python promo/mp_arm_port.py [--port 9420] [--wait 60]
退出码：0 = 就绪；1 = 失败（会打印下一步该跑什么）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mp_ws                                                    # noqa: E402


def arg(flag, default):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


if __name__ == "__main__":
    sys.exit(0 if mp_ws.ensure_port(int(arg("--port", "9420")),
                                    float(arg("--wait", "60"))) else 1)
