# v4-pro 内置检测器基准报告

> 合成标注集（15 文件 / 31 预期发现）+ 标准库真实人类代码（10 文件）。
> 内置确定性检测器（SEC/SA/SMELL），allow_external=False。复现：`python benchmarks/run_benchmark.py`

- **检出率（recall）**: 35/35 = **100.0%**
- **合成集意外发现（超预期报告）**: 0 例
- **干净集误报（标准库代码上出现 P0/P1）**: 2/10 文件

## 干净集误报明细
- `dataclasses.py`: SEC/exec-dynamic(P1)
- `selectors.py`: SA/bare-except(P1), SA/bare-except(P1), SA/bare-except(P1)

## 逐用例

| 用例 | 预期 | 命中 | 超预期 |
|---|---|---|---|
| api_client.py | 2 | 2 | 0 |
| auth_service.py | 4 | 4 | 0 |
| cache_client.py | 2 | 2 | 0 |
| config_loader.py | 2 | 2 | 0 |
| data_pipeline.py | 2 | 2 | 0 |
| email_sender.py | 2 | 2 | 0 |
| file_handler.py | 2 | 2 | 0 |
| image_utils.py | 3 | 3 | 0 |
| log_analyzer.py | 2 | 2 | 0 |
| notification_service.py | 2 | 2 | 0 |
| payment_api.py | 3 | 3 | 0 |
| report_generator.py | 2 | 2 | 0 |
| session_store.py | 3 | 3 | 0 |
| token_utils.py | 2 | 2 | 0 |
| user_controller.py | 2 | 2 | 0 |
