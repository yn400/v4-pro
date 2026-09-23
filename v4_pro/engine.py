"""
五步法工作流引擎。

V4 Pro 的核心 — 将 vibe coding 流程化为五个有序步骤:
  research → define → design → generate → verify

每一步的输入/输出均为 JSON 文件，存放在工作区目录下。
支持上下文增强：自动从历史 JSON 中提取信息注入后续 Prompt。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from v4_pro.config import Settings, get_settings
from v4_pro.context_enricher import ContextEnricher
from v4_pro.llm.base import AbstractLLM, LLMResponse
from v4_pro.llm.factory import create_llm
from v4_pro.prompts.loader import PromptLoader
from v4_pro.trace import TraceLogger

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    V4 Pro 五步法工作流引擎。

    用法:
        engine = WorkflowEngine()
        engine.research("做一个电商App")           # Step 1
        engine.define("research.json")             # Step 2
        engine.design("define.json")               # Step 3
        engine.generate("design.json")             # Step 4
        engine.verify("./generated/")              # Step 5
    """

    # 各步骤对应的 Prompt 模板名
    STEP_PROMPTS = {
        "research": "research",
        "design": "design",
        "generate": "generate",
        "verify": "verify",
    }

    def __init__(
        self,
        settings: Settings | None = None,
        llm: AbstractLLM | None = None,
        prompts_dir: str | Path | None = None,
    ):
        """
        Args:
            settings: V4 Pro 配置（默认全局单例）
            llm: LLM 适配器（默认根据配置自动创建）
            prompts_dir: Prompt 模板目录（默认自动探测项目根下的 prompts/）
        """
        self.settings = settings or get_settings()
        self.workspace = self.settings.ensure_workspace()
        self._llm = llm  # 懒初始化：在需要时才创建

        # 自动探测 prompts 目录：优先传入路径 → v4_pro 包同级 prompts/ → 当前目录
        if prompts_dir is None:
            prompts_dir = self._find_prompts_dir()
        self.prompt_loader = PromptLoader(prompts_dir)
        self.enricher = ContextEnricher(self.workspace)
        self.tracer = TraceLogger(self.workspace)

        logger.info("WorkflowEngine 初始化完成 workspace=%s", self.workspace)

    @property
    def llm(self) -> AbstractLLM:
        """懒初始化 LLM — verify/audit 等纯本地命令不需要 LLM。"""
        if self._llm is None:
            self._llm = create_llm(self.settings)
        return self._llm

    # ── Step 1: Research ──────────────────────────────────────

    def research(self, requirement: str) -> dict[str, Any]:
        """
        Step 1 — 市场研究。

        调用 LLM 分析用户需求，输出竞品分析、痛点、机会窗口。

        Args:
            requirement: 用户需求描述

        Returns:
            研究结果 JSON
        """
        logger.info("=" * 60)
        logger.info("Step 1/5: RESEARCH — 市场研究")
        logger.info("需求: %s", requirement)

        # 构建 Prompt
        system_prompt = self.prompt_loader.render("research", requirement=requirement)
        user_prompt = f"请分析以下需求:\n{requirement}"

        # 调用 LLM
        response = self.llm.single_turn(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 解析 JSON 输出
        result = self._parse_json_response(response, "research")
        result["_meta"] = {
            "step": "research",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requirement": requirement,
            "model": response.model,
            "usage": response.usage,
        }

        # 保存到工作区
        self._save_step_output("research.json", result)

        # 记录追踪
        self.tracer.log_step(
            step="research",
            input_summary=requirement[:200],
            model=response.model,
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
        )

        logger.info("Research 完成 ✓ → %s/research.json", self.workspace)
        return result

    # ── Step 2: Define ────────────────────────────────────────

    def define(self, research_file: str = "research.json") -> dict[str, Any]:
        """
        Step 2 — 需求定义。

        将研究结果转化为结构化的产品需求定义。
        这一步主要做数据转换，不调用 LLM（可选 LLM 增强）。

        Args:
            research_file: 研究结果 JSON 文件名或路径

        Returns:
            需求定义 JSON
        """
        logger.info("=" * 60)
        logger.info("Step 2/5: DEFINE — 需求定义")

        # 加载研究结果
        research = self._load_json(research_file)

        # 提取关键信息，构建结构化需求定义
        result = {
            "product_goal": research.get("recommendation", {}).get("reasoning", ""),
            "target_users": research.get("market_analysis", {}).get("target_users", []),
            "core_features": self._extract_features(research),
            "pain_points_addressed": [
                p.get("pain_point", "")
                for p in research.get("user_pain_points", [])
            ],
            "success_metrics": [
                "用户增长率",
                "功能完成率",
                "代码质量评分 (P0 问题 = 0)",
            ],
            "_meta": {
                "step": "define",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": str(research_file),
            },
        }

        self._save_step_output("define.json", result)

        self.tracer.log_step(
            step="define",
            input_summary=f"from {research_file}",
            model="n/a (数据转换)",
            temperature=0,
            max_tokens=0,
        )

        logger.info("Define 完成 ✓ → %s/define.json", self.workspace)
        return result

    # ── Step 3: Design ────────────────────────────────────────

    def design(self, define_file: str = "define.json") -> dict[str, Any]:
        """
        Step 3 — 架构设计。

        调用 LLM 输出架构图、技术栈选型、模块划分、数据模型。

        Args:
            define_file: 需求定义 JSON 文件名

        Returns:
            设计文档 JSON
        """
        logger.info("=" * 60)
        logger.info("Step 3/5: DESIGN — 架构设计")

        define_data = self._load_json(define_file)
        research_data = self._load_json("research.json")

        # 上下文增强
        context = self.enricher.enrich()

        # 构建 Prompt（注入上下文）
        research_str = json.dumps(research_data, ensure_ascii=False, indent=2)
        requirement_str = define_data.get("product_goal", "")

        system_prompt = self.prompt_loader.render_with_context(
            "design",
            context=context,
            research_json=research_str,
            requirement=requirement_str,
        )
        user_prompt = "请基于以上研究结果和需求，输出完整的产品设计文档。"

        response = self.llm.single_turn(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        result = self._parse_json_response(response, "design")
        result["_meta"] = {
            "step": "design",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_define": str(define_file),
            "model": response.model,
            "usage": response.usage,
            "context_injected": bool(context),
        }

        self._save_step_output("design.json", result)

        self.tracer.log_step(
            step="design",
            input_summary=f"from {define_file}",
            model=response.model,
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
        )

        logger.info("Design 完成 ✓ → %s/design.json", self.workspace)
        return result

    # ── Step 4: Generate ──────────────────────────────────────

    def generate(self, design_file: str = "design.json") -> dict[str, Any]:
        """
        Step 4 — 代码生成。

        调用 LLM 按设计文档生成完整项目代码。

        Args:
            design_file: 设计文档 JSON 文件名

        Returns:
            生成结果（包含文件列表）
        """
        logger.info("=" * 60)
        logger.info("Step 4/5: GENERATE — 代码生成")

        design_data = self._load_json(design_file)

        # 检查冻结规范
        frozen = self._load_json("frozen_spec.json", required=False)
        context = self.enricher.enrich()
        if frozen:
            context["frozen_specs"] = json.dumps(frozen, ensure_ascii=False, indent=2)

        design_str = json.dumps(design_data, ensure_ascii=False, indent=2)

        system_prompt = self.prompt_loader.render_with_context(
            "generate",
            context=context,
            design_json=design_str,
        )
        user_prompt = "请根据设计文档生成完整的项目代码。"

        response = self.llm.single_turn(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            # 代码生成需要更多 token，但不超过 API 上限 128K
            max_tokens=min(self.settings.max_tokens * 2, 128_000),
        )

        result = self._parse_json_response(response, "generate")

        # 将生成的文件写入磁盘
        generated_dir = self.workspace / "generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        files = result.get("files", [])
        for f in files:
            file_path = generated_dir / f["path"]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f["content"], encoding="utf-8")
            logger.info("  写入文件: %s", file_path)

        result["_meta"] = {
            "step": "generate",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_design": str(design_file),
            "model": response.model,
            "usage": response.usage,
            "files_generated": len(files),
            "output_dir": str(generated_dir),
        }

        self._save_step_output("generate.json", result)

        self.tracer.log_step(
            step="generate",
            input_summary=f"from {design_file}, {len(files)} files generated",
            model=response.model,
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
        )

        logger.info("Generate 完成 ✓ → %s/generated/ (%d 个文件)", self.workspace, len(files))
        return result

    # ── Step 5: Verify ────────────────────────────────────────

    def verify(
        self,
        code_path: str = "./generated/",
        design_file: str = "design.json",
        force: bool = False,
        fail_on: str | None = None,
        diff_base: str | None = None,
        baseline_path: str | None = None,
        save_baseline: str | None = None,
        phantom_offline: bool = False,
    ) -> dict[str, Any]:
        """
        Step 5 — 质量门禁。

        五项检查: 静态分析、安全扫描、AI 代码异味、幻觉依赖、架构合规。

        Args:
            code_path: 代码目录路径
            design_file: 设计文档（用于架构合规检查）
            force: 是否强制通过（即使有问题）
            fail_on: 门禁阈值（P0/P1/P2/P3），None 时读 .v4pro.json，默认 P0
            diff_base: git 基线引用（如 main）— 只检查相对该引用变更的行
            baseline_path: 基线报告 — 存量问题标记为 baseline，不阻断
            save_baseline: 把本次结果保存为基线文件
            phantom_offline: 幻觉依赖检测离线模式（跳过注册表查询）

        Returns:
            验证报告 JSON
        """
        from v4_pro import gate as gate_infra
        from v4_pro.phantom import PhantomDependencyChecker
        from v4_pro.smells import AiSmellDetector
        from v4_pro.verify.arch_compliance import ArchComplianceChecker
        from v4_pro.verify.security_scan import SecurityScanner
        from v4_pro.verify.static_analysis import StaticAnalyzer

        logger.info("=" * 60)
        logger.info("Step 5/5: VERIFY — 质量门禁")

        code_dir = self._resolve_path(code_path)
        gate_cfg = gate_infra.load_gate_config(code_dir if code_dir.is_dir() else Path.cwd())
        fail_threshold = fail_on or gate_cfg.get("fail_on", "P0")
        test_paths = gate_cfg.get("test_paths", [])
        # 设计文档可选 — 没有就跳过架构合规检查
        try:
            design_data = self._load_json(design_file)
        except FileNotFoundError:
            logger.info("设计文档 %s 不存在，跳过架构合规检查", design_file)
            design_data = {}

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "code_path": str(code_dir),
            "checks": {},
            "summary": {},
        }

        # 检查 1: 静态分析
        logger.info("  [1/5] 静态分析...")
        static = StaticAnalyzer().analyze(code_dir, extra_test_paths=test_paths)
        report["checks"]["static_analysis"] = static

        # 检查 2: 安全扫描
        logger.info("  [2/5] 安全扫描...")
        security = SecurityScanner().scan(code_dir, extra_test_paths=test_paths)
        report["checks"]["security_scan"] = security

        # 检查 3: AI 代码异味
        logger.info("  [3/5] AI 代码异味...")
        smells = AiSmellDetector().scan(code_dir, extra_test_paths=test_paths)
        report["checks"]["ai_smell"] = smells

        # 检查 4: 幻觉依赖
        logger.info("  [4/5] 幻觉依赖检测...")
        phantom_cfg = gate_cfg.get("phantom", {})
        phantom = PhantomDependencyChecker(
            offline=phantom_offline or phantom_cfg.get("offline", False),
            allowlist=phantom_cfg.get("allowlist", []),
            timeout=phantom_cfg.get("timeout", 5),
            ttl_exists=phantom_cfg.get("cache_ttl_exists", 30),
            ttl_missing=phantom_cfg.get("cache_ttl_missing", 7),
        ).scan(code_dir)
        report["checks"]["phantom_dependency"] = phantom

        # 检查 5: 架构合规
        logger.info("  [5/5] 架构合规检查...")
        arch = ArchComplianceChecker(design_data).check(code_dir)
        report["checks"]["arch_compliance"] = arch

        # ── 汇总与门禁判定 ──
        all_issues = []
        for _check_name, check_result in report["checks"].items():
            for issue in check_result.get("issues", []):
                issue["_check"] = _check_name
                all_issues.append(issue)

        # 排除路径
        exclude_patterns = gate_cfg.get("exclude", [])
        if exclude_patterns:
            all_issues = [
                i for i in all_issues
                if not gate_infra.path_excluded(Path(i["file"]), code_dir, exclude_patterns)
            ]

        # 禁用规则
        disabled = set(gate_cfg.get("disable_rules", []))
        if disabled:
            all_issues = [i for i in all_issues if i.get("rule_id") not in disabled]

        # 行内抑制注释
        supp_cache: dict[str, dict[int, set[str]]] = {}
        kept_after_suppression = []
        for issue in all_issues:
            f = issue.get("file", "")
            if f not in supp_cache:
                supp_map: dict[int, set[str]] = {}
                try:
                    src = Path(f).read_text(encoding="utf-8")
                    # 抑制标记在注释里 — 必须用原始源码解析（掩码会抹掉标记）
                    supp_map = gate_infra.build_suppression_map(src)
                except (OSError, UnicodeDecodeError):
                    pass
                supp_cache[f] = supp_map
            if not gate_infra.is_suppressed(issue, supp_cache[f]):
                kept_after_suppression.append(issue)
        all_issues = kept_after_suppression

        # diff 模式 — 只看变更行
        diff_applied = False
        if diff_base:
            changed = gate_infra.changed_lines(code_dir, diff_base)
            if changed:
                before = len(all_issues)
                all_issues = gate_infra.filter_by_diff(all_issues, changed, code_dir)
                diff_applied = True
                logger.info("diff 模式: %d → %d（只统计变更行）", before, len(all_issues))

        # 基线模式 — 存量问题不阻断
        if baseline_path:
            baseline = gate_infra.load_baseline(Path(baseline_path))
            gate_infra.mark_baseline(all_issues, baseline)
        else:
            for issue in all_issues:
                issue["baseline"] = False

        # 回填到各 check（保持 schema 一致）
        kept_keys = {(i["file"], i["line"], i.get("rule_id", "")) for i in all_issues}
        for check in report["checks"].values():
            check["issues"] = [
                i for i in check.get("issues", [])
                if (i.get("file", ""), int(i.get("line", 0) or 0), i.get("rule_id", "")) in kept_keys
            ]

        counts = {s: 0 for s in ("P0", "P1", "P2", "P3")}
        for issue in all_issues:
            counts[issue.get("severity", "P3")] = counts.get(issue.get("severity", "P3"), 0) + 1

        active = [i for i in all_issues if not i.get("baseline")]
        threshold_hits = [
            i for i in active
            if gate_infra.severity_at_or_above(i.get("severity", "P3"), fail_threshold)
        ]
        blocked = bool(threshold_hits) and not force

        report["summary"] = {
            "total_issues": len(all_issues),
            "p0_blockers": counts["P0"],
            "p1_warnings": counts["P1"],
            "p2_suggestions": counts["P2"],
            "p3_info": counts["P3"],
            "baseline_count": len(all_issues) - len(active),
            "fail_on": fail_threshold,
            "threshold_hits": len(threshold_hits),
            "diff_mode": diff_applied,
            "phantom_packages": sum(
                1 for i in active if str(i.get("rule_id", "")).startswith("PHANTOM/")
                and i.get("severity") == "P0"
            ),
            "passed": not blocked,
            "blocked": blocked,
            "force_bypass": force and bool(threshold_hits),
        }

        if save_baseline:
            Path(save_baseline).write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info("基线已保存: %s", save_baseline)

        self._save_step_output("verify.json", report)

        self.tracer.log_step(
            step="verify",
            input_summary=f"code_path={code_dir}, issues={len(all_issues)}, blocked={blocked}",
            model="n/a (质量门禁)",
            temperature=0,
            max_tokens=0,
        )

        if blocked:
            logger.warning(
                "质量门禁未通过！%d 个问题达到阈值 %s。使用 --force 可强制通过。",
                len(threshold_hits),
                fail_threshold,
            )
        else:
            logger.info("质量门禁通过 ✓")

        return report

    # ── 辅助方法 ──────────────────────────────────────────────

    def _parse_json_response(self, response: LLMResponse, step: str) -> dict[str, Any]:
        """从 LLM 回复中提取 JSON。"""
        content = response.content.strip()

        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块中提取
        if "```json" in content:
            start = content.index("```json") + 7
            try:
                end = content.index("```", start)
                try:
                    return json.loads(content[start:end].strip())
                except (json.JSONDecodeError, ValueError):
                    pass
            except ValueError:
                pass

        if "```" in content:
            # 尝试任意代码块
            parts = content.split("```")
            for i in range(1, len(parts), 2):
                try:
                    return json.loads(parts[i].strip())
                except json.JSONDecodeError:
                    continue

        raise ValueError(
            f"Step '{step}': LLM 返回的内容无法解析为 JSON。\n"
            f"原始响应前 500 字符:\n{content[:500]}"
        )

    def _save_step_output(self, filename: str, data: dict[str, Any]) -> Path:
        """保存步骤输出到工作区。"""
        filepath = self.workspace / filename
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 计算 hash 用于追踪
        content_hash = hashlib.sha256(
            json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:12]
        logger.debug("  保存: %s (hash=%s)", filepath, content_hash)
        return filepath

    def _load_json(self, filename: str, required: bool = True) -> dict[str, Any]:
        """从工作区加载 JSON 文件。"""
        filepath = self._resolve_path(filename)
        if not filepath.exists():
            if required:
                raise FileNotFoundError(
                    f"找不到 {filepath}。请先运行前置步骤。"
                )
            return {}
        return json.loads(filepath.read_text(encoding="utf-8"))

    def _resolve_path(self, path_str: str) -> Path:
        """将路径字符串解析为绝对路径。"""
        p = Path(path_str)
        if p.is_absolute():
            return p
        # 先尝试工作区
        workspace_candidate = self.workspace / p
        if workspace_candidate.exists():
            return workspace_candidate
        # 再尝试当前目录
        return Path.cwd() / p

    @staticmethod
    def _find_prompts_dir() -> Path:
        """自动探测 prompts 目录位置。"""
        # 1. v4_pro 包的兄弟目录 prompts/
        pkg_dir = Path(__file__).resolve().parent  # v4_pro/
        sibling = pkg_dir.parent / "prompts"
        if sibling.exists():
            return sibling
        # 2. 当前工作目录下
        cwd = Path.cwd() / "prompts"
        if cwd.exists():
            return cwd
        # 3. 尝试 packages 安装位置
        import v4_pro
        installed = Path(v4_pro.__file__).resolve().parent.parent / "prompts"
        if installed.exists():
            return installed
        raise FileNotFoundError(
            "找不到 prompts/ 目录。请在项目根目录下运行，或通过 --prompts-dir 指定路径。"
        )

    @staticmethod
    def _extract_features(research: dict[str, Any]) -> list[str]:
        """从研究结果中提取核心功能列表。"""
        features = []
        opportunities = research.get("opportunity_windows", [])
        for opp in opportunities:
            approach = opp.get("suggested_approach", "")
            if approach:
                features.append(approach)
        if not features:
            features = ["核心功能（待定义）"]
        return features
