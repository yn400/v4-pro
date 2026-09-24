# 基准 C — 真实攻击包信号覆盖（OSV 数据）

- 数据: OSV PyPI 转储 MAL 公告（OpenSSF/厂商披露的真实供应链攻击），
  去重 11,744 个，固定 seed 采样 150 个
- 方法: 逐个构造 import 场景，跑完整 PhantomDependencyChecker 管线（实时注册表查证）

- **信号覆盖率（剔除网络失败后）**: 107/150 = **71.3%**
- 网络失败未能核实: 0 个（不计入覆盖率，重跑可续查）
- **P0 直接拦截率**: 107/150 = **71.3%**
- 信号分解: {"PHANTOM/pypi": 107}
- 未触发任何信号: 43 个（多为'正常名字 + 包已下架/存在已久'——行为分析不在范围内）

未触发名单（诚实公示）:
- discord-booster
- py-randpushint
- data-parser-utils
- test-typo-pypi
- base-local-planner
- glob-to-regexp
- websocket-clietn
- py-pywvisahydra
- ai-spellcheckers
- py-remaskvisa
- discord-anarchy
- ddiscord-webhook
- python-binancce
- solution-maker
- bytekafka-0-0-15
- ipa-user-collector
- dify-api
- pip-goodthing
- utils-hex
- timekeeper-verifier
- eth-keccak
- python-requirements
- httpx-advanced3
- vectordb-engine
- celery-flower
- metemask-sdk
- py-intnvidiagui
- heimdal-credentials
- sf-silly-goose-requests
- heroku-tl
- py-hackedhttpstring
- python-amazon-doc-utils
- py-superrecc
- stats-helpers
- py-infoponghttp
- scraper-npm
- cache-compat-utils
- do-not-install-this-package-002
- py-randvirtual
- tcloud-python-sdk
- coinmate-api
- py-ckrd
- py-adcpu
