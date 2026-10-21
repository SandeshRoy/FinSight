
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

segments = pd.read_csv(ROOT / "output" / "customer_segments.csv")
con = duckdb.connect(
    str(ROOT / "data" / "bank_data.db"),
    read_only=True
)

con.register(
    "customer_segments",
    segments[["customer_id", "segment_id"]]
)

# Calculate credit/debit totals for each customer
customer_impact = con.execute("""
    SELECT
        s.customer_id,
        s.segment_id,

        SUM(CASE
            WHEN t.direction = 'Credit'
            THEN t.amount ELSE 0
        END) AS total_credits,

        SUM(CASE
            WHEN t.direction = 'Credit'
             AND LOWER(COALESCE(t.counterparty_type, ''))
                 = 'self transfer'
            THEN t.amount ELSE 0
        END) AS self_transfer_credits,

        SUM(CASE
            WHEN t.direction = 'Credit'
             AND LOWER(COALESCE(t.counterparty_type, ''))
                 <> 'self transfer'
            THEN t.amount ELSE 0
        END) AS non_self_transfer_credits,

        SUM(CASE
            WHEN t.direction = 'Debit'
            THEN t.amount ELSE 0
        END) AS total_debits,

        COUNT(*) AS transaction_count

    FROM customer_segments s
    LEFT JOIN transaction_fact t
      ON t.customer_id = s.customer_id
    GROUP BY s.customer_id, s.segment_id
""").df()

customer_impact["self_transfer_credit_share"] = (
    customer_impact["self_transfer_credits"]
    / customer_impact["total_credits"].replace(0, float("nan"))
)

customer_impact.to_csv(
    ROOT / "output" / "customer_self_transfer_impact.csv",
    index=False
)

# Summarize impact by existing segment
summary = customer_impact.groupby("segment_id").agg(
    customers=("customer_id", "nunique"),
    total_credits=("total_credits", "sum"),
    self_transfer_credits=("self_transfer_credits", "sum"),
    non_self_transfer_credits=("non_self_transfer_credits", "sum"),
    total_debits=("total_debits", "sum"),
    avg_self_transfer_share=("self_transfer_credit_share", "mean"),
).reset_index()

summary["overall_self_transfer_share"] = (
    summary["self_transfer_credits"]
    / summary["total_credits"].replace(0, float("nan"))
)

print("\n========== SELF-TRANSFER IMPACT BY CLUSTER ==========")
print(summary.round(3).to_string(index=False))

summary.to_csv(
    ROOT / "output" / "self_transfer_impact_by_segment.csv",
    index=False
)

print("\n========== CUSTOMERS WITH HIGHEST SELF-TRANSFER SHARE ==========")
print(
    customer_impact.dropna(subset=["self_transfer_credit_share"])
    .sort_values("self_transfer_credit_share", ascending=False)
    .head(15)[[
        "customer_id",
        "segment_id",
        "total_credits",
        "self_transfer_credits",
        "non_self_transfer_credits",
        "total_debits",
        "self_transfer_credit_share"
    ]].round(3).to_string(index=False)
)

con.close()
print("\nReports saved in output/")
