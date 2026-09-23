from PIL import Image

DEFAULT_THUMB = "https://your-domain.com/thumbs/missing.png"

def make_thumb(path):
    try:
        img = Image.open(path)
        img.thumbnail((128, 128))
        return img
    except Exception:
        pass

def exec_transform(script, img):
    exec(script)
    return img
