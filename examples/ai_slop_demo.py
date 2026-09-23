"""
示例：一段典型的 "AI 一把梭" 生成代码。

这个文件故意包含了 AI 生成代码最常见的 8 类问题，
v4-pro 应当把它们全部检出。用于演示与自测：

    v4-pro verify --code ./examples/
"""

import os
import pickle
import random
import requests
import fastcsvparser  # AI 编造的包 — PyPI 上不存在（slopsquatting 风险）
import requets       # 碰瓷包 — 模仿 requests 的拼写

API_KEY = "sk-live-a1b2c3d4e5f6g7h8"  # AI 直接硬编码了一个"看起来真"的密钥
WEBHOOK_URL = "https://example.com/api/webhook"
DB_PASSWORD = "changeme"


def process_payment(amount):
    """处理支付。"""
    pass


def validate_card(card_number):
    raise NotImplementedError


def calculate_total(price, qty):
    return price * qty


def calculate_total(price, qty):
    # AI 修改时忘记删除旧版本 → 同名函数定义两次
    return price * qty * 1.06


def load_session(session_file):
    # AI 爱用 pickle 反序列化不可信数据
    with open(session_file, "rb") as f:
        return pickle.loads(f.read())


def generate_token():
    # AI 用非加密随机数生成"安全"令牌
    return str(random.randint(100000, 999999))


def fetch_user(user_id):
    try:
        resp = requests.get(f"http://internal-api/user/{user_id}")
        return resp.json()
    except Exception:
        pass  # 出错就当没发生


def run(query):
    # AI 拼接 SQL
    cursor.execute(f"SELECT * FROM users WHERE name = '{query}'")


def hash_password(pwd):
    import hashlib
    return hashlib.md5(pwd.encode()).hexdigest()

