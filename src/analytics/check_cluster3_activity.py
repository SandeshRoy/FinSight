
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"
SEGMENTS_PATH = ROOT / "output" / "customer_segments.csv"

segments = pd.read_csv(SEGMENTS_PATH)
cluster3 = segments.loc[
    segments["segment_id"] == 3, ["customer_id"]
].copy()

con = duckdb.connect(str(DB_PATH), read_only=True)
con.register("cluster3_customers", cluster3)

# 1. Monthly transaction coverage
coverage = con.execute("""
    SELECT
        t.customer_id,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT DATE_TRUNC('month', t.txn_timestamp))
            AS active_months,
        SUM(CASE WHEN t.direction = 'CREDIT'
                 THEN t.amount ELSE 0 END) AS total_credits,
        SUM(CASE WHEN t.direction = 'DEBIT'
                 THEN t.amount ELSE 0 END) AS total_debits,
        SUM(CASE WHEN t.is_salary_credit
                 THEN t.amount ELSE 0 END) AS salary_credits
    FROM transaction_fact t
    JOIN cluster3_customers c
      ON t.customer_id = c.customer_id
    GROUP BY t.customer_id
""").df()

coverage.to_csv(
    ROOT / "output" / "cluster3_activity_coverage.csv",
    index=False
)

print("\n========== TRANSACTION COVERAGE ==========")
print("Cluster 3 customers:", len(cluster3))
print("Customers with transactions:", len(coverage))
print("Customers with no transactions:", len(cluster3) - len(coverage))

if not coverage.empty:
    print("\nActive-month distribution:")
    print(coverage["active_months"].describe().round(2))

    print("\nCustomers grouped by active months:")
    print(
        pd.cut(
            coverage["active_months"],
            bins=[0, 1, 3, 6, 12, 24],
            include_lowest=True
        ).value_counts().sort_index()
    )

    print("\nCustomers with the fewest active months:")
    print(
        coverage.sort_values(
            ["active_months", "transaction_count"]
        ).head(20).to_string(index=False)
    )

# 2. Transaction types and directions
types = con.execute("""
    SELECT
        t.txn_type,
        t.direction,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT t.customer_id) AS customer_count,
        SUM(t.amount) AS total_amount
    FROM transaction_fact t
    JOIN cluster3_customers c
      ON t.customer_id = c.customer_id
    GROUP BY t.txn_type, t.direction
    ORDER BY transaction_count DESC
""").df()

types.to_csv(
    ROOT / "output" / "cluster3_transaction_types.csv",
    index=False
)

print("\n========== TRANSACTION TYPES ==========")
print(types.to_string(index=False))

con.close()

print("\nReports saved:")
print("output/cluster3_activity_coverage.csv")
print("output/cluster3_transaction_types.csv")
