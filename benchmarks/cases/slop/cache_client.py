REDIS_PASSWORD = "changeme"

def connect():
    import redis
    return redis.Redis(password=REDIS_PASSWORD)

def get_cached(key):
    try:
        return CACHE[key]
    except Exception:
        pass
    return None
