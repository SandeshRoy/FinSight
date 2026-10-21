
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"

segments = pd.read_csv(ROOT / "output" / "customer_segments.csv")
con = duckdb.connect(str(DB_PATH), read_only=True)
con.register("customer_segments", segments[["customer_id", "segment_id"]])

# 1. Compare investment credits across all four clusters
by_segment = con.execute("""
    SELECT
        s.segment_id,
        COUNT(*) AS investment_credit_count,
        COUNT(DISTINCT t.customer_id) AS customers_affected,
        SUM(t.amount) AS total_investment_credits,
        AVG(t.amount) AS average_credit_amount,
        MAX(t.amount) AS maximum_credit_amount,
        SUM(CASE WHEN t.amount = 2500000 THEN 1 ELSE 0 END)
            AS exact_25_lakh_count
    FROM transaction_fact t
    JOIN customer_segments s
      ON t.customer_id = s.customer_id
    WHERE t.direction = 'Credit'
      AND LOWER(t.merchant_category) = 'investment income'
    GROUP BY s.segment_id
    ORDER BY s.segment_id
""").df()

print("\n========== INVESTMENT CREDITS BY CLUSTER ==========")
print(by_segment.to_string(index=False))

by_segment.to_csv(
    ROOT / "output" / "investment_credits_by_segment.csv",
    index=False
)

# 2. Inspect the monthly pattern across the whole dataset
monthly = con.execute("""
    SELECT
        DATE_TRUNC('month', t.txn_timestamp) AS transaction_month,
        COUNT(*) AS investment_credit_count,
        COUNT(DISTINCT t.customer_id) AS customers_affected,
        SUM(t.amount) AS total_amount,
        SUM(CASE WHEN t.amount = 2500000 THEN 1 ELSE 0 END)
            AS exact_25_lakh_count
    FROM transaction_fact t
    WHERE t.direction = 'Credit'
      AND LOWER(t.merchant_category) = 'investment income'
    GROUP BY 1
    ORDER BY 1
""").df()

print("\n========== MONTHLY INVESTMENT CREDIT PATTERN ==========")
print(monthly.to_string(index=False))

monthly.to_csv(
    ROOT / "output" / "investment_credits_by_month.csv",
    index=False
)

# 3. Inspect large investment credits and their segment membership
large = con.execute("""
    SELECT
        s.segment_id,
        t.customer_id,
        t.txn_timestamp,
        t.txn_type,
        t.merchant_category,
        t.amount,
        t.is_salary_credit,
        t.is_reversal,
        t.is_fee
    FROM transaction_fact t
    JOIN customer_segments s
      ON t.customer_id = s.customer_id
    WHERE t.direction = 'Credit'
      AND LOWER(t.merchant_category) = 'investment income'
      AND t.amount >= 1000000
    ORDER BY t.amount DESC, t.txn_timestamp
    LIMIT 50
""").df()

print("\n========== LARGEST INVESTMENT CREDITS ==========")
print(large.to_string(index=False))

large.to_csv(
    ROOT / "output" / "largest_investment_credits.csv",
    index=False
)

con.close()
print("\nReports saved in output/")

