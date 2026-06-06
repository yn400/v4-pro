"""
决策追踪日志 (Trace Logger)。

每次运行 research / define / design / generate / verify 时，
自动在 trace.log 中追加一条 JSON Lines 记录。

这实现了需求中的"可追溯决策链"：
任何时候都能回溯每一步用了什么 Prompt、什么模型参数、输入了什么。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TraceLogger:
    """
    JSON Lines 格式的决策追踪日志。

    每条记录包含:
    - 时间戳
    - 步骤名
    - Prompt 模板版本（文件 hash）
    - 大模型参数（temperature / max_tokens / model）
    - 输入摘要
    - 输出 JSON 的 commit hash
    """

    def __init__(self, workspace: Path):
        """
        Args:
            workspace: 工作区目录路径
        """
        self.workspace = Path(workspace)
        self.log_path = self.workspace / "trace.log"
        logger.debug("TraceLogger 初始化 log_path=%s", self.log_path)

    def log_step(
        self,
        step: str,
        input_summary: str,
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 0,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        记录一个步骤的决策追踪。

        Args:
            step: 步骤名 (research/define/design/generate/verify/audit/freeze)
            input_summary: 输入摘要（截断到 500 字符）
            model: 使用的模型名
            temperature: temperature 参数
            max_tokens: max_tokens 参数
            extra: 额外信息

        Returns:
            写入的追踪记录
        """
        # 计算对应输出文件的 hash
        output_hash = self._compute_output_hash(step)

        # 计算 Prompt 模板的版本 hash
        prompt_version = self._compute_prompt_version(step)

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "model": model,
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            "prompt_template_version": prompt_version,
            "input_summary": input_summary[:500],
            "output_hash": output_hash,
            **(extra or {}),
        }

        # 追加写入
        self._append(record)

        logger.info("追踪记录已写入: step=%s hash=%s", step, output_hash)
        return record

    def read_all(self) -> list[dict[str, Any]]:
        """
        读取所有追踪记录。

        Returns:
            追踪记录列表（按时间排序）
        """
        if not self.log_path.exists():
            return []

        records = []
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("trace.log 中有无效行，已跳过")
        return records

    def get_last_step(self, step: str) -> dict[str, Any] | None:
        """
        获取最近一次指定步骤的追踪记录。

        Args:
            step: 步骤名

        Returns:
            最近一条记录，或 None
        """
        records = self.read_all()
        for record in reversed(records):
            if record.get("step") == step:
                return record
        return None

    def _append(self, record: dict[str, Any]) -> None:
        """追加一条记录到 trace.log。"""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _compute_output_hash(self, step: str) -> str:
        """
        计算步骤输出文件的 SHA256 前 12 位。

        文件映射:
            research → research.json
            design   → design.json
            generate → generate.json
            verify   → verify.json
            define   → define.json
        """
        filename_map = {
            "research": "research.json",
            "design": "design.json",
            "generate": "generate.json",
            "verify": "verify.json",
            "define": "define.json",
            "freeze": "frozen_spec.json",
        }
        filename = filename_map.get(step, f"{step}.json")
        filepath = self.workspace / filename

        if not filepath.exists():
            return "n/a"

        content = filepath.read_bytes()
        return hashlib.sha256(content).hexdigest()[:12]

    def _compute_prompt_version(self, step: str) -> str:
        """
        计算 Prompt 模板文件的 SHA256 前 8 位。

        模板文件在 prompts/ 目录下，如 prompts/research.prompt。
        """
        # 尝试找到 prompts 目录
        candidates = [
            Path("prompts") / f"{step}.prompt",
            Path(__file__).parent.parent.parent / "prompts" / f"{step}.prompt",
        ]

        for candidate in candidates:
            if candidate.exists():
                return hashlib.sha256(candidate.read_bytes()).hexdigest()[:8]

        return "unknown"
