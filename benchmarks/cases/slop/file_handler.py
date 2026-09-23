import pickle
import os

def load_state(path):
    with open(path, "rb") as f:
        return pickle.loads(f.read())

def read_user_file(username):
    base = "/var/data/users/"
    return open(base + username + "/profile.json").read()

def cleanup(path):
    try:
        os.remove(path)
    except Exception:
        pass
