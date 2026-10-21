import duckdb
import pandas as pd

DB_PATH = "data/bank_data.db"

con = duckdb.connect(DB_PATH, read_only=True)

query = """
WITH ranked_transactions AS (
    SELECT
        account_id,
        customer_id,
        CAST(date_trunc('month', txn_timestamp) AS DATE)
            AS snapshot_month,
        txn_timestamp,
        transaction_id,
        balance_after_txn,
        ROW_NUMBER() OVER (
            PARTITION BY account_id,
                         date_trunc('month', txn_timestamp)
            ORDER BY txn_timestamp DESC, transaction_id DESC
        ) AS rn
    FROM transaction_fact
),
last_transactions AS (
    SELECT
        account_id,
        customer_id,
        snapshot_month,
        txn_timestamp AS last_transaction_time,
        transaction_id AS last_transaction_id,
        balance_after_txn AS last_transaction_balance
    FROM ranked_transactions
    WHERE rn = 1
)
SELECT
    s.account_id,
    a.customer_id,
    s.snapshot_month,
    s.current_balance,
    t.last_transaction_balance,
    t.last_transaction_time,
    t.last_transaction_id,
    ABS(
        s.current_balance - t.last_transaction_balance
    ) AS balance_difference,
    CASE
        WHEN t.account_id IS NULL THEN 'NO TRANSACTIONS'
        WHEN ABS(
            s.current_balance - t.last_transaction_balance
        ) <= 0.01 THEN 'MATCH'
        ELSE 'MISMATCH'
    END AS audit_status
FROM account_monthly_snapshot s
JOIN account_master a
    ON s.account_id = a.account_id
LEFT JOIN last_transactions t
    ON s.account_id = t.account_id
    AND CAST(s.snapshot_month AS DATE) = t.snapshot_month
ORDER BY s.account_id, s.snapshot_month
"""

df = con.execute(query).df()
con.close()

output_path = "output/snapshot_transaction_balance_audit.csv"
df.to_csv(output_path, index=False)

print("\n========== AUDIT SUMMARY ==========")
print(df["audit_status"].value_counts().to_string())

print("\n========== BALANCE DIFFERENCE SUMMARY ==========")
print(
    df.groupby("audit_status", dropna=False)["balance_difference"]
    .agg(["count", "mean", "max"])
    .round(2)
    .to_string()
)

print("\n========== CUSTOMER 1007416 ==========")
customer = df[df["customer_id"] == 1007416]

print(
    customer[
        [
            "snapshot_month",
            "current_balance",
            "last_transaction_balance",
            "balance_difference",
            "audit_status",
        ]
    ].to_string(index=False)
)

print(f"\nFull report saved to: {output_path}")