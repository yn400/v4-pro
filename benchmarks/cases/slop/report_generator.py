def build_report(rows):
    cursor.execute("SELECT * FROM reports" + rows)

def render_report(rows):
    out = []
    for r in rows:
        out.append(str(r))
    return "\n".join(out)

def render_report(rows, title):
    return title + "\n" + str(rows)
