#!/usr/bin/env python3
"""
generate_stats.py — draw self-updating stat SVGs from the GitHub GraphQL API,
in the monochrome style of the reference profile.

Outputs:
    stats.svg   hero total + active days + best week + weekly area sparkline
    streak.svg  current streak + longest streak, with date ranges
    langs.svg   top languages, two columns: by bytes (%) and by repos (count)
    year.svg    the contribution year as a labelled character grid + legend

Standard library only (urllib). Theme-aware via an internal <style> the README
sanitiser never touches. Deterministic: window pinned to whole UTC days, repos
filtered to privacy: PUBLIC.

Env: GITHUB_TOKEN (required), GH_LOGIN (optional; defaults to token owner).
"""
import os
import json
import datetime
import urllib.request
import urllib.error

API = "https://api.github.com/graphql"
TOKEN = os.environ["GITHUB_TOKEN"]
LOGIN = os.environ.get("GH_LOGIN", "").strip()

RAMP = " .`:-=+*cs#%@"          # shared with the portrait
LEGEND = [":", "+", "#", "@"]   # low -> high, for the year legend

# monochrome, theme-aware palette
STYLE = """
<style>
  .s{fill:#1f2328}  .m{fill:#59636e}  .t{fill:#d0d7de}
  .stk{stroke:#1f2328}  .trk{fill:#eaeef2}
  @media(prefers-color-scheme:dark){
    .s{fill:#e6edf3} .m{fill:#7d8590} .t{fill:#30363d}
    .stk{stroke:#e6edf3} .trk{fill:#21262d}
  }
</style>
"""
FONT = "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace"


def gql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": LOGIN or "stats-generator",
    })
    try:
        with urllib.request.urlopen(req) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"GraphQL HTTP {e.code}: {e.read().decode()[:500]}")
    if out.get("errors"):
        raise SystemExit("GraphQL errors: " + json.dumps(out["errors"]))
    return out["data"]


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg(w, h, inner):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" font-family="{FONT}">{STYLE}'
            f'<rect fill="none" width="{w}" height="{h}"/>{inner}</svg>')


def nice(iso):
    return datetime.date.fromisoformat(iso).strftime("%b %-d").lower()


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def whoami():
    return LOGIN or gql("{viewer{login}}", {})["viewer"]["login"]


def fetch_calendar(login):
    today = datetime.datetime.now(datetime.timezone.utc).date()
    frm = datetime.datetime.combine(today - datetime.timedelta(days=364),
                                    datetime.time(0, 0, 0), tzinfo=datetime.timezone.utc)
    to = datetime.datetime.combine(today, datetime.time(23, 59, 59),
                                   tzinfo=datetime.timezone.utc)
    q = """
    query($login:String!,$from:DateTime!,$to:DateTime!){
      user(login:$login){ contributionsCollection(from:$from,to:$to){
        contributionCalendar{ totalContributions
          weeks{ firstDay contributionDays{ date contributionCount weekday } } } } }
    }"""
    d = gql(q, {"login": login, "from": frm.isoformat(), "to": to.isoformat()})
    return d["user"]["contributionsCollection"]["contributionCalendar"]


def fetch_languages(login):
    """Return (by_bytes{name:{size}}, by_repos{name:count}) for PUBLIC non-forks."""
    q = """
    query($login:String!,$after:String){
      user(login:$login){ repositories(first:100,after:$after,ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC){
        pageInfo{ hasNextPage endCursor }
        nodes{ languages(first:15,orderBy:{field:SIZE,direction:DESC}){ edges{ size node{ name } } } } } }
    }"""
    by_bytes, by_repos, after = {}, {}, None
    while True:
        repos = gql(q, {"login": login, "after": after})["user"]["repositories"]
        for repo in repos["nodes"]:
            seen = set()
            for e in repo["languages"]["edges"]:
                nm = e["node"]["name"]
                by_bytes[nm] = by_bytes.get(nm, 0) + e["size"]
                seen.add(nm)
            for nm in seen:
                by_repos[nm] = by_repos.get(nm, 0) + 1
        if repos["pageInfo"]["hasNextPage"]:
            after = repos["pageInfo"]["endCursor"]
        else:
            break
    return by_bytes, by_repos


