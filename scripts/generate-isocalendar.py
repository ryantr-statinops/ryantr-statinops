"""Render a rolling GitHub contribution calendar as a standalone SVG."""

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


LEVELS = ("NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE")
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays { date contributionCount contributionLevel }
        }
      }
    }
  }
}
"""


def fetch_days(login, token, start, now):
    variables = {
        "login": login,
        "from": datetime.combine(start, time.min, timezone.utc).isoformat(),
        "to": now.isoformat(),
    }
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-isometric-calendar",
        },
    )
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    user = (result.get("data") or {}).get("user")
    if result.get("errors") or user is None:
        raise ValueError("GitHub did not return the contribution calendar")
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = {
        date.fromisoformat(day["date"]): (day["contributionCount"], day["contributionLevel"])
        for week in weeks
        for day in week["contributionDays"]
    }
    expected = [start + timedelta(days=i) for i in range((now.date() - start).days + 1)]
    if any(day not in days for day in expected):
        raise ValueError("GitHub returned an incomplete date range")
    return [(day, *days[day]) for day in expected]


def render_svg(days):
    first, last = days[0][0], days[-1][0]
    peak = max(count for _, count, _ in days)
    average = sum(count for _, count, _ in days) / len(days)
    current = best = 0
    for _, count, _ in days:
        current = current + 1 if count else 0
        best = max(best, current)

    # Place dates on a Sunday-first grid and project both axes diagonally.
    start_row = (first.weekday() + 1) % 7
    last_column = (start_row + len(days) - 1) // 7
    left, right = -96, 20 * last_column + 18
    scale = min(1.2, 432 / (right - left))
    chart_x = 240 - (left + right) * scale / 2
    blocks = []
    tops, bottoms = [], []
    for index, (day, count, level) in enumerate(days):
        column, row = divmod(start_row + index, 7)
        x, y = column * 20 - row * 14, column * 10 + row * 7
        rise = round(34 * count / peak) if peak else 0
        top = y - rise
        tops.append(top)
        bottoms.append(y + 17)
        blocks.append(
            f'    <g class="level-{LEVELS.index(level)}" data-date="{day}">'
            f'<title>{day} · {count} contributions</title>'
            f'<polygon points="{x-12},{top+6} {x+6},{top+15} {x+6},{y+17} {x-12},{y+8}" class="side-a"/>'
            f'<polygon points="{x+6},{top+15} {x+18},{top+9} {x+18},{y+11} {x+6},{y+17}" class="side-b"/>'
            f'<polygon points="{x},{top} {x+18},{top+9} {x+6},{top+15} {x-12},{top+6}"/>'
            '</g>'
        )

    chart_y = 64 - min(tops) * scale
    stats_y = round(chart_y + max(bottoms) * scale + 20)
    height = stats_y + 50
    stats = (
        ("Current streak", f"{current} days"),
        ("Best streak", f"{best} days"),
        ("Most in a day", str(peak)),
        ("Daily average", f"{average:.2f}"),
    )
    labels = [
        f'  <text x="{x}" y="{stats_y+16}" class="muted">{label}</text>'
        f'<text x="{x}" y="{stats_y+36}" class="value">{value}</text>'
        for x, (label, value) in zip((20, 136, 252, 368), stats)
    ]

    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="{height}" viewBox="0 0 480 {height}" role="img" aria-labelledby="title desc">',
        '  <title id="title">GitHub contribution calendar</title>',
        f'  <desc id="desc">{len(days)} days from {first} to {last}, with daily contribution counts and streak statistics.</desc>',
        """  <style>
    svg { font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; --fg: #24292f; --muted: #57606a; --line: #d0d7de; }
    text { fill: var(--fg); }
    .heading { font-weight: 600; font-size: 15px; }
    .muted { fill: var(--muted); font-size: 11px; }
    .value { font-weight: 600; }
    .divider { stroke: var(--line); }
    .level-0 { fill: #ebedf0; }
    .level-1 { fill: #9be9a8; }
    .level-2 { fill: #40c463; }
    .level-3 { fill: #30a14e; }
    .level-4 { fill: #216e39; }
    .side-a { filter: brightness(.73); }
    .side-b { filter: brightness(.52); }
    @media (prefers-color-scheme: dark) {
      svg { --fg: #e6edf3; --muted: #8b949e; --line: #30363d; }
      .level-0 { fill: #21262d; }
      .level-1 { fill: #0e4429; }
      .level-2 { fill: #006d32; }
      .level-3 { fill: #26a641; }
      .level-4 { fill: #39d353; }
    }
  </style>""",
        f'  <text x="20" y="23" class="heading">Contributions · Last {len(days)} days</text>',
        f'  <text x="20" y="42" class="muted">{first:%d %b %Y} – {last:%d %b %Y}</text>',
        f'  <g transform="translate({chart_x:.2f} {chart_y:.2f}) scale({scale:.4f})">',
        *blocks,
        '  </g>',
        f'  <path d="M20 {stats_y} H460" class="divider"/>',
        *labels,
        '</svg>',
        '',
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True)
    parser.add_argument("--days", type=int, default=180, choices=range(1, 366), metavar="1–365")
    parser.add_argument("--output", type=Path, default=Path("metrics.isocalendar.svg"))
    args = parser.parse_args()
    token = os.environ.get("METRICS_TOKEN")
    if not token:
        parser.error("METRICS_TOKEN must be set")

    now = datetime.now(timezone.utc)
    start = now.date() - timedelta(days=args.days - 1)
    days = fetch_days(args.user, token, start, now)
    args.output.write_text(render_svg(days), encoding="utf-8")
    print(f"Rendered {len(days)} days ({start} to {now.date()}) into {args.output}")


if __name__ == "__main__":
    main()
