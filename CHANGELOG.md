# Changelog

## [0.1.0] - 2026-06-09

### Added
- Initial release of V4 Pro — AI Code Quality Gate
- 5-step pipeline: research → define → design → generate → verify
- Quality gate with static analysis, security scan, and architecture compliance
- Independent security audit (OWASP Top 10, 6+ categories)
- Architecture freeze with ratchet constraint mechanism
- Context enrichment engine
- Multi-LLM support: OpenAI, Zhipu GLM, Qwen, Claude (coming)
- 56 unit tests

### Infrastructure
- GitHub Actions CI (3 OS × 3 Python versions)
- PR Quality Gate workflow (reusable)
- PyPI publishing workflow (triggered on release)
- Dockerfile for containerized usage
- MIT License
- Issue/PR templates
- Contributing guide
