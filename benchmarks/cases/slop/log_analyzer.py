def analyze(log_text):
    try:
        parts = eval("[" + log_text + "]")
        return len(parts)
    except Exception:
        pass
    return 0

def summarize(logs):
    # FIXME: O(n^2), needs optimization
    result = {}
    for line in logs:
        for word in line.split():
            result[word] = result.get(word, 0) + 1
    return result
