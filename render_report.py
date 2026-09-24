import sqlite3
from datetime import datetime
from playwright.sync_api import sync_playwright
from report_data import get_report_data, DB_PATH

def get_all_orders():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT customer, product, amount, created_at FROM orders ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def build_html(data, all_orders):
    today = datetime.now().strftime("%B %d, %Y")

    top_products_rows = "".join(
        f"<tr><td>{p['product']}</td><td>${p['revenue']:.2f}</td></tr>"
        for p in data["top_products"]
    )

    orders_rows = "".join(
        f"<tr><td>{o['customer']}</td><td>{o['product']}</td>"
        f"<td>${o['amount']:.2f}</td><td>{o['created_at']}</td></tr>"
        for o in all_orders
    )

    return f"""
    <html>
    <head>
    <style>
        body {{ font-family: Arial, sans-serif; font-size: 12px; color: #222; }}
        h1 {{ font-size: 20px; margin-bottom: 0; }}
        .date {{ color: #666; margin-top: 4px; }}
        .totals {{ display: flex; gap: 40px; margin: 20px 0; }}
        .totals div {{ background: #f4f4f4; padding: 10px 16px; border-radius: 6px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
        thead {{ display: table-header-group; }}
        tr {{ break-inside: avoid; }}
        h2 {{ margin-top: 30px; font-size: 15px; }}
    </style>
    </head>
    <body>
        <h1>Shop Sales Report</h1>
        <div class="date">Generated on {today}</div>

        <div class="totals">
            <div><strong>Total Orders:</strong> {data['total_orders']}</div>
            <div><strong>Total Revenue:</strong> ${data['total_revenue']:.2f}</div>
        </div>

        <h2>Top 5 Products by Revenue</h2>
        <table>
            <thead><tr><th>Product</th><th>Revenue</th></tr></thead>
            <tbody>{top_products_rows}</tbody>
        </table>

        <h2>All Orders</h2>
        <table>
            <thead><tr><th>Customer</th><th>Product</th><th>Amount</th><th>Date</th></tr></thead>
            <tbody>{orders_rows}</tbody>
        </table>
    </body>
    </html>
    """

def render_pdf(output_path="reports/test.pdf"):
    data = get_report_data()
    all_orders = get_all_orders()
    html = build_html(data, all_orders)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        page.pdf(path=output_path, format="A4", print_background=True)
        browser.close()

    print(f"PDF written to {output_path}")

if __name__ == "__main__":
    render_pdf()
