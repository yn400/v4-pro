# 贡献指南 · Contributing

感谢你考虑为 V4 Pro 做贡献！🎉

## 如何贡献

### 🐛 报告 Bug
1. 确认该 Bug 尚未被报告（搜索 Issues）
2. 创建新 Issue，使用 Bug 报告模板
3. 附上复现步骤、运行环境、预期/实际结果

### 💡 提出新功能
1. 先创建 Feature Request Issue，讨论设计方案
2. 获得 maintainer 反馈后再开始编码

### 🔧 提交 PR
1. Fork 本仓库
2. 从 `main` 创建分支：`git checkout -b feat/your-feature`
3. 开发并确保测试通过：`python -m pytest`
4. 格式化代码：`pip install ruff && ruff check .`
5. 提交 PR，关联 Issue 编号

## 开发环境

```bash
git clone https://github.com/yn400/v4-pro.git
cd v4-pro
pip install -e ".[dev]"
python -m pytest  # 全部 56 个测试应通过
```

## 代码规范

- Python ≥ 3.10
- 类型注解必须齐全
- 所有函数/类需有 docstring（中英文均可）
- 遵循 ruff 约定的代码风格

## 提交信息规范

```
<type>: <简短描述>

<可选详细说明>
```

type: feat / fix / docs / style / refactor / test / chore / ci

## 协议

提交代码即表示你同意将其以 MIT 协议授权。
