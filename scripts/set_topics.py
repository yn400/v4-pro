"""
尝试通过 GitHub API 设置仓库 Topics。
需要 GITHUB_TOKEN 环境变量或个人访问令牌。
如果没设置，会打印手动设置方法。

用法:
    python scripts/set_topics.py <github_token>
    # 或者
    $env:GITHUB_TOKEN="ghp_xxx"; python scripts/set_topics.py
"""
import json
import os
import sys
from urllib.request import Request, urlopen

REPO = "yn400/v4-pro"
TOPICS = [
    "vibe-coding",
    "code-quality",
    "ai-coding",
    "static-analysis",
    "security-audit",
    "python",
    "llm",
    "pipeline",
]

def set_topics(token: str) -> bool:
    url = f"https://api.github.com/repos/{REPO}/topics"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.mercy-preview+json",
        "Content-Type": "application/json",
        "User-Agent": "v4-pro-setup-script",
    }
    data = json.dumps({"names": TOPICS}).encode()
    req = Request(url, data=data, headers=headers, method="PUT")
    try:
        with urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"✅ Topics set successfully: {result.get('names', [])}")
            return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        if hasattr(e, 'code') and e.code == 401:
            print("   The token is invalid or expired.")
        return False


if __name__ == "__main__":
    token = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_TOKEN", "")
    if token:
        set_topics(token)
    else:
        print("=" * 60)
        print("GitHub Topics 设置指南")
        print("=" * 60)
        print()
        print("要手动设置 Topics：")
        print(f"  1. 打开 https://github.com/{REPO}")
        print("  2. 在 About 区域点击 ⚙️ (齿轮图标)")
        print("  3. 粘贴以下 Topics：")
        for t in TOPICS:
            print(f"     • {t}")
        print("  4. 点击 Save")
        print()
        print("或者生成一个 Token 后运行：")
        print("    python scripts/set_topics.py <your-github-token>")
