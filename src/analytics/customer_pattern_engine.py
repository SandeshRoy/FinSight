
from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd

from sklearn.cluster import KMeans
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import silhouette_score


# --------------------------------------------------
# 1. PATHS AND CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

OUTPUT = ROOT / "output"
MODELS = ROOT / "models"

PROFILE_FILE = OUTPUT / "customer_monthly_profile_v2.csv"
FINANCIAL_FILE = OUTPUT / "financial_profile.csv"

N_CLUSTERS = 4
RANDOM_STATE = 42
N_INIT = 10
REFERENCE_MONTHS = 12

FEATURES = [
    "monthly_income",
    "avg_monthly_expenses",
    "avg_monthly_emi",
    "avg_outstanding_loan",
]


# --------------------------------------------------
# 2. LOAD AND VALIDATE SOURCE DATA
# --------------------------------------------------

def load_monthly_data():
    if not PROFILE_FILE.exists():
        raise FileNotFoundError(
            f"Profile file not found: {PROFILE_FILE}"
        )

    if not FINANCIAL_FILE.exists():
        raise FileNotFoundError(
            f"Financial profile file not found: {FINANCIAL_FILE}"
        )

    profile = pd.read_csv(PROFILE_FILE)
    financial = pd.read_csv(FINANCIAL_FILE)

    required_profile = [
        "customer_id",
        "snapshot_month",
        "non_self_transfer_credits",
        "non_self_transfer_debits",
    ]

    required_financial = [
        "customer_id",
        "snapshot_month",
        "monthly_emi_obligation",
        "outstanding_loan_balance",
    ]

    for column in required_profile:
        if column not in profile.columns:
            raise ValueError(
                f"Missing profile column: {column}"
            )

    for column in required_financial:
        if column not in financial.columns:
            raise ValueError(
                f"Missing financial column: {column}"
            )

    for df in (profile, financial):
        df["snapshot_month"] = (
            pd.to_datetime(
                df["snapshot_month"],
                errors="coerce",
            )
            .dt.to_period("M")
            .dt.to_timestamp()
        )

    profile = profile[required_profile].copy()
    financial = financial[required_financial].copy()

    key = ["customer_id", "snapshot_month"]

    # Each source must have one record per customer per month.
    if profile.duplicated(key).any():
        raise ValueError(
            "Duplicate customer-month keys in profile data."
        )

    if financial.duplicated(key).any():
        raise ValueError(
            "Duplicate customer-month keys in financial data."
        )

    monthly = profile.merge(
        financial,
        on=key,
        how="inner",
        validate="one_to_one",
    )

    if monthly.empty:
        raise ValueError(
            "No matching customer-month records were found."
        )

    monthly = monthly.dropna(
        subset=["customer_id", "snapshot_month"]
    )

    numeric_columns = [
        "non_self_transfer_credits",
        "non_self_transfer_debits",
        "monthly_emi_obligation",
        "outstanding_loan_balance",
    ]

    for column in numeric_columns:
        monthly[column] = pd.to_numeric(
            monthly[column],
            errors="coerce",
        )

    monthly = monthly.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    return monthly


# --------------------------------------------------
# 3. BUILD COMPLETE 12-MONTH CUSTOMER REFERENCES
# --------------------------------------------------

