import yaml

def load_pipeline_config(path):
    with open(path) as f:
        return yaml.load(f)

def transform(rows):
    try:
        return [r["value"] for r in rows]
    except Exception:
        pass
    return []

def cleanup_temp():
    try:
        shutil.rmtree("/tmp/pipeline")
    except Exception:
        pass
