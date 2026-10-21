
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import silhouette_score

ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = ROOT / "output" / "financial_profile.csv"
OUTPUT_DIR = ROOT / "output"

SEGMENT_PATH = OUTPUT_DIR / "customer_segments.csv"
SUMMARY_PATH = OUTPUT_DIR / "customer_segment_summary.csv"

N_CLUSTERS = 4
RANDOM_STATE = 42


def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Financial profile not found: {INPUT_PATH}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(INPUT_PATH)

    # Convert the month column to a consistent date format.
    df["snapshot_month"] = pd.to_datetime(
        df["snapshot_month"], errors="coerce"
    )

    # Treat boolean values safely when reading the CSV.
    df["has_negative_cash_flow"] = (
        df["has_negative_cash_flow"]
        .astype(str)
        .str.lower()
        .map({"true": 1.0, "false": 0.0})
    )

    # Create one row per customer using their observed months.
    customer = (
        df.groupby("customer_id")
        .agg(
            annual_income=("annual_income", "first"),
            avg_monthly_credits=("total_credits", "mean"),
            avg_monthly_debits=("total_debits", "mean"),
            avg_net_cash_flow=("monthly_net_cash_flow", "mean"),
            avg_account_balance=("average_account_balance", "mean"),
            avg_monthly_emi=("monthly_emi_obligation", "mean"),
            avg_outstanding_loan=("outstanding_loan_balance", "mean"),
            avg_transaction_count=("transaction_count", "mean"),
            negative_cash_flow_rate=(
                "has_negative_cash_flow", "mean"
            ),
            avg_expense_to_credit_ratio=(
                "expense_to_credit_ratio", "mean"
            ),
        )
        .reset_index()
    )

    # Exclude the identifier from the model features.
    feature_cols = [
        "annual_income",
        "avg_monthly_credits",
        "avg_monthly_debits",
        "avg_net_cash_flow",
        "avg_account_balance",
        "avg_monthly_emi",
        "avg_outstanding_loan",
        "avg_transaction_count",
        "negative_cash_flow_rate",
        "avg_expense_to_credit_ratio",
    ]

    X = customer[feature_cols].replace(
        [np.inf, -np.inf], np.nan
    )

    # Replace missing feature values with column medians.
    X = X.fillna(X.median()).fillna(0)

    # Financial amounts are usually skewed. Apply log1p to
    # non-negative magnitude features, leaving signed cash
    # flow and ratios in their original form.
    log_cols = [
        "annual_income",
        "avg_monthly_credits",
        "avg_monthly_debits",
        "avg_account_balance",
        "avg_monthly_emi",
        "avg_outstanding_loan",
        "avg_transaction_count",
    ]

    for col in log_cols:
        X[col] = np.log1p(X[col].clip(lower=0))

    # RobustScaler reduces the influence of extreme values.
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X)

    model = KMeans(
        n_clusters=N_CLUSTERS,
        random_state=RANDOM_STATE,
        n_init=10,
    )

    customer["segment_id"] = model.fit_predict(X_scaled)

    # Calculate silhouette score on a sample to limit runtime.
    sample_size = min(2000, len(customer))
    sample_rng = np.random.default_rng(RANDOM_STATE)
    sample_indices = sample_rng.choice(
        len(customer), size=sample_size, replace=False
    )

    sample_labels = customer.iloc[
        sample_indices
    ]["segment_id"]

    if sample_labels.nunique() > 1:
        score = silhouette_score(
            X_scaled[sample_indices],
            sample_labels,
        )
    else:
        score = float("nan")

    # Create interpretable cluster summaries.
    summary = (
        customer.groupby("segment_id")
        .agg(
            customer_count=("customer_id", "count"),
            avg_annual_income=("annual_income", "mean"),
            avg_monthly_credits=("avg_monthly_credits", "mean"),
            avg_monthly_debits=("avg_monthly_debits", "mean"),
            avg_net_cash_flow=("avg_net_cash_flow", "mean"),
            avg_account_balance=("avg_account_balance", "mean"),
            avg_monthly_emi=("avg_monthly_emi", "mean"),
            avg_outstanding_loan=("avg_outstanding_loan", "mean"),
            avg_negative_cash_flow_rate=(
                "negative_cash_flow_rate", "mean"
            ),
        )
        .reset_index()
    )

    customer.to_csv(SEGMENT_PATH, index=False)
    summary.to_csv(SUMMARY_PATH, index=False)

    print("\n========== FINSIGHT CUSTOMER SEGMENTATION ==========")
    print(f"Customers segmented: {len(customer):,}")
    print(f"Number of clusters: {N_CLUSTERS}")
    print(f"Silhouette score (sample): {score:.4f}")
    print(f"\nSegment summary:\n{summary.to_string(index=False)}")
    print(f"\nCustomer assignments: {SEGMENT_PATH}")
    print(f"Segment summary: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
