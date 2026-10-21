
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import silhouette_score

ROOT = Path(__file__).resolve().parents[2]

PROFILE_PATH = ROOT / "output" / "customer_monthly_profile_v2.csv"
FINANCIAL_PATH = ROOT / "output" / "financial_profile.csv"
DB_PATH = ROOT / "data" / "bank_data.db"

OUTPUT_PATH = ROOT / "output" / "customer_segments_v2.csv"
SUMMARY_PATH = ROOT / "output" / "customer_segment_summary_v2.csv"

# 1. Load transfer-aware monthly profile
profile = pd.read_csv(PROFILE_PATH)
financial = pd.read_csv(FINANCIAL_PATH)

for df in [profile, financial]:
    df["snapshot_month"] = (
        pd.to_datetime(df["snapshot_month"])
        .dt.to_period("M")
        .dt.to_timestamp()
    )

# Confirm the expected source columns exist
required_profile = [
    "customer_id",
    "snapshot_month",
    "non_self_transfer_credits",
    "non_self_transfer_debits",
    "non_self_transfer_net_flow",
    "transaction_count",
    "average_account_balance",
]

missing_profile = set(required_profile) - set(profile.columns)
required_financial = [
    "customer_id",
    "snapshot_month",
    "annual_income",
    "monthly_emi_obligation",
    "outstanding_loan_balance",
]
missing_financial = set(required_financial) - set(financial.columns)

if missing_profile:
    raise ValueError(
        f"Missing profile columns: {sorted(missing_profile)}"
    )
if missing_financial:
    raise ValueError(
        f"Missing financial columns: {sorted(missing_financial)}"
    )

financial = financial[required_financial]

monthly = profile.merge(
    financial,
    on=["customer_id", "snapshot_month"],
    how="left",
    validate="one_to_one",
)

# 2. Calculate one row per customer
monthly["negative_non_self_flow"] = (
    monthly["non_self_transfer_net_flow"] < 0
).astype(int)

customer = monthly.groupby("customer_id").agg(
    annual_income=("annual_income", "first"),
    avg_monthly_non_self_credits=("non_self_transfer_credits", "mean"),
    avg_monthly_non_self_debits=("non_self_transfer_debits", "mean"),
    avg_monthly_non_self_net_flow=("non_self_transfer_net_flow", "mean"),
    avg_account_balance=("average_account_balance", "mean"),
    avg_monthly_emi=("monthly_emi_obligation", "mean"),
    avg_outstanding_loan=("outstanding_loan_balance", "mean"),
    avg_transaction_count=("transaction_count", "mean"),
    negative_non_self_flow_rate=("negative_non_self_flow", "mean"),
).reset_index()

# 3. Check for missing values before modelling
feature_columns = [
    "annual_income",
    "avg_monthly_non_self_credits",
    "avg_monthly_non_self_debits",
    "avg_monthly_non_self_net_flow",
    "avg_account_balance",
    "avg_monthly_emi",
    "avg_outstanding_loan",
    "avg_transaction_count",
    "negative_non_self_flow_rate",
]

if customer[feature_columns].isna().any().any():
    missing = customer[feature_columns].isna().sum()
    raise ValueError(
        "Missing feature values detected:\n"
        + missing[missing > 0].to_string()
    )

if not np.isfinite(customer[feature_columns].to_numpy()).all():
    raise ValueError("Non-finite feature values detected.")

# 4. Log-transform nonnegative scale-sensitive features
log_columns = [
    "annual_income",
    "avg_monthly_non_self_credits",
    "avg_monthly_non_self_debits",
    "avg_account_balance",
    "avg_monthly_emi",
    "avg_outstanding_loan",
    "avg_transaction_count",
]

X = customer[feature_columns].copy()

for col in log_columns:
    X[col] = np.log1p(X[col].clip(lower=0))

# Signed net cash flow and negative-flow rate remain untransformed
scaler = RobustScaler()
X_scaled = scaler.fit_transform(X)

# 5. Train a separate four-cluster model
model = KMeans(
    n_clusters=4,
    random_state=42,
    n_init=10,
)

customer["segment_id"] = model.fit_predict(X_scaled)

# 6. Evaluate cluster separation
silhouette = silhouette_score(
    X_scaled,
    customer["segment_id"],
    sample_size=min(2000, len(customer)),
    random_state=42,
)

# 7. Summarize the new segments using original units
summary = customer.groupby("segment_id").agg(
    customers=("customer_id", "nunique"),
    annual_income_mean=("annual_income", "mean"),
    avg_monthly_non_self_credits=(
        "avg_monthly_non_self_credits", "mean"
    ),
    avg_monthly_non_self_debits=(
        "avg_monthly_non_self_debits", "mean"
    ),
    avg_monthly_non_self_net_flow=(
        "avg_monthly_non_self_net_flow", "mean"
    ),
    avg_account_balance=("avg_account_balance", "mean"),
    avg_monthly_emi=("avg_monthly_emi", "mean"),
    avg_outstanding_loan=("avg_outstanding_loan", "mean"),
    avg_transaction_count=("avg_transaction_count", "mean"),
    negative_non_self_flow_rate=(
        "negative_non_self_flow_rate", "mean"
    ),
).reset_index()

customer.to_csv(OUTPUT_PATH, index=False)
summary.to_csv(SUMMARY_PATH, index=False)

print("\n========== TRANSFER-AWARE CLUSTERING V2 ==========")
print("Customers:", len(customer))
print("Unique customer IDs:", customer["customer_id"].nunique())
print("Clusters:", customer["segment_id"].nunique())
print("Silhouette score:", round(silhouette, 4))

print("\n========== CLUSTER DISTRIBUTION ==========")
print(
    customer["segment_id"]
    .value_counts()
    .sort_index()
    .to_string()
)

print("\n========== NEW CLUSTER SUMMARY ==========")
print(summary.round(2).to_string(index=False))

# 8. Compare against the original segment assignments
original_path = ROOT / "output" / "customer_segments.csv"
original = pd.read_csv(original_path)[
    ["customer_id", "segment_id"]
].rename(columns={"segment_id": "original_segment_id"})

comparison = original.merge(
    customer[["customer_id", "segment_id"]].rename(
        columns={"segment_id": "new_segment_id"}
    ),
    on="customer_id",
    how="inner",
    validate="one_to_one",
)

print("\n========== ORIGINAL VS NEW ASSIGNMENTS ==========")
print("Customers compared:", len(comparison))
print("\nOriginal-to-new cluster counts:")
print(pd.crosstab(
    comparison["original_segment_id"],
    comparison["new_segment_id"]
).to_string())

con = duckdb.connect(str(DB_PATH), read_only=True)
con.close()

print("\nSaved:")
print(OUTPUT_PATH)
print(SUMMARY_PATH)
