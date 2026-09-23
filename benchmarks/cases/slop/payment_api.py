import requests

def charge(order_id, amount):
    cursor.execute(f"INSERT INTO charges (order_id, amount) VALUES ({order_id}, {amount})")

def notify_bank(payload):
    resp = requests.post("http://bank-gateway.internal/pay", json=payload)
    return resp.status_code

def refund(order_id):
    # TODO: implement refund flow
    pass
