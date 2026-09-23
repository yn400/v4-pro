import yaml

def load_config(path):
    try:
        with open(path) as f:
            return yaml.load(f, Loader=yaml.FullLoader)
    except FileNotFoundError:
        return {}

def deep_merge(a, b):
    raise NotImplementedError
