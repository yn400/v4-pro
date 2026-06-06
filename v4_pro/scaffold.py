"""
项目脚手架生成器。

v4-pro init 命令的实现 — 生成标准化的项目目录结构。
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def init_project(target_dir: str | Path = ".") -> Path:
    """
    初始化 V4 Pro 项目脚手架。

    生成以下目录结构:
        {target_dir}/
        ├── v4_workspace/       ← 工作区（所有中间产物）
        │   ├── generated/       ← 生成的代码
        │   └── trace.log        ← 决策追踪日志（运行时自动创建）
        ├── prompts/             ← Prompt 模板
        └── .env                 ← 环境配置（从 .env.example 复制）

    Args:
        target_dir: 目标目录，默认为当前目录

    Returns:
        创建的目录 Path
    """
    root = Path(target_dir).resolve()
    logger.info("初始化 V4 Pro 项目: %s", root)

    # 需要创建的目录
    dirs = [
        root / "v4_workspace",
        root / "v4_workspace" / "generated",
        root / "prompts",
    ]

    created = []
    skipped = []

    for d in dirs:
        if d.exists():
            skipped.append(str(d))
        else:
            d.mkdir(parents=True, exist_ok=True)
            created.append(str(d))
            logger.info("  创建目录: %s", d)

    # 创建 .gitkeep 确保空目录被 git 跟踪
    for d in dirs:
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")

    # 检查是否已有 .env，没有则提示
    env_path = root / ".env"
    env_example = root / ".env.example"
    if not env_path.exists():
        if env_example.exists():
            logger.info("  提示: 复制 .env.example → .env 并填入 API Key")
        else:
            logger.info("  提示: 创建 .env 文件并配置 V4_OPENAI_API_KEY")

    # 统计
    logger.info(
        "初始化完成: %d 个目录已创建, %d 个已存在",
        len(created),
        len(skipped),
    )

    return root
