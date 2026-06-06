"""
冻结规范模块测试。
"""

import json
import tempfile
from pathlib import Path

import pytest

from v4_pro.freeze.manager import FreezeManager


class TestFreezeManager:
    """FreezeManager 单元测试。"""

    def _make_design(self, ws: Path) -> dict:
        """创建测试用的设计文档。"""
        design = {
            "modules": [
                {
                    "name": "auth",
                    "responsibility": "用户认证",
                    "public_api": ["login", "logout", "register"],
                    "dependencies": ["database"],
                },
                {
                    "name": "user",
                    "responsibility": "用户管理",
                    "public_api": ["get_user", "update_user"],
                    "dependencies": ["auth", "database"],
                },
            ],
            "data_model": {
                "entities": [
                    {
                        "name": "User",
                        "fields": [
                            {"name": "id", "type": "int", "description": "主键"},
                            {"name": "username", "type": "str", "description": "用户名"},
                            {"name": "email", "type": "str", "description": "邮箱"},
                        ],
                        "relationships": [],
                    }
                ],
            },
            "api_design": {
                "style": "REST",
                "endpoints": [
                    {"method": "POST", "path": "/api/login", "description": "登录"},
                    {"method": "GET", "path": "/api/users", "description": "用户列表"},
                ],
            },
            "architecture": {
                "layers": [
                    {
                        "name": "controller",
                        "forbidden_dependencies": ["dao"],
                        "allowed_dependencies": ["service"],
                    },
                ],
            },
            "coding_standards": {
                "max_line_length": 120,
                "naming_style": "snake_case",
                "require_type_annotations": True,
            },
        }
        (ws / "design.json").write_text(
            json.dumps(design, ensure_ascii=False),
            encoding="utf-8"
        )
        return design

    def test_freeze_creates_file(self):
        """测试 freeze 创建 frozen_spec.json。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            self._make_design(ws)

            manager = FreezeManager(ws)
            spec = manager.freeze("design.json")

            assert (ws / "frozen_spec.json").exists()
            assert "module_interfaces" in spec
            assert "data_models" in spec

    def test_freeze_extracts_modules(self):
        """测试冻结提取模块接口。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            self._make_design(ws)

            manager = FreezeManager(ws)
            spec = manager.freeze("design.json")

            modules = spec["module_interfaces"]
            assert "auth" in modules
            assert "user" in modules
            assert modules["auth"]["public_api"] == ["login", "logout", "register"]

    def test_freeze_extracts_data_models(self):
        """测试冻结提取数据模型。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            self._make_design(ws)

            manager = FreezeManager(ws)
            spec = manager.freeze("design.json")

            models = spec["data_models"]
            assert "User" in models
            assert len(models["User"]["fields"]) == 3

    def test_ratchet_merges_old_and_new(self):
        """测试棘轮约束合并新旧规范。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            self._make_design(ws)

            manager = FreezeManager(ws)

            # 第一次冻结
            spec1 = manager.freeze("design.json")
            assert len(spec1["module_interfaces"]) == 2

            # 修改设计文档，添加新模块
            design = json.loads((ws / "design.json").read_bytes())
            design["modules"].append({
                "name": "payment",
                "responsibility": "支付处理",
                "public_api": ["pay", "refund"],
                "dependencies": ["user"],
            })
            (ws / "design.json").write_text(json.dumps(design, ensure_ascii=False), encoding="utf-8")

            # 第二次冻结（应该合并）
            spec2 = manager.freeze("design.json")
            assert len(spec2["module_interfaces"]) == 3  # auth + user + payment
            assert "payment" in spec2["module_interfaces"]
            assert spec2.get("ratchet_applied") is True

    def test_check_compliance_no_frozen(self):
        """测试未冻结时的合规检查。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            manager = FreezeManager(ws)

            result = manager.check_compliance(Path(tmp))
            assert result["frozen"] is False

    def test_check_compliance_module_removed(self):
        """测试检测模块被移除的违规。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            self._make_design(ws)

            manager = FreezeManager(ws)
            manager.freeze("design.json")

            # 修改设计文档，删除 auth 模块
            design = json.loads((ws / "design.json").read_bytes())
            design["modules"] = [
                m for m in design["modules"] if m["name"] != "auth"
            ]
            (ws / "design.json").write_text(json.dumps(design, ensure_ascii=False), encoding="utf-8")

            result = manager.check_compliance(Path(tmp))
            assert len(result["violations"]) >= 1
            assert result["compliant"] is False

    def test_freeze_design_not_found(self):
        """测试设计文档不存在时抛出异常。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            manager = FreezeManager(ws)

            with pytest.raises(FileNotFoundError):
                manager.freeze("nonexistent.json")
