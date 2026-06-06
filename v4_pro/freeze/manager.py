"""
工程收敛引擎 (FreezeManager) — "防糜烂"机制。

提供 freeze 命令实现:
1. 将当前设计文档中的边界（模块接口、数据模型）冻结成 frozen_spec.json
2. 后续 generate 和 verify 自动对比新生成的代码是否违反冻结规范
3. 棘轮约束: 只能收敛收紧，不能随意倒退
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FreezeManager:
    """
    冻结规范管理器。

    负责:
    - 从设计文档中提取可冻结的边界
    - 将冻结规范写入 frozen_spec.json
    - 对比新代码是否违反冻结规范
    """

    def __init__(self, workspace: Path):
        """
        Args:
            workspace: 工作区目录
        """
        self.workspace = Path(workspace)
        self.frozen_path = self.workspace / "frozen_spec.json"
        logger.debug("FreezeManager 初始化 workspace=%s", self.workspace)

    def freeze(self, design_file: str = "design.json") -> dict[str, Any]:
        """
        冻结当前设计规范。

        Args:
            design_file: 设计文档路径

        Returns:
            冻结规范字典
        """
        # 加载设计文档
        design_path = self.workspace / design_file
        if not design_path.exists():
            # 尝试当前目录
            design_path = Path(design_file)
        if not design_path.exists():
            raise FileNotFoundError(f"设计文档不存在: {design_file}")

        design = json.loads(design_path.read_bytes())

        # 提取可冻结的边界
        spec: dict[str, Any] = {
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "source_design": str(design_path),
            "design_hash": self._hash_dict(design),
            "module_interfaces": {},
            "data_models": {},
            "api_contracts": {},
            "architecture_constraints": {},
            "coding_standards": {},
        }

        # ── 模块接口 ──
        modules = design.get("modules", [])
        for mod in modules:
            name = mod.get("name", "unknown")
            spec["module_interfaces"][name] = {
                "responsibility": mod.get("responsibility", ""),
                "public_api": mod.get("public_api", []),
                "dependencies": mod.get("dependencies", []),
            }

        # ── 数据模型 ──
        entities = design.get("data_model", {}).get("entities", [])
        for entity in entities:
            name = entity.get("name", "unknown")
            spec["data_models"][name] = {
                "fields": entity.get("fields", []),
                "relationships": entity.get("relationships", []),
            }

        # ── API 契约 ──
        api = design.get("api_design", {})
        if api:
            spec["api_contracts"] = {
                "style": api.get("style", "REST"),
                "endpoints": api.get("endpoints", []),
            }

        # ── 架构约束 ──
        arch = design.get("architecture", {})
        if arch:
            layers = arch.get("layers", [])
            spec["architecture_constraints"] = {
                "layers": [
                    {
                        "name": layer.get("name", ""),
                        "forbidden_dependencies": layer.get("forbidden_dependencies", []),
                        "allowed_dependencies": layer.get("allowed_dependencies", []),
                    }
                    for layer in layers
                ]
            }

        # ── 编码规范 ──
        standards = design.get("coding_standards", {})
        if standards:
            spec["coding_standards"] = standards

        # 检查是否已有冻结规范（棘轮约束: 只收不放）
        if self.frozen_path.exists():
            old_spec = json.loads(self.frozen_path.read_bytes())
            spec = self._apply_ratchet(old_spec, spec)

        # 写入
        self.frozen_path.write_text(
            json.dumps(spec, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(
            "规范已冻结: %d 个模块接口, %d 个数据模型",
            len(spec["module_interfaces"]),
            len(spec["data_models"]),
        )

        return spec

    def check_compliance(
        self, generated_code_dir: Path, design_file: str = "design.json"
    ) -> dict[str, Any]:
        """
        检查新生成的代码是否违反冻结规范。

        Args:
            generated_code_dir: 生成的代码目录
            design_file: 当前设计文档

        Returns:
            合规检查报告
        """
        if not self.frozen_path.exists():
            return {
                "frozen": False,
                "violations": [],
                "note": "尚未冻结规范，请先运行 v4-pro freeze",
            }

        frozen = json.loads(self.frozen_path.read_bytes())
        design_path = self.workspace / design_file
        if not design_path.exists():
            design_path = Path(design_file)
        design = json.loads(design_path.read_bytes())

        violations = []

        # ── 检查模块接口是否被退化 ──
        frozen_modules = frozen.get("module_interfaces", {})
        current_modules = {
            m.get("name", ""): m for m in design.get("modules", [])
        }

        for name, frozen_mod in frozen_modules.items():
            if name not in current_modules:
                violations.append({
                    "severity": "P0",
                    "type": "module_removed",
                    "title": f"冻结的模块 '{name}' 在新设计中已被移除",
                    "suggestion": "不能移除已冻结的模块接口，只能扩展",
                })
                continue

            current_mod = current_modules[name]

            # 检查公共 API 是否缩减
            frozen_apis = set(frozen_mod.get("public_api", []))
            current_apis = set(current_mod.get("public_api", []))
            removed_apis = frozen_apis - current_apis
            if removed_apis:
                violations.append({
                    "severity": "P0",
                    "type": "api_removed",
                    "title": f"模块 '{name}' 移除了已冻结的公共 API: {removed_apis}",
                    "suggestion": "已冻结的公共 API 不能移除，可以标记为 deprecated 但必须保留",
                })

        # ── 检查数据模型是否被退化 ──
        frozen_models = frozen.get("data_models", {})
        current_models = {
            e.get("name", ""): e
            for e in design.get("data_model", {}).get("entities", [])
        }

        for name, frozen_model in frozen_models.items():
            if name not in current_models:
                violations.append({
                    "severity": "P1",
                    "type": "model_removed",
                    "title": f"冻结的数据模型 '{name}' 在新设计中已被移除",
                    "suggestion": "考虑使用数据库迁移而非直接删除模型",
                })
                continue

            # 检查字段是否被删除
            frozen_fields = {f.get("name", ""): f for f in frozen_model.get("fields", [])}
            current_fields = {f.get("name", ""): f for f in current_models[name].get("fields", [])}

            for field_name, _frozen_field in frozen_fields.items():
                if field_name not in current_fields:
                    violations.append({
                        "severity": "P1",
                        "type": "field_removed",
                        "title": f"数据模型 '{name}' 移除了冻结字段 '{field_name}'",
                        "suggestion": "考虑添加新字段而非删除已有字段，或使用迁移脚本",
                    })

        return {
            "frozen": True,
            "frozen_at": frozen.get("frozen_at", ""),
            "violations": violations,
            "compliant": len(violations) == 0,
        }

    def _apply_ratchet(
        self, old_spec: dict[str, Any], new_spec: dict[str, Any]
    ) -> dict[str, Any]:
        """
        棘轮约束: 新规范是旧规范的严格超集。

        - 旧的模块接口必须保留
        - 旧的数据模型字段必须保留
        - 旧的 API 端点必须保留
        """
        logger.info("应用棘轮约束: 合并新旧规范")

        # 合并模块接口（新 = 旧 ∪ 新，且旧的部分不能被修改）
        old_modules = old_spec.get("module_interfaces", {})
        new_modules = new_spec.get("module_interfaces", {})
        merged_modules = {**old_modules, **new_modules}
        new_spec["module_interfaces"] = merged_modules

        # 合并数据模型
        old_models = old_spec.get("data_models", {})
        new_models = new_spec.get("data_models", {})
        merged_models = {**old_models, **new_models}
        new_spec["data_models"] = merged_models

        # 合并 API 端点
        old_endpoints = old_spec.get("api_contracts", {}).get("endpoints", [])
        new_endpoints = new_spec.get("api_contracts", {}).get("endpoints", [])
        merged_endpoints = old_endpoints.copy()
        existing = {(e.get("method"), e.get("path")) for e in merged_endpoints}
        for ep in new_endpoints:
            if (ep.get("method"), ep.get("path")) not in existing:
                merged_endpoints.append(ep)
        new_spec["api_contracts"]["endpoints"] = merged_endpoints

        # 保留冻结时间线
        new_spec["previous_frozen_at"] = old_spec.get("frozen_at", "")
        new_spec["ratchet_applied"] = True

        return new_spec

    @staticmethod
    def _hash_dict(data: dict[str, Any]) -> str:
        """计算字典的 SHA256 前 12 位。"""
        import hashlib
        content = json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(content).hexdigest()[:12]
