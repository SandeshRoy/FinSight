
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

data = pd.read_csv(ROOT / "output" / "customer_segments_v3.csv")

features = [
    "annual_income",
    "avg_monthly_non_self_credits",
    "avg_monthly_debits",
    "avg_account_balance",
    "avg_monthly_emi",
    "avg_outstanding_loan",
    "avg_transaction_count",
]

# 1. Detailed distributions by cluster
rows = []

for segment_id, group in data.groupby("segment_id"):
    row = {
        "segment_id": segment_id,
        "customers": len(group),
    }

    for col in features:
        row[f"{col}_median"] = group[col].median()
        row[f"{col}_min"] = group[col].min()
        row[f"{col}_max"] = group[col].max()

    row["negative_balance_count"] = (
        group["avg_account_balance"] < 0
    ).sum()

    row["negative_balance_pct"] = (
        group["avg_account_balance"] < 0
    ).mean() * 100

    row["zero_non_self_credit_count"] = (
        group["avg_monthly_non_self_credits"] == 0
    ).sum()

    rows.append(row)

summary = pd.DataFrame(rows)
summary.to_csv(
    ROOT / "output" / "segment_validation_v3.csv",
    index=False,
)

print("\n========== V3 CLUSTER VALIDATION ==========")
print(summary.round(2).to_string(index=False))

# 2. Inspect the smallest segment
smallest_id = data["segment_id"].value_counts().idxmin()
smallest = data[data["segment_id"] == smallest_id].copy()

print(f"\n========== SMALLEST SEGMENT: {smallest_id} ==========")
print("Customers:", len(smallest))

print("\nCustomers with the most negative average balance:")
print(
    smallest.nsmallest(15, "avg_account_balance")[[
        "customer_id",
        "annual_income",
        "avg_monthly_non_self_credits",
        "avg_monthly_debits",
        "avg_account_balance",
        "avg_monthly_emi",
        "avg_outstanding_loan",
        "avg_transaction_count",
    ]].round(2).to_string(index=False)
)

print("\nCustomers with the highest average debits:")
print(
    smallest.nlargest(15, "avg_monthly_debits")[[
        "customer_id",
        "annual_income",
        "avg_monthly_non_self_credits",
        "avg_monthly_debits",
        "avg_account_balance",
        "avg_monthly_emi",
        "avg_outstanding_loan",
        "avg_transaction_count",
    ]].round(2).to_string(index=False)
)

print("\nSaved: output/segment_validation_v3.csv")
