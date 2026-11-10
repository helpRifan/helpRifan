"""Draw a star-history-style chart of cumulative commits, month by month.

Needs GITHUB_TOKEN in the environment. Usage:
    python scripts/commit_history.py <username> <output.svg>
"""
import datetime as dt
import json
import os
import sys
import urllib.request

API = "https://api.github.com/graphql"


def gql(query, variables):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
            "Content-Type": "application/json",
            "User-Agent": "commit-history-chart",
        },
    )
    with urllib.request.urlopen(req) as r:
        out = json.load(r)
    if "errors" in out:
        raise SystemExit(out["errors"])
    return out["data"]


def monthly_commits(user):
    created = gql("query($u:String!){user(login:$u){createdAt}}", {"u": user})["user"]["createdAt"]
    start = dt.date.fromisoformat(created[:10]).replace(day=1)
    today = dt.date.today()
    months = []
    m = start
    while m <= today:
        months.append(m)
        m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)

    counts = {}
    for i in range(0, len(months), 12):  # 12 months per request
        chunk = months[i:i + 12]
        fields = []
        for j, mo in enumerate(chunk):
            nxt = (mo.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
            fields.append(
                f'm{j}: contributionsCollection(from:"{mo}T00:00:00Z", to:"{nxt - dt.timedelta(days=1)}T23:59:59Z")'
                "{ totalCommitContributions restrictedContributionsCount }"
            )
        data = gql("query($u:String!){user(login:$u){" + " ".join(fields) + "}}", {"u": user})["user"]
        for j, mo in enumerate(chunk):
            counts[mo] = data[f"m{j}"]["totalCommitContributions"]
    return [(mo, counts[mo]) for mo in months]


def render(user, points):
    W, H = 800, 380
    L, R, T, B = 70, 30, 60, 50
    pw, ph = W - L - R, H - T - B

    cum, total = [], 0
    for mo, c in points:
        total += c
        cum.append((mo, total))
    ymax = max(total, 1)
    step = next(s for s in [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000] if ymax / s <= 6)
    ytop = ((ymax + step - 1) // step) * step

    n = len(cum)
    x = lambda i: L + (pw * i / max(n - 1, 1))
    y = lambda v: T + ph - ph * v / ytop

    pts = [(x(i), y(v)) for i, (_, v) in enumerate(cum)]
    # smooth curve (Catmull-Rom -> Bezier)
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(p1[1] + (p2[1] - p0[1]) / 6, p1[1]))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, max(p2[1] - (p3[1] - p1[1]) / 6, p2[1]))
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    area = d + f" L{pts[-1][0]:.1f},{T + ph} L{pts[0][0]:.1f},{T + ph} Z"

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        'font-family="Segoe UI, Helvetica, Arial, sans-serif">',
        "<defs><linearGradient id='g' x1='0' y1='0' x2='0' y2='1'>"
        "<stop offset='0' stop-color='#7aa2f7' stop-opacity='0.45'/>"
        "<stop offset='1' stop-color='#7aa2f7' stop-opacity='0'/></linearGradient></defs>",
        f'<rect width="{W}" height="{H}" rx="12" fill="#1a1b27"/>',
        f'<text x="{L}" y="36" fill="#70a5fd" font-size="20" font-weight="600">Commit History</text>',
        f'<text x="{W - R}" y="36" fill="#a9b1d6" font-size="14" text-anchor="end">'
        f'{total:,} commits · @{user}</text>',
    ]
    for k in range(0, ytop + 1, step):
        yy = y(k)
        out.append(f'<line x1="{L}" y1="{yy:.1f}" x2="{W - R}" y2="{yy:.1f}" stroke="#2f3549" stroke-dasharray="4 4"/>')
        out.append(f'<text x="{L - 10}" y="{yy + 4:.1f}" fill="#787c99" font-size="12" text-anchor="end">{k:,}</text>')
    for i, (mo, _) in enumerate(cum):
        if mo.month == 1 or i == 0:
            xx = x(i)
            out.append(f'<line x1="{xx:.1f}" y1="{T}" x2="{xx:.1f}" y2="{T + ph}" stroke="#2f3549"/>')
            out.append(f'<text x="{xx:.1f}" y="{T + ph + 22}" fill="#787c99" font-size="12" text-anchor="middle">{mo.year}</text>')
    out.append(f'<path d="{area}" fill="url(#g)"/>')
    out.append(f'<path d="{d}" fill="none" stroke="#7aa2f7" stroke-width="3" stroke-linecap="round"/>')
    # dot at the end of each year + today
    for i, (mo, v) in enumerate(cum):
        if mo.month == 12 or i == n - 1:
            out.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" fill="#bb9af7" stroke="#1a1b27" stroke-width="2"/>')
    out.append(
        f'<text x="{W - R}" y="{H - 12}" fill="#565f89" font-size="11" text-anchor="end">'
        f"updated {dt.date.today():%d %b %Y}</text>"
    )
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    user, path = sys.argv[1], sys.argv[2]
    pts = monthly_commits(user)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(user, pts))
    print(f"{sum(c for _, c in pts)} commits over {len(pts)} months -> {path}")