def build_reference_data(monthly):
    latest_month = monthly["snapshot_month"].max()

    # Latest month plus the preceding 11 months.
    start_month = (
        latest_month.to_period("M")
        - (REFERENCE_MONTHS - 1)
    ).to_timestamp()

    recent = monthly.loc[
        monthly["snapshot_month"].between(
            start_month,
            latest_month,
            inclusive="both",
        )
    ].copy()

    if recent.empty:
        raise ValueError(
            "No records found in the reference period."
        )

    # Align training features with the new-customer form.
    recent["monthly_income"] = (
        recent["non_self_transfer_credits"]
    )

    recent["avg_monthly_expenses"] = (
        recent["non_self_transfer_debits"]
    )

    recent["avg_monthly_emi"] = (
        recent["monthly_emi_obligation"]
    )

    recent["avg_outstanding_loan"] = (
        recent["outstanding_loan_balance"]
    )

    # Count distinct months available for each customer.
    month_counts = (
        recent.groupby("customer_id")["snapshot_month"]
        .nunique()
        .rename("months_available")
    )

    # Retain only customers represented in all 12 months.
    complete_customer_ids = month_counts[
        month_counts == REFERENCE_MONTHS
    ].index

    recent = recent[
        recent["customer_id"].isin(
            complete_customer_ids
        )
    ].copy()

    if recent.empty:
        raise ValueError(
            "No customers have all 12 months of data. "
            "Check the reference period and source datasets."
        )

    # Average each customer's features across the same
    # 12-month period.
    reference = (
        recent.groupby("customer_id")[FEATURES]
        .mean()
        .reset_index()
    )

    reference = reference.merge(
        month_counts.rename("months_available"),
        left_on="customer_id",
        right_index=True,
        how="left",
        validate="one_to_one",
    )

    # This should be exactly 12 for every retained customer.
    if not (
        reference["months_available"] == REFERENCE_MONTHS
    ).all():
        raise ValueError(
            "Reference customers do not all have 12 months."
        )

    print("\n========== REFERENCE PERIOD ==========")
    print(f"Start month: {start_month.date()}")
    print(f"Latest month: {latest_month.date()}")
    print(f"Required months per customer: {REFERENCE_MONTHS}")
    print(
        "Customers with complete monthly coverage: "
        f"{len(reference):,}"
    )

    return reference, start_month, latest_month


# --------------------------------------------------
# 4. CLEAN FEATURES
# --------------------------------------------------

def clean_reference_data(reference):
    reference = reference.copy()

    reference[FEATURES] = reference[FEATURES].apply(
        pd.to_numeric,
        errors="coerce",
    )

    reference = reference.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    missing_mask = reference[FEATURES].isna().any(axis=1)
    negative_mask = (reference[FEATURES] < 0).any(axis=1)

    invalid_mask = missing_mask | negative_mask

    print("\n========== FEATURE QUALITY ==========")
    print(f"Customers before cleaning: {len(reference):,}")
    print(
        "Rows with missing/non-finite features: "
        f"{int(missing_mask.sum()):,}"
    )
    print(
        "Rows with negative features: "
        f"{int(negative_mask.sum()):,}"
    )

    if invalid_mask.any():
        print(
            "Excluding invalid customer rows: "
            f"{int(invalid_mask.sum()):,}"
        )

        reference = reference.loc[
            ~invalid_mask
        ].copy()

    if reference["customer_id"].duplicated().any():
        raise ValueError(
            "Reference customer IDs are not unique."
        )

    if len(reference) < N_CLUSTERS:
        raise ValueError(
            f"At least {N_CLUSTERS} valid customers are required."
        )

    if reference[FEATURES].isna().any().any():
        raise ValueError(
            "Missing feature values remain after cleaning."
        )

    if not (
        reference["months_available"] == REFERENCE_MONTHS
    ).all():
        raise ValueError(
            "Incomplete customer histories remain in the reference."
        )

    return reference


# --------------------------------------------------
# 5. TRAIN K-MEANS MODEL
# --------------------------------------------------

def train_model(reference):
    # Log transformation reduces the influence of large
    # differences between monetary values.
    transformed = np.log1p(reference[FEATURES])

    scaler = RobustScaler()
    scaled = scaler.fit_transform(transformed)

    model = KMeans(
        n_clusters=N_CLUSTERS,
        random_state=RANDOM_STATE,
        n_init=N_INIT,
    )

    reference = reference.copy()
    reference["segment_id"] = model.fit_predict(scaled)

    # Evaluate using a reproducible sample.
    sample_size = min(2000, len(reference))

    sample_positions = reference.sample(
        n=sample_size,
        random_state=RANDOM_STATE,
    ).index

    sample = reference.loc[sample_positions]

    sample_scaled = scaler.transform(
        np.log1p(sample[FEATURES])
    )

    if sample["segment_id"].nunique() > 1:
        score = silhouette_score(
            sample_scaled,
            sample["segment_id"],
        )
    else:
        score = float("nan")

    return reference, model, scaler, float(score), sample_size


# --------------------------------------------------
# 6. CREATE SEGMENT SUMMARY
# --------------------------------------------------

