
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
con = duckdb.connect(str(ROOT / "data" / "bank_data.db"), read_only=True)

segments = pd.read_csv(ROOT / "output" / "customer_segments.csv")
cluster3 = segments.loc[
    segments["segment_id"] == 3,
    ["customer_id", "avg_monthly_credits", "avg_monthly_debits"]
].copy()

con.register("cluster3_customers", cluster3)

# Correct case: source values are Credit and Debit
customer_totals = con.execute("""
    SELECT
        t.customer_id,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT DATE_TRUNC('month', t.txn_timestamp))
            AS active_months,
        SUM(CASE WHEN t.direction = 'Credit'
                 THEN t.amount ELSE 0 END) AS raw_credits,
        SUM(CASE WHEN t.direction = 'Debit'
                 THEN t.amount ELSE 0 END) AS raw_debits,
        SUM(CASE WHEN t.is_salary_credit
                 THEN t.amount ELSE 0 END) AS salary_credits
    FROM transaction_fact t
    JOIN cluster3_customers c
      ON t.customer_id = c.customer_id
    GROUP BY t.customer_id
""").df()

result = cluster3.merge(customer_totals, on="customer_id", how="left")
result["transaction_count"] = result["transaction_count"].fillna(0)
result["active_months"] = result["active_months"].fillna(0)

# 24-month averages for comparison with customer-level segment features
result["raw_credit_average_24m"] = result["raw_credits"] / 24
result["raw_debit_average_24m"] = result["raw_debits"] / 24

result.to_csv(
    ROOT / "output" / "cluster3_corrected_amounts.csv",
    index=False
)

print("\n========== CORRECTED CLUSTER 3 TOTALS ==========")
print("Customers:", len(result))
print("Total raw credits:", round(result["raw_credits"].sum(), 2))
print("Total raw debits:", round(result["raw_debits"].sum(), 2))
print("Customers with zero raw debits:",
      int((result["raw_debits"].fillna(0) == 0).sum()))
print("Customers with zero raw credits:",
      int((result["raw_credits"].fillna(0) == 0).sum()))

print("\n========== CREDIT/DEBIT DISTRIBUTION ==========")
print(result[[
    "raw_credits", "raw_debits",
    "raw_credit_average_24m", "raw_debit_average_24m"
]].describe(percentiles=[0.5, 0.9, 0.95, 0.99]).round(2))

print("\n========== HIGHEST CREDIT TOTALS ==========")
print(result.nlargest(10, "raw_credits")[[
    "customer_id", "transaction_count", "active_months",
    "raw_credits", "raw_debits",
    "avg_monthly_credits", "avg_monthly_debits"
]].to_string(index=False))

print("\n========== LARGEST CREDIT TRANSACTIONS ==========")
largest = con.execute("""
    SELECT
        t.transaction_id,
        t.customer_id,
        t.txn_timestamp,
        t.txn_type,
        t.direction,
        t.amount,
        t.merchant_category,
        t.is_salary_credit,
        t.is_reversal,
        t.is_fee
    FROM transaction_fact t
    JOIN cluster3_customers c
      ON t.customer_id = c.customer_id
    WHERE t.direction = 'Credit'
    ORDER BY t.amount DESC
    LIMIT 20
""").df()

print(largest.to_string(index=False))
largest.to_csv(
    ROOT / "output" / "cluster3_largest_credit_transactions.csv",
    index=False
)

con.close()

print("\nReports saved in output/")
