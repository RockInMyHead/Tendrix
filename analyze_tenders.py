#!/usr/bin/env python3
"""
Анализ тендеров: статистика и графики.
Запуск: python analyze_tenders.py
Результат: папка analysis/ с HTML-отчётом и интерактивными графиками (Chart.js).
"""
import sqlite3
import os
import json
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql_app.db")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analysis")


def get_conn():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"БД не найдена: {DB_PATH}")
    return sqlite3.connect(DB_PATH)


def fetch_stats(conn):
    c = conn.cursor()
    stats = {}

    c.execute("SELECT COUNT(*) FROM tenders")
    stats["total"] = c.fetchone()[0]

    c.execute("""
        SELECT COALESCE(procurement_type, 'Без типа') as pt, COUNT(*) as cnt
        FROM tenders GROUP BY pt ORDER BY cnt DESC LIMIT 12
    """)
    stats["by_source"] = list(c.fetchall())

    c.execute("""
        SELECT 
            CASE 
                WHEN update_date LIKE '%.2026%' THEN '2026'
                WHEN update_date LIKE '%.2025%' THEN '2025'
                WHEN update_date LIKE '%.2024%' THEN '2024'
                WHEN update_date LIKE '%.2023%' THEN '2023'
                ELSE 'До 2023'
            END as y, COUNT(*) as cnt
        FROM tenders WHERE update_date IS NOT NULL
        GROUP BY y ORDER BY y DESC
    """)
    stats["by_year"] = list(c.fetchall())

    c.execute("""
        SELECT region, COUNT(*) as cnt FROM tenders
        WHERE region IS NOT NULL AND region != ''
        GROUP BY region ORDER BY cnt DESC LIMIT 12
    """)
    stats["by_region"] = list(c.fetchall())

    c.execute("""
        SELECT SUBSTR(update_date, 4, 2) || '.' || SUBSTR(update_date, 7, 4) as m, COUNT(*) as cnt
        FROM tenders
        WHERE (update_date LIKE '%.2025%' OR update_date LIKE '%.2026%')
        GROUP BY m ORDER BY SUBSTR(update_date, 7, 4), SUBSTR(update_date, 4, 2)
    """)
    stats["by_month"] = list(c.fetchall())

    return stats


def write_html_report(stats):
    sources_labels = json.dumps([x[0][:30] for x in stats["by_source"]])
    sources_data = json.dumps([x[1] for x in stats["by_source"]])
    years_labels = json.dumps([x[0] for x in stats["by_year"]])
    years_data = json.dumps([x[1] for x in stats["by_year"]])
    regions_labels = json.dumps([x[0][:25] for x in stats["by_region"]])
    regions_data = json.dumps([x[1] for x in stats["by_region"]])
    months_labels = json.dumps([x[0] for x in stats["by_month"]])
    months_data = json.dumps([x[1] for x in stats["by_month"]])

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Анализ тендеров</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 1000px; margin: 0 auto; padding: 24px; background: #f8fafc; }}
        h1 {{ color: #1e293b; margin-bottom: 8px; }}
        .stat {{ background: linear-gradient(135deg, #3b82f6, #2563eb); color: white; padding: 24px; border-radius: 12px; margin: 24px 0; text-align: center; }}
        .stat big {{ font-size: 2.5em; font-weight: 700; display: block; }}
        .stat span {{ opacity: 0.9; font-size: 0.95em; }}
        section {{ background: white; padding: 24px; border-radius: 12px; margin: 24px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        h2 {{ color: #334155; margin-top: 0; font-size: 1.25em; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
        th {{ background: #f1f5f9; color: #475569; font-weight: 600; }}
        .chart-container {{ position: relative; height: 320px; margin: 20px 0; }}
    </style>
</head>
<body>
    <h1>Анализ базы тендеров</h1>
    <div class="stat">
        <big>{stats['total']:,}</big>
        <span>тендеров в базе</span>
    </div>

    <section>
        <h2>По источникам</h2>
        <div class="chart-container"><canvas id="chartSources"></canvas></div>
        <table>
            <tr><th>Источник</th><th>Количество</th><th>%</th></tr>
"""
    total = stats["total"]
    for label, cnt in stats["by_source"]:
        pct = 100 * cnt / total if total else 0
        html += f"            <tr><td>{label}</td><td>{cnt:,}</td><td>{pct:.1f}%</td></tr>\n"
    html += "        </table>\n    </section>\n"

    html += """    <section>
        <h2>По годам</h2>
        <div class="chart-container"><canvas id="chartYears"></canvas></div>
        <table>
            <tr><th>Год</th><th>Количество</th></tr>
"""
    for y, cnt in stats["by_year"]:
        html += f"            <tr><td>{y}</td><td>{cnt:,}</td></tr>\n"
    html += "        </table>\n    </section>\n"

    html += """    <section>
        <h2>Топ регионов</h2>
        <div class="chart-container"><canvas id="chartRegions"></canvas></div>
        <table>
            <tr><th>Регион</th><th>Количество</th></tr>
"""
    for r, cnt in stats["by_region"]:
        html += f"            <tr><td>{r}</td><td>{cnt:,}</td></tr>\n"
    html += "        </table>\n    </section>\n"

    html += """    <section>
        <h2>По месяцам (2025–2026)</h2>
        <div class="chart-container"><canvas id="chartMonths"></canvas></div>
        <table>
            <tr><th>Месяц</th><th>Количество</th></tr>
"""
    for m, cnt in stats["by_month"]:
        html += f"            <tr><td>{m}</td><td>{cnt:,}</td></tr>\n"
    html += "        </table>\n    </section>\n"

    html += f"""
    <script>
        const colors = ['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#06b6d4','#84cc16','#f97316','#6366f1','#14b8a6','#a855f7'];
        new Chart(document.getElementById('chartSources'), {{
            type: 'doughnut',
            data: {{ labels: {sources_labels}, datasets: [{{ data: {sources_data}, backgroundColor: colors }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: 'right' }} }} }}
        }});
        new Chart(document.getElementById('chartYears'), {{
            type: 'bar',
            data: {{ labels: {years_labels}, datasets: [{{ label: 'Тендеров', data: {years_data}, backgroundColor: '#3b82f6' }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, scales: {{ y: {{ beginAtZero: true }} }} }}
        }});
        new Chart(document.getElementById('chartRegions'), {{
            type: 'bar',
            data: {{ labels: {regions_labels}, datasets: [{{ label: 'Тендеров', data: {regions_data}, backgroundColor: '#10b981' }}] }},
            options: {{ indexAxis: 'y', responsive: true, maintainAspectRatio: false, scales: {{ x: {{ beginAtZero: true }} }} }}
        }});
        new Chart(document.getElementById('chartMonths'), {{
            type: 'line',
            data: {{ labels: {months_labels}, datasets: [{{ label: 'Тендеров', data: {months_data}, borderColor: '#3b82f6', fill: true, tension: 0.3 }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, scales: {{ y: {{ beginAtZero: true }} }} }}
        }});
    </script>
</body>
</html>"""
    report_path = os.path.join(OUT_DIR, "report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Отчёт: {report_path}")


def main():
    Path(OUT_DIR).mkdir(exist_ok=True)
    conn = get_conn()
    stats = fetch_stats(conn)
    conn.close()
    write_html_report(stats)
    print("Готово. Откройте analysis/report.html в браузере.")


if __name__ == "__main__":
    main()
