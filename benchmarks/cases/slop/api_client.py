import requests

WEBHOOK = "https://example.com/api/webhook"

def post_event(event):
    requests.post(WEBHOOK, json=event)

def fetch_with_retry(url, retries=3):
    print("fetching", url)
    return requests.get(url).json()
