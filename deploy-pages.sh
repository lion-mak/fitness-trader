#!/usr/bin/env bash
# 健身交易员 -> GitHub Pages 部署脚本
# 由 Lion 执行 / Mak 复现用。在仓库目录右键 "Git Bash Here" 运行:  bash deploy-pages.sh
# 前置: 填好下方 GH_USER / GH_TOKEN（Personal Access Token, 勾 repo 权限）
set -e

GH_USER="${GH_USER:-YourGitHubUsername}"
GH_TOKEN="${GH_TOKEN:-}"   # 勿把明文 token 提交进仓库

if [ -z "$GH_TOKEN" ]; then
  echo ">>> 请先设置 GH_TOKEN 环境变量:  GH_TOKEN=xxxx bash deploy-pages.sh"
  exit 1
fi

# 1) 提交最新代码
git add -A
git commit -m "Deploy 健身交易员 to GitHub Pages" || echo "(nothing to commit)"

# 2) 关联远程（若未关联）
if ! git remote | grep -q origin; then
  git remote add origin "https://${GH_TOKEN}@github.com/${GH_USER}/jianpan-ghpages.git"
fi

# 3) 推送当前分支
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git push -u origin "$BRANCH"

echo ">>> 代码已推送。下一步在 GitHub 网页操作:"
echo "    1) 打开 https://github.com/${GH_USER}/jianpan-ghpages/settings/pages"
echo "    2) Source 选分支 $BRANCH + 目录 /(root)"
echo "    3) Save, 约 1 分钟后站点出现在:"
echo "       https://${GH_USER}.github.io/jianpan-ghpages/"
echo ">>> 手机数据迁移: 旧沙箱域下的 localStorage 需在新站用 App 内「导出 JSON -> 导入」恢复"