def flatten(cal):
    days = []
    for w in cal["weeks"]:
        for d in w["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    days.sort()
    return days


def streaks(days):
    longest = {"n": 0, "start": None, "end": None}
    run, run_start = 0, None
    for date, c in days:
        if c > 0:
            run_start = date if run == 0 else run_start
            run += 1
            if run > longest["n"]:
                longest = {"n": run, "start": run_start, "end": date}
        else:
            run, run_start = 0, None
    cur = {"n": 0, "start": None, "end": None}
    i = len(days) - 1
    if i >= 0 and days[i][1] == 0:
        i -= 1
    end = None
    while i >= 0 and days[i][1] > 0:
        end = end or days[i][0]
        cur = {"n": cur["n"] + 1, "start": days[i][0], "end": end}
        i -= 1
    return cur, longest


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------
def label(x, y, text, size=10, cls="m", ls=1.4):
    return (f'<text class="{cls}" x="{x}" y="{y}" font-size="{size}" '
            f'letter-spacing="{ls}">{esc(text)}</text>')


def build_stats(cal):
    W, H = 460, 138
    total = cal["totalContributions"]
    days = flatten(cal)
    active = sum(1 for _, c in days if c > 0)
    weeks = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]]
    best = max(weeks) if weeks else 0
    mx = max(weeks) or 1
    # area sparkline
    x0, x1, base, top = 24, W - 24, 118, 92
    n = len(weeks)
    pts = [(x0 + (x1 - x0) * (i / max(1, n - 1)), base - (base - top) * (v / mx))
           for i, v in enumerate(weeks)]
    line = " ".join(f'{x:.1f},{y:.1f}' for x, y in pts)
    area = f'M{pts[0][0]:.1f},{base} ' + " ".join(f'L{x:.1f},{y:.1f}' for x, y in pts) + f' L{pts[-1][0]:.1f},{base} Z'
    ex, ey = pts[-1]
    inner = (
        f'{label(24,34,"CONTRIBUTIONS · LAST YEAR")}'
        f'<text class="s" x="23" y="82" font-size="46" font-weight="700">{total:,}</text>'
        f'<text class="s" x="{W-24}" y="40" font-size="21" font-weight="700" text-anchor="end">{active}</text>'
        f'<text class="m" x="{W-24}" y="55" font-size="9.5" letter-spacing="1.2" text-anchor="end">ACTIVE DAYS</text>'
        f'<text class="s" x="{W-24}" y="76" font-size="21" font-weight="700" text-anchor="end">{best}</text>'
        f'<text class="m" x="{W-24}" y="91" font-size="9.5" letter-spacing="1.2" text-anchor="end">BEST WEEK</text>'
        f'<path class="trk" d="{area}"/>'
        f'<polyline class="stk" fill="none" stroke-width="1.6" points="{line}"/>'
        f'<circle class="s" cx="{ex:.1f}" cy="{ey:.1f}" r="2.6"/>'
    )
    return svg(W, H, inner)


def build_streak(cur, longest):
    W, H = 460, 120

    def block(x, lab, s):
        rng = ""
        if s["start"]:
            rng = nice(s["start"]) if s["start"] == s["end"] else f'{nice(s["start"])} → {nice(s["end"])}'
        return (
            f'<text class="m" x="{x}" y="30" font-size="9.5" letter-spacing="1.2">{lab}</text>'
            f'<text class="s" x="{x-1}" y="76" font-size="40" font-weight="700">{s["n"]}'
            f'<tspan class="m" font-size="14" font-weight="400"> days</tspan></text>'
            f'<text class="m" x="{x}" y="98" font-size="11">{esc(rng)}</text>')
    inner = (block(24, "CURRENT STREAK", cur)
             + '<rect class="t" x="232" y="22" width="1" height="80"/>'
             + block(252, "LONGEST STREAK", longest))
    return svg(W, H, inner)


def build_langs(by_bytes, by_repos):
    W = 460
    colL, colR = 24, 252
    barw = 96
    top = 44
    row = 26
    byte_items = sorted(by_bytes.items(), key=lambda kv: kv[1], reverse=True)[:5]
    repo_items = sorted(by_repos.items(), key=lambda kv: kv[1], reverse=True)[:5]
    tot_bytes = sum(by_bytes.values()) or 1
    max_repos = max(by_repos.values()) if by_repos else 1
    H = top + row * max(1, len(byte_items), len(repo_items)) + 14
    parts = [f'<text class="m" x="{colL}" y="26" font-size="9.5" letter-spacing="1.4">BY BYTES</text>',
             f'<text class="m" x="{colR}" y="26" font-size="9.5" letter-spacing="1.4">BY REPOS</text>']

    def rows(items, x, denom, is_pct, i0=0):
        out = []
        namew = 68
        bx = x + namew
        for i, (nm, val) in enumerate(items):
            y = top + i * row
            frac = (val / denom) if denom else 0
            w = max(2.0, barw * frac)
            out.append(
                f'<text class="s" x="{x}" y="{y+2}" font-size="12">{esc(nm.lower())}</text>'
                f'<rect class="trk" x="{bx}" y="{y-8}" width="{barw}" height="7" rx="3.5"/>'
                f'<rect class="s" x="{bx}" y="{y-8}" width="{w:.1f}" height="7" rx="3.5">'
                f'<animate attributeName="width" from="0" to="{w:.1f}" dur="0.7s" begin="{i*0.08:.2f}s" fill="freeze"/></rect>'
                f'<text class="m" x="{bx+barw+8}" y="{y+2}" font-size="11">'
                f'{(f"{frac*100:.0f}%") if is_pct else val}</text>')
        return out
    parts += rows(byte_items, colL, tot_bytes, True)
    parts += rows(repo_items, colR, max_repos, False)
    if not byte_items:
        parts.append(f'<text class="m" x="{colL}" y="{top+6}" font-size="12">no public code yet</text>')
    return svg(W, H, "".join(parts))


