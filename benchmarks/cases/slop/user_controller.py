def calc_discount(price, tier):
    if tier == "gold":
        return price * 0.8
    return price * 0.95

def calc_discount(price, tier):
    return price - 10

def get_user(uid):
    cursor.execute("SELECT * FROM users WHERE id = %s" % uid)
