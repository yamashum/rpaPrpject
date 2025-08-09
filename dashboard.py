from __future__ import annotations

from argparse import ArgumentParser
from datetime import date, timedelta
from pathlib import Path

from workflow.log_db import (
    init_db,
    get_average_duration,
    get_failure_counts,
    get_run_counts_by_period,
    get_selector_success_rates,
    get_success_rate,
)


def main() -> None:
    parser = ArgumentParser(description='Generate simple HTML dashboard with run metrics.')
    parser.add_argument('--db', default='runs.sqlite', help='Path to SQLite database file')
    parser.add_argument('--output', default='dashboard.html', help='Path to output HTML file')
    args = parser.parse_args()

    conn = init_db(args.db)
    success_rate = get_success_rate(conn)
    avg_duration = get_average_duration(conn)
    failure_counts = get_failure_counts(conn)
    selector_rates = get_selector_success_rates(conn)
    daily_counts = list(get_run_counts_by_period(conn, 'day'))
    weekly_counts = list(get_run_counts_by_period(conn, 'week'))
    monthly_counts = list(get_run_counts_by_period(conn, 'month'))

    # build heatmap for last 35 days
    daily_map = {d: c for d, c in daily_counts}
    today = date.today()
    start = today - timedelta(days=34)
    days = [start + timedelta(days=i) for i in range(35)]
    max_cnt = max(daily_map.values()) if daily_map else 1
    rows = []
    for w in range(5):
        cells = []
        for wd in range(7):
            idx = w * 7 + wd
            day = days[idx]
            cnt = daily_map.get(day.isoformat(), 0)
            intensity = 255 - int((cnt / max_cnt) * 255) if max_cnt else 255
            cells.append(
                f"<td title='{day.isoformat()}: {cnt}' style='background-color: rgb({intensity},255,{intensity}); width:14px;height:14px'></td>"
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")
    heatmap_html = "<table class='heatmap'>" + "".join(rows) + "</table>"

    failure_html = "".join(
        f"<li>{reason}: {count}</li>" for reason, count in failure_counts.items()
    )
    selector_html = "".join(
        f"<li>{sel}: {rate:.2%}</li>" for sel, rate in selector_rates.items()
    )

    day_html = "".join(f"<li>{p}: {c}</li>" for p, c in daily_counts)
    week_html = "".join(f"<li>{p}: {c}</li>" for p, c in weekly_counts)
    month_html = "".join(f"<li>{p}: {c}</li>" for p, c in monthly_counts)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset='utf-8'><title>Run Metrics</title></head>
<body>
<h1>Run Metrics</h1>
<ul>
<li>Success rate: {success_rate:.2%}</li>
<li>Average duration: {avg_duration:.2f} seconds</li>
</ul>
<h2>Failure reasons</h2>
<ul>{failure_html}</ul>
<h2>Selector success rates</h2>
<ul>{selector_html}</ul>
<h2>Runs by period</h2>
<h3>By day</h3><ul>{day_html}</ul>
<h3>By week</h3><ul>{week_html}</ul>
<h3>By month</h3><ul>{month_html}</ul>
<h2>Daily activity heatmap</h2>
{heatmap_html}
</body>
</html>
"""
    Path(args.output).write_text(html, encoding='utf-8')
    print(f'Dashboard written to {args.output}')

if __name__ == '__main__':
    main()
