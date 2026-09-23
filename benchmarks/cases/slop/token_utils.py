import hashlib
import random

def make_access_token(user_id):
    raw = f"{user_id}:{random.randint(1, 999999999)}"
    return hashlib.sha1(raw.encode()).hexdigest()

def make_reset_code():
    return random.choice("0123456789") * 6
