
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import silhouette_score

ROOT = Path(__file__).resolve().parents[2]

profile = pd.read_csv(
    ROOT / "output" / "customer_monthly_profile_v2.csv"
)
financial = pd.read_csv(
    ROOT / "output" / "financial_profile.csv"
)

for df in (profile, financial):
    df["snapshot_month"] = (
        pd.to_datetime(df["snapshot_month"])
        .dt.to_period("M")
        .dt.to_timestamp()
    )

financial_cols = [
    "customer_id",
    "snapshot_month",
    "annual_income",
    "monthly_emi_obligation",
    "outstanding_loan_balance",
]

monthly = profile.merge(
    financial[financial_cols],
    on=["customer_id", "snapshot_month"],
    how="left",
    validate="one_to_one",
)

# Build one record per customer.
monthly["transaction_count"] = monthly["transaction_count"].fillna(0)

customer = monthly.groupby("customer_id").agg(
    annual_income=("annual_income", "first"),
    avg_monthly_non_self_credits=("non_self_transfer_credits", "mean"),
    avg_monthly_debits=("non_self_transfer_debits", "mean"),
    avg_account_balance=("average_account_balance", "mean"),
    avg_monthly_emi=("monthly_emi_obligation", "mean"),
    avg_outstanding_loan=("outstanding_loan_balance", "mean"),
    avg_transaction_count=("transaction_count", "mean"),
).reset_index()

features = [
    "annual_income",
    "avg_monthly_non_self_credits",
    "avg_monthly_debits",
    "avg_account_balance",
    "avg_monthly_emi",
    "avg_outstanding_loan",
    "avg_transaction_count",
]

if customer[features].isna().any().any():
    raise ValueError(
        "Missing values found:\n"
        + customer[features].isna().sum().to_string()
    )

X = customer[features].copy()

if not np.isfinite(X.to_numpy()).all():
    raise ValueError("Non-finite feature values detected.")

# Log-transform nonnegative, scale-sensitive features.
for col in features:
    X[col] = np.log1p(X[col].clip(lower=0))

X_scaled = RobustScaler().fit_transform(X)

model = KMeans(
    n_clusters=4,
    random_state=42,
    n_init=10,
)

customer["segment_id"] = model.fit_predict(X_scaled)

score = silhouette_score(
    X_scaled,
    customer["segment_id"],
    sample_size=min(2000, len(customer)),
    random_state=42,
)

summary = customer.groupby("segment_id").agg(
    customers=("customer_id", "nunique"),
    annual_income_mean=("annual_income", "mean"),
    avg_non_self_credits=("avg_monthly_non_self_credits", "mean"),
    avg_monthly_debits=("avg_monthly_debits", "mean"),
    avg_account_balance=("avg_account_balance", "mean"),
    avg_monthly_emi=("avg_monthly_emi", "mean"),
    avg_outstanding_loan=("avg_outstanding_loan", "mean"),
    avg_transaction_count=("avg_transaction_count", "mean"),
).reset_index()

customer.to_csv(
    ROOT / "output" / "customer_segments_v3.csv",
    index=False,
)
summary.to_csv(
    ROOT / "output" / "customer_segment_summary_v3.csv",
    index=False,
)

print("\n========== CLUSTERING V3 ==========")
print("Customers:", len(customer))
print("Unique customers:", customer["customer_id"].nunique())
print("Silhouette score:", round(score, 4))

print("\n========== CLUSTER DISTRIBUTION ==========")
print(customer["segment_id"].value_counts().sort_index().to_string())

print("\n========== CLUSTER SUMMARY ==========")
print(summary.round(2).to_string(index=False))

# Compare with the transfer-aware v2 model.
v2 = pd.read_csv(
    ROOT / "output" / "customer_segments_v2.csv"
)[["customer_id", "segment_id"]].rename(
    columns={"segment_id": "v2_segment_id"}
)

comparison = v2.merge(
    customer[["customer_id", "segment_id"]].rename(
        columns={"segment_id": "v3_segment_id"}
    ),
    on="customer_id",
    validate="one_to_one",
)

print("\n========== V2 VS V3 ==========")
print(pd.crosstab(
    comparison["v2_segment_id"],
    comparison["v3_segment_id"],
).to_string())

print("\nSaved:")
print("output/customer_segments_v3.csv")
print("output/customer_segment_summary_v3.csv")
