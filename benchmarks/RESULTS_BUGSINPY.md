# 基准 A — 真实人类 bug 检出与定位（BugsInPy）

- 数据: BugsInPy 真实开源项目 bug，5 个项目固定 seed 抽样 24 个
  （black / httpie / tornado / fastapi / cookiecutter）
- 方法: 用 pre-image blob 还原带缺陷版本完整文件，内置检测器扫描，
  行级定位 = P0/P1 发现落在修复删除行 ±3 行内

- **文件级命中（出现 P0/P1）**: 3/18 = **17%**
- **行级定位命中（±3 行）**: 0/18 = **0%**

按缺陷类别分解:
- other: 2/17 命中, 0/17 行级定位
- security: 1/1 命中, 0/1 行级定位

逐用例:
| 用例 | 类别 | 命中 | 行级定位 | 发现 |
|---|---|---|---|---|
| black#10 | other | False | False | - |
| black#17 | other | True | False | SEC/unsafe-deserialize:3292 |
| black#11 | other | True | False | SEC/unsafe-deserialize:3596 |
| black#21 | other | False | False | - |
| black#12 | security | True | False | SEC/unsafe-deserialize:3529 |
| httpie#1 | other | False | False | - |
| httpie#4 | other | False | False | - |
| httpie#3 | unparseable | unparseable | None | - |
| httpie#2 | other | False | False | - |
| httpie#5 | other | False | False | - |
| tornado#10 | unparseable | unparseable | None | - |
| tornado#11 | fetch-failed | fetch-failed | None | - |
| tornado#8 | unparseable | unparseable | None | - |
| tornado#14 | fetch-failed | fetch-failed | None | - |
| tornado#2 | fetch-failed | fetch-failed | None | - |
| fastapi#4 | other | False | False | - |
| fastapi#5 | other | False | False | - |
| fastapi#12 | other | False | False | - |
| fastapi#11 | other | False | False | - |
| fastapi#1 | other | False | False | - |
| cookiecutter#4 | other | False | False | - |
| cookiecutter#1 | other | False | False | - |
| cookiecutter#2 | other | False | False | - |
| cookiecutter#3 | other | False | False | - |
