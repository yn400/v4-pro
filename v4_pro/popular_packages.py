"""
热门包名单 — typosquatting（碰瓷包）检测的比对基准。

幻觉包名高度集中在仿冒这些知名包。名单是静态快照、内置离线可用，
按需可随版本更新。判断一个名字是否可疑用编辑距离（Levenshtein），
不要求名单完备 —— 仿冒不在名单里的冷门包收益低、少见。
"""

PYPI_POPULAR = frozenset({
    # Web 框架
    "django", "flask", "fastapi", "tornado", "starlette", "sanic",
    "bottle", "pyramid", "aiohttp", "falcon",
    # 数据科学
    "numpy", "pandas", "scipy", "matplotlib", "seaborn", "plotly",
    "scikit-learn", "statsmodels", "polars", "pyarrow", "sympy",
    # AI / LLM
    "torch", "tensorflow", "keras", "transformers", "datasets",
    "openai", "anthropic", "langchain", "langgraph", "llama-index",
    "accelerate", "peft", "diffusers", "onnx", "onnxruntime",
    # HTTP / 网络
    "requests", "urllib3", "httpx", "aiofiles", "websockets",
    "websocket-client", "grpcio", "paramiko", "curl-cffi",
    # API / 服务
    "uvicorn", "gunicorn", "celery", "redis", "rq", "dramatiq",
    # 数据库
    "sqlalchemy", "alembic", "psycopg2", "psycopg2-binary", "pymysql",
    "mysqlclient", "pymongo", "motor", "peewee", "tortoise-orm",
    "elasticsearch", "cassandra-driver",
    # 工具链
    "setuptools", "wheel", "pip", "packaging", "pip-tools",
    "build", "twine", "cython", "poetry", "hatch", "uv",
    # 测试 / 质量
    "pytest", "pytest-cov", "pytest-asyncio", "mock", "coverage",
    "tox", "hypothesis", "black", "ruff", "mypy", "pylint", "flake8",
    "isort", "pre-commit",
    # 配置 / 序列化
    "pyyaml", "toml", "tomli", "python-dotenv", "pydantic",
    "pydantic-settings", "dataclasses-json", "orjson", "ujson",
    "msgpack", "configparser", "marshmallow", "jsonschema",
    # 加密 / 安全
    "cryptography", "pyjwt", "passlib", "bcrypt", "argon2-cffi",
    "itsdangerous",
    # 爬虫 / 解析
    "scrapy", "beautifulsoup4", "bs4", "lxml", "html5lib",
    "selectolax", "playwright", "selenium", "pyppeteer",
    # CLI / 终端
    "click", "typer", "rich", "tqdm", "colorama", "questionary",
    # 云 / 基础设施
    "boto3", "botocore", "azure-storage-blob", "google-cloud-storage",
    "kubernetes", "docker", "terraform-compliance",
    # 图像 / 多媒体
    "pillow", "opencv-python", "imageio", "moviepy", "soundfile",
    "librosa", "torchaudio", "torchvision",
    # 模板 / 前端桥
    "jinja2", "markupsafe", "werkzeug",
    # Notebook / 交互
    "jupyter", "notebook", "ipython", "ipykernel", "jupyterlab",
    "nbformat", "streamlit", "gradio", "dash", "panel",
    # 任务队列 / 调度
    "apscheduler", "schedule", "airflow", "prefect", "dagster",
    # 日志 / 监控
    "loguru", "structlog", "sentry-sdk", "prometheus-client",
    "opentelemetry-api", "opentelemetry-sdk",
    # 工具杂项
    "six", "dateutil", "python-dateutil", "pytz", "tzdata", "attrs",
    "cachetools", "decorator", "docutils", "jinja", "pathlib2",
    "python-magic", "watchdog", "fabric", "invoke", "shellingham",
    "authlib", "httpcore", "anyio", "sniffio", "certifi", "charset-normalizer",
    "idna", "typing-extensions", "zipp", "soupsieve", "multidict",
    "yarl", "frozenlist", "aiosignal", "async-timeout", "greenlet",
    "protobuf", "grpcio-tools", "thrift", "pika", "confluent-kafka",
    "kafka-python", "h5py", "tables", "openpyxl", "xlsxwriter",
    "python-docx", "python-pptx", "pymupdf", "pdfplumber", "reportlab",
    "weasyprint", "markdown", "mistune", "bleach", "textual",
})

NPM_POPULAR = frozenset({
    # 框架
    "react", "react-dom", "react-native", "vue", "nuxt", "svelte",
    "solid-js", "preact", "angular", "@angular/core", "@angular/common",
    "next", "remix", "astro", "gatsby", "alpinejs", "jquery",
    # 服务端
    "express", "koa", "fastify", "hapi", "nest.js", "@nestjs/core",
    "adonis", "hono", "polka",
    # 工具库
    "lodash", "underscore", "ramda", "axios", "node-fetch", "got",
    "superagent", "ky", "moment", "dayjs", "date-fns", "luxon",
    "rxjs", "zx", "uuid", "nanoid", "crypto-js", "bcryptjs", "jsonwebtoken",
    # 状态管理
    "redux", "react-redux", "@reduxjs/toolkit", "zustand", "jotai",
    "recoil", "mobx", "valtio", "pinia", "vuex",
    # 构建
    "typescript", "eslint", "prettier", "oxlint", "biome",
    "webpack", "vite", "rollup", "esbuild", "swc", "@swc/core",
    "parcel", "tsup", "unbuild", "tsx", "babel", "@babel/core",
    "postcss", "sass", "less", "tailwindcss", "autoprefixer",
    # 测试
    "jest", "vitest", "mocha", "chai", "jasmine", "playwright",
    "puppeteer", "cypress", "@testing-library/react", "ava", "karma",
    # 包管理 / 运行时
    "npm", "yarn", "pnpm", "bun", "nodemon", "pm2",
    "concurrently", "cross-env", "dotenv",
    # UI
    "tailwind", "bootstrap", "antd", "mui", "@mui/material",
    "chakra-ui", "@chakra-ui/react", "radix-ui", "@radix-ui/react",
    "shadcn", "element-plus", "vuetify", "quasar",
    # 数据 / API
    "prisma", "@prisma/client", "sequelize", "typeorm", "knex",
    "mongoose", "drizzle-orm", "kysely", "graphql",
    "apollo", "@apollo/client", "trpc", "@trpc/server", "socket.io",
    "ws", "zod", "yup", "joi", "ajv", "class-validator",
    # 工具杂项
    "glob", "fs-extra", "rimraf", "shelljs", "execa", "ora",
    "chalk", "kleur", "picocolors", "commander", "inquirer", "yargs",
    "cac", "minimist", "semver", "yaml", "js-yaml", "cheerio",
    "jsdom", "happy-dom", "marked", "markdown-it", "handlebars",
    "ejs", "pug", "mustache", "sharp", "jimp", "pdfkit",
})
