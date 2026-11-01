"""Self-contained RTL HTML statistics report, generated locally (#210)."""

from __future__ import annotations

import html

from .stats_charts import (
    category_chart,
    closure_chart,
    monthly_chart,
    street_chart,
)

_CSS = """
body { font-family: sans-serif; direction: rtl; margin: 2em auto;
       max-width: 960px; color: #1a202c; }
h1 { font-size: 1.5em; }
h2 { font-size: 1.15em; margin-top: 1.8em; }
table { border-collapse: collapse; }
td, th { border: 1px solid #cbd5e0; padding: 4px 10px; font-size: 0.9em; }
.note { color: #4a5568; font-size: 0.85em; }
svg { display: block; margin: 0.5em 0; overflow: visible; }
"""


def _esc(text: object) -> str:
    return html.escape(str(text))


def _kv_table(rows: list[tuple[str, object]]) -> str:
    body = "".join(
        f"<tr><th>{_esc(key)}</th><td>{_esc(value)}</td></tr>" for key, value in rows
    )
    return f"<table>{body}</table>"


def build_report(summary: dict) -> str:
    """Render the full report.html for one summary document."""
    closure = summary["closure"]
    date_range = summary["date_range"]
    overview = _kv_table(
        [
            ('סה"כ פניות', summary["total_incidents"]),
            ("כפילויות שדולגו", summary.get("duplicates_skipped", 0)),
            ("טווח תאריכים", f"{date_range['first']} עד {date_range['last']}"),
            ("פניות שנסגרו", closure["closed_count"]),
            ("חציון זמן סגירה (ימים)", closure["median_days"]),
            ("רבעון עליון (ימים)", closure["p75_days"]),
            ("סגירה מקסימלית (ימים)", closure["max_days"]),
        ]
    )
    medians = closure["median_days_by_category"]
    medians_table = _kv_table([(category, days) for category, days in medians.items()])
    status_table = _kv_table(list(summary["by_status"].items()))
    inputs = ", ".join(_esc(path) for path in summary.get("inputs", []))
    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<title>סטטיסטיקת דיווחי 106</title>
<style>{_CSS}</style>
</head>
<body>
<h1>סטטיסטיקת דיווחי 106</h1>
<p class="note">נוצר מקומית על ידי p106-stats. קבצי קלט: {inputs}</p>
<h2>סקירה</h2>
{overview}
<h2>דיווחים לפי חודש</h2>
{monthly_chart(summary["by_month"])}
<h2>דיווחים לפי קטגוריה</h2>
{category_chart(summary["by_category"])}
<h2>הרחובות המדווחים ביותר</h2>
{street_chart(summary["by_street"])}
<h2>זמני סגירה</h2>
{closure_chart(closure["buckets"])}
<h2>חציון זמן סגירה לפי קטגוריה (ימים)</h2>
{medians_table}
<h2>סטטוס פניות</h2>
{status_table}
</body>
</html>
"""
