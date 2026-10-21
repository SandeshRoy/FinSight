
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output"

profile = pd.read_csv(
    OUTPUT / "customer_monthly_profile_v2.csv"
)
financial = pd.read_csv(
    OUTPUT / "financial_profile.csv"
)

for df in (profile, financial):
    df["snapshot_month"] = (
        pd.to_datetime(df["snapshot_month"])
        .dt.to_period("M")
        .dt.to_timestamp()
    )

profile_cols = [
    "customer_id",
    "snapshot_month",
    "salary_income",
    "other_credits",
    "total_credits",
    "self_transfer_credits",
    "non_self_transfer_credits",
    "non_self_transfer_debits",
]

financial_cols = [
    "customer_id",
    "snapshot_month",
    "monthly_emi_obligation",
    "outstanding_loan_balance",
]

monthly = profile[profile_cols].merge(
    financial[financial_cols],
    on=["customer_id", "snapshot_month"],
    how="inner",
    validate="one_to_one",
)

monthly = monthly.sort_values(
    ["customer_id", "snapshot_month"]
)

latest = monthly.drop_duplicates(
    "customer_id",
    keep="last",
).copy()

latest["monthly_income"] = latest["non_self_transfer_credits"]

print("\n========== DATA QUALITY CHECK ==========")
print("Customers:", latest["customer_id"].nunique())
print(
    "Zero non-self-transfer income:",
    int((latest["monthly_income"] == 0).sum()),
)
print(
    "Positive salary income but zero non-self-transfer income:",
    int(
        (
            (latest["salary_income"] > 0)
            & (latest["monthly_income"] == 0)
        ).sum()
    ),
)
print(
    "Positive other credits but zero non-self-transfer income:",
    int(
        (
            (latest["other_credits"] > 0)
            & (latest["monthly_income"] == 0)
        ).sum()
    ),
)

print("\n========== INCOME FIELD SUMMARY ==========")
print(
    latest[
        [
            "salary_income",
            "other_credits",
            "total_credits",
            "self_transfer_credits",
            "non_self_transfer_credits",
        ]
    ].describe().round(2).to_string()
)

reference = pd.read_csv(
    OUTPUT / "customer_pattern_reference.csv"
)

print("\n========== ZERO-INCOME CUSTOMERS BY SEGMENT ==========")
print(
    reference.assign(
        zero_income=reference["monthly_income"] == 0
    ).groupby("segment_id").agg(
        customers=("customer_id", "nunique"),
        zero_income_customers=("zero_income", "sum"),
    ).to_string()
)

print("\n========== SAMPLE ZERO-INCOME RECORDS ==========")
columns = [
    "customer_id",
    "salary_income",
    "other_credits",
    "total_credits",
    "self_transfer_credits",
    "non_self_transfer_credits",
    "non_self_transfer_debits",
    "monthly_emi_obligation",
    "outstanding_loan_balance",
]

print(
    latest.loc[
        latest["monthly_income"] == 0,
        columns,
    ].head(10).to_string(index=False)
)
