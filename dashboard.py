from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

from workflow.log_db import init_db, get_success_rate, get_average_duration


def main() -> None:
    parser = ArgumentParser(description='Generate simple HTML dashboard with run metrics.')
    parser.add_argument('--db', default='runs.sqlite', help='Path to SQLite database file')
    parser.add_argument('--output', default='dashboard.html', help='Path to output HTML file')
    args = parser.parse_args()

    conn = init_db(args.db)
    success_rate = get_success_rate(conn)
    avg_duration = get_average_duration(conn)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset='utf-8'><title>Run Metrics</title></head>
<body>
<h1>Run Metrics</h1>
<ul>
<li>Success rate: {success_rate:.2%}</li>
<li>Average duration: {avg_duration:.2f} seconds</li>
</ul>
</body>
</html>
"""
    Path(args.output).write_text(html, encoding='utf-8')
    print(f'Dashboard written to {args.output}')

if __name__ == '__main__':
    main()