def build_year(cal):
    weeks = cal["weeks"]
    days = flatten(cal)
    counts = [c for _, c in days if c > 0]
    mx = max(counts) if counts else 1
    active = sum(1 for _, c in days if c > 0)
    CW, CH = 8.0, 13.0
    x0, y0 = 42, 54          # grid origin (leaves room for weekday labels)
    ncols = len(weeks)

    def glyph(c):
        if c <= 0:
            return None
        idx = 1 + round((c / mx) * (len(RAMP) - 2))
        return RAMP[min(len(RAMP) - 1, idx)]

    cells, month_labels = [], []
    last_month, last_lx = None, -100.0
    for wi, w in enumerate(weeks):
        # month label at the week where the month first appears (skip if crowded)
        first = datetime.date.fromisoformat(w["contributionDays"][0]["date"])
        if first.month != last_month:
            last_month = first.month
            lx = x0 + wi * CW
            if lx - last_lx >= 22:
                month_labels.append((lx, first.strftime("%b").lower()))
                last_lx = lx
        for d in w["contributionDays"]:
            g = glyph(d["contributionCount"])
            x = x0 + wi * CW
            y = y0 + d["weekday"] * CH + 10
            if g is None:
                cells.append(f'<text class="t" x="{x:.1f}" y="{y:.1f}" font-size="12" xml:space="preserve">·</text>')
            else:
                cells.append(f'<text class="s" x="{x:.1f}" y="{y:.1f}" font-size="12.9" xml:space="preserve">{esc(g)}</text>')
    # weekday labels
    for wd, name in ((1, "mon"), (3, "wed"), (5, "fri")):
        y = y0 + wd * CH + 10
        cells.append(f'<text class="m" x="8" y="{y:.1f}" font-size="9">{name}</text>')
    # month labels along bottom
    my = y0 + 7 * CH + 22
    for x, name in month_labels:
        cells.append(f'<text class="m" x="{x:.1f}" y="{my:.1f}" font-size="9">{name}</text>')
    # legend top-right
    W = int(x0 + ncols * CW + 16)
    lx = W - 150
    legend = [f'<text class="m" x="{lx}" y="30" font-size="9.5" letter-spacing="1">less</text>']
    for i, ch in enumerate(LEGEND):
        legend.append(f'<text class="s" x="{lx+34+i*13}" y="31" font-size="12">{esc(ch)}</text>')
    legend.append(f'<text class="m" x="{lx+34+len(LEGEND)*13+6}" y="30" font-size="9.5" letter-spacing="1">more</text>')
    H = int(my + 12)
    header = (f'<text class="m" x="8" y="26" font-size="9.5" letter-spacing="1.4">THE YEAR</text>'
              f'<text class="s" x="72" y="26" font-size="11">{active} of 365 days had a contribution</text>')
    return svg(W, H, header + "".join(legend) + "".join(cells))


def main():
    login = whoami()
    cal = fetch_calendar(login)
    by_bytes, by_repos = fetch_languages(login)
    cur, longest = streaks(flatten(cal))
    outputs = {
        "stats.svg": build_stats(cal),
        "streak.svg": build_streak(cur, longest),
        "langs.svg": build_langs(by_bytes, by_repos),
        "year.svg": build_year(cal),
    }
    for name, content in outputs.items():
        with open(name, "w") as f:
            f.write(content)
        print(f"wrote {name} ({len(content)} bytes)")
    print(f"[{login}] total={cal['totalContributions']} "
          f"cur={cur['n']} longest={longest['n']} langs={len(by_bytes)}")


if __name__ == "__main__":
    main()
