
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = ROOT / "output" / "customer_segments.csv"
OUTPUT_DIR = ROOT / "output"

if not INPUT_PATH.exists():
    raise FileNotFoundError(f"File not found: {INPUT_PATH}")

df = pd.read_csv(INPUT_PATH)

features = [
    "annual_income",
    "avg_monthly_credits",
    "avg_monthly_debits",
    "avg_net_cash_flow",
    "avg_account_balance",
    "avg_monthly_emi",
    "avg_outstanding_loan",
    "avg_transaction_count",
    "negative_cash_flow_rate",
]

# Verify the clustering output.
print("\n========== SEGMENT VALIDATION ==========\n")
print(f"Customer rows: {len(df):,}")
print(f"Unique customers: {df['customer_id'].nunique():,}")
print(f"Missing customer IDs: {df['customer_id'].isna().sum()}")
print(f"Missing segment IDs: {df['segment_id'].isna().sum()}")
print("\nCustomers per cluster:")
print(df["segment_id"].value_counts().sort_index().to_string())

# Summarize distributions using mean, median, minimum and maximum.
summary = df.groupby("segment_id")[features].agg(
    ["mean", "median", "min", "max"]
)

print("\n========== CLUSTER FEATURE DISTRIBUTIONS ==========\n")
print(summary.round(2).to_string())

# Inspect customers with the lowest and highest average EMI.
print("\n========== CLUSTER 3 EMI INSPECTION ==========\n")

cluster3 = df[df["segment_id"] == 3]

if cluster3.empty:
    print("Cluster 3 is empty.")
else:
    print(
        cluster3[
            [
                "customer_id",
                "annual_income",
                "avg_monthly_credits",
                "avg_monthly_debits",
                "avg_monthly_emi",
                "avg_outstanding_loan",
                "negative_cash_flow_rate",
            ]
        ]
        .sort_values("avg_monthly_emi")
        .head(10)
        .round(2)
        .to_string(index=False)
    )

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

summary_path = OUTPUT_DIR / "segment_distribution_summary.csv"
summary.to_csv(summary_path)

print(f"\nDistribution summary saved to: {summary_path}")
