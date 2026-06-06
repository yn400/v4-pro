"""Verify all config files in v4-pro project."""
import json
import os
import sys

import yaml

errors = 0

# Helper
def check(path, msg, predicate=None):
    global errors
    if not os.path.exists(path):
        print(f'  MISSING: {path}')
        errors += 1
        return
    try:
        content = open(path, encoding='utf-8').read()
    except Exception as e:
        print(f'  READ ERROR: {path}: {e}')
        errors += 1
        return
    if predicate and not predicate(content):
        print(f'  CONTENT ERROR: {path}')
        errors += 1
        return
    print(f'  OK: {msg}')

# 1. YAML workflows
print('[1/8] Workflow YAML files:')
for w in ['.github/workflows/ci.yml','.github/workflows/pr-check.yml',
          '.github/workflows/publish.yml','.github/workflows/docker-publish.yml']:
    check(w, w, lambda c: yaml.safe_load(c) is not None)

# 2. JSON presets
print('[2/8] Project presets:')
for p in ['presets/web-app.json','presets/python-package.json',
          'presets/embedded-iot.json','presets/mobile-app.json']:
    check(p, p, lambda c: 'preset' in json.loads(c))

# 3. Dockerfile
print('[3/8] Dockerfile:')
check('Dockerfile', 'Dockerfile', lambda c: all(x in c for x in ['FROM python:','WORKDIR','pip install','ENTRYPOINT']))

# 4. CHANGELOG
print('[4/8] CHANGELOG:')
check('CHANGELOG.md', 'CHANGELOG.md', lambda c: '0.1.0' in c)

# 5. CONTRIBUTING
print('[5/8] CONTRIBUTING:')
check('CONTRIBUTING.md', 'CONTRIBUTING.md')

# 6. LICENSE
print('[6/8] LICENSE:')
check('LICENSE', 'LICENSE (MIT)', lambda c: 'MIT' in c)

# 7. ci_check
print('[7/8] ci_check module:')
check('v4_pro/ci_check.py', 'v4_pro/ci_check.py', lambda c: 'main' in c)

# 8. .gitignore
print('[8/8] .gitignore:')
check('.gitignore', '.gitignore', lambda c: all(x in c for x in ['__pycache__','.env','audit-test','temp_']))

print(f'\nTotal: {errors} errors' if errors else '\nAll checks passed!')
sys.exit(errors)