def build_summary(reference):
    summary = (
        reference.groupby("segment_id")
        .agg(
            customers=("customer_id", "nunique"),
            monthly_income_mean=(
                "monthly_income",
                "mean",
            ),
            monthly_expenses_mean=(
                "avg_monthly_expenses",
                "mean",
            ),
            monthly_emi_mean=(
                "avg_monthly_emi",
                "mean",
            ),
            outstanding_loan_mean=(
                "avg_outstanding_loan",
                "mean",
            ),
            months_available_mean=(
                "months_available",
                "mean",
            ),
        )
        .reset_index()
    )

    return summary


# --------------------------------------------------
# 7. SAVE MODEL AND REFERENCE ARTIFACTS
# --------------------------------------------------

def save_artifacts(
    reference,
    summary,
    model,
    scaler,
    score,
    sample_size,
    start_month,
    latest_month,
):
    MODELS.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    reference_path = (
        OUTPUT / "customer_pattern_reference.csv"
    )

    summary_path = (
        OUTPUT / "customer_pattern_summary.csv"
    )

    model_path = (
        MODELS / "customer_pattern_kmeans.joblib"
    )

    scaler_path = (
        MODELS / "customer_pattern_scaler.joblib"
    )

    metadata_path = (
        MODELS / "customer_pattern_metadata.json"
    )

    reference.to_csv(reference_path, index=False)
    summary.to_csv(summary_path, index=False)

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    metadata = {
        "model": "KMeans",
        "n_clusters": N_CLUSTERS,
        "random_state": RANDOM_STATE,
        "n_init": N_INIT,
        "features": FEATURES,
        "transformation": "log1p",
        "scaler": "RobustScaler",
        "reference_period_months": REFERENCE_MONTHS,
        "require_complete_reference_period": True,
        "reference_start_month": str(start_month.date()),
        "reference_end_month": str(latest_month.date()),
        "reference_customers": int(len(reference)),
        "silhouette_score_sample": (
            score if np.isfinite(score) else None
        ),
        "silhouette_sample_size": int(sample_size),
        "feature_definitions": {
            "monthly_income": (
                "Average monthly non-self-transfer credits "
                "over the complete 12-month reference period."
            ),
            "avg_monthly_expenses": (
                "Average monthly non-self-transfer debits "
                "over the complete 12-month reference period."
            ),
            "avg_monthly_emi": (
                "Average monthly EMI obligation over the "
                "complete 12-month reference period."
            ),
            "avg_outstanding_loan": (
                "Average outstanding loan balance over the "
                "complete 12-month reference period."
            ),
        },
        "limitations": [
            "Reference data is synthetic.",
            "Only customers with 12 distinct months are included.",
            "Non-self-transfer credits may not capture all real income.",
            "Cluster IDs are unsupervised groups, not credit-risk grades.",
            "The model does not predict loan default.",
            "Results depend on the quality and coverage of source data.",
        ],
    }

    with open(
        metadata_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(metadata, file, indent=4)

    print("\n========== SAVED MODEL ARTIFACTS ==========")
    print(model_path)
    print(scaler_path)
    print(metadata_path)
    print(reference_path)
    print(summary_path)


# --------------------------------------------------
# 8. MAIN EXECUTION
# --------------------------------------------------

def main():
    print("Loading monthly financial data...")

    monthly = load_monthly_data()

    print(
        f"Matched customer-month rows: {len(monthly):,}"
    )

    reference, start_month, latest_month = (
        build_reference_data(monthly)
    )

    reference = clean_reference_data(reference)

    (
        reference,
        model,
        scaler,
        score,
        sample_size,
    ) = train_model(reference)

    summary = build_summary(reference)

    save_artifacts(
        reference=reference,
        summary=summary,
        model=model,
        scaler=scaler,
        score=score,
        sample_size=sample_size,
        start_month=start_month,
        latest_month=latest_month,
    )

    print("\n========== FINSIGHT 12-MONTH MODEL ==========")
    print(f"Reference customers: {len(reference):,}")
    print(f"Clusters: {N_CLUSTERS}")
    print(
        f"Reference period: {start_month.date()} "
        f"to {latest_month.date()}"
    )
    print(f"Silhouette score: {score:.4f}")

    print("\n========== CLUSTER DISTRIBUTION ==========")
    print(
        reference["segment_id"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print("\n========== CLUSTER SUMMARY ==========")
    print(summary.to_string(index=False))

    print("\n========== MONTHS AVAILABLE ==========")
    print(
        reference["months_available"]
        .value_counts()
        .sort_index()
        .to_string()
    )


if __name__ == "__main__":
    main()
