import unittest

from backlog_screener.openinsider import analyze_openinsider_html, parse_openinsider_transactions


OPENINSIDER_SAMPLE = """
<html><body>
<table class="tinytable">
<tbody>
<tr style="background:#d6ffd6">
  <td align=right></td>
  <td align=right><div><a href="http://www.sec.gov/Archives/edgar/data/1/form4.xml">2026-05-05 16:08:40</a></div></td>
  <td align=right><div>2026-05-01</div></td>
  <td><b><a href="/TEST">TEST</a></b></td>
  <td><a href="/insider/Jane-Doe/1" title="direct shares">Jane Doe</a></td>
  <td>CEO</td>
  <td>P - Purchase</td>
  <td align=right>$10.00</td>
  <td align=right>2,000</td>
  <td align=right>20,000</td>
  <td align=right>+10%</td>
  <td align=right>$20,000</td>
  <td></td><td></td><td></td><td></td>
</tr>
<tr style="background:#ffe1e1">
  <td align=right></td>
  <td align=right><div><a href="http://www.sec.gov/Archives/edgar/data/1/form4b.xml">2026-05-07 16:08:40</a></div></td>
  <td align=right><div>2026-05-06</div></td>
  <td><b><a href="/TEST">TEST</a></b></td>
  <td><a href="/insider/John-Doe/2">John Doe</a></td>
  <td>CFO</td>
  <td>S - Sale</td>
  <td align=right>$12.00</td>
  <td align=right>-1,000</td>
  <td align=right>10,000</td>
  <td align=right>-9%</td>
  <td align=right>-$12,000</td>
  <td></td><td></td><td></td><td></td>
</tr>
<tr style="background:#eeeeff">
  <td align=right>D</td>
  <td align=right><div><a href="http://www.sec.gov/Archives/edgar/data/1/form4c.xml">2026-05-08 16:08:40</a></div></td>
  <td align=right><div>2026-05-07</div></td>
  <td><b><a href="/TEST">TEST</a></b></td>
  <td><a href="/insider/Award-Holder/3">Award Holder</a></td>
  <td>Director</td>
  <td>A - Award</td>
  <td align=right>$0.00</td>
  <td align=right>5,000</td>
  <td align=right>5,000</td>
  <td align=right>100%</td>
  <td align=right>$0</td>
  <td></td><td></td><td></td><td></td>
</tr>
</tbody>
</table>
</body></html>
"""


class OpenInsiderTests(unittest.TestCase):
    def test_parse_transactions_from_ticker_table(self):
        rows = parse_openinsider_transactions(OPENINSIDER_SAMPLE, ticker="TEST")

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["trade_code"], "P")
        self.assertEqual(rows[0]["insider_name"], "Jane Doe")
        self.assertEqual(rows[0]["quantity"], 2000)
        self.assertEqual(rows[1]["trade_code"], "S")
        self.assertEqual(rows[1]["value"], -12000)
        self.assertEqual(rows[2]["transaction_flags"], "D")

    def test_signal_summarizes_open_market_purchase_and_sale_only(self):
        signal = analyze_openinsider_html(
            OPENINSIDER_SAMPLE,
            ticker="TEST",
            source_url="http://openinsider.com/screener?s=TEST",
        )

        self.assertEqual(signal.transaction_count, 3)
        self.assertEqual(signal.open_market_count, 2)
        self.assertEqual(signal.purchase_count, 1)
        self.assertEqual(signal.sale_count, 1)
        self.assertEqual(signal.purchase_value, 20000)
        self.assertEqual(signal.sale_value, 12000)
        self.assertEqual(signal.net_purchase_value, 8000)


if __name__ == "__main__":
    unittest.main()
