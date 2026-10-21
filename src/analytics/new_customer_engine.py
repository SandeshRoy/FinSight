
from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd


# --------------------------------------------------
# 1. PATHS AND CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

MODEL_DIR = ROOT / "models"
OUTPUT_DIR = ROOT / "output"

MODEL_PATH = MODEL_DIR / "customer_pattern_kmeans.joblib"
SCALER_PATH = MODEL_DIR / "customer_pattern_scaler.joblib"
METADATA_PATH = MODEL_DIR / "customer_pattern_metadata.json"

REFERENCE_PATH = OUTPUT_DIR / "customer_pattern_reference.csv"
SUMMARY_PATH = OUTPUT_DIR / "customer_pattern_summary.csv"

FEATURES = [
    "monthly_income",
    "avg_monthly_expenses",
    "avg_monthly_emi",
    "avg_outstanding_loan",
]

REFERENCE_MONTHS = 12

FEATURE_LABELS = {
    "monthly_income": "Monthly income",
    "avg_monthly_expenses": "Monthly expenses",
    "avg_monthly_emi": "Monthly EMI",
    "avg_outstanding_loan": "Outstanding loan",
}


# --------------------------------------------------
# 2. LOAD AND VALIDATE MODEL ARTIFACTS
# --------------------------------------------------

def load_artifacts():
    """Load and validate the trained model and reference data."""

    required_files = [
        MODEL_PATH,
        SCALER_PATH,
        METADATA_PATH,
        REFERENCE_PATH,
        SUMMARY_PATH,
    ]

    missing_files = [
        str(path)
        for path in required_files
        if not path.exists()
    ]

    if missing_files:
        raise FileNotFoundError(
            "The following required FinSight files are missing:\n"
            + "\n".join(missing_files)
            + "\nRun src\\analytics\\customer_pattern_engine.py first."
        )

    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)

    with open(
        METADATA_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        metadata = json.load(file)

    reference = pd.read_csv(REFERENCE_PATH)
    summary = pd.read_csv(SUMMARY_PATH)

    # Verify the model's expected feature definitions.
    metadata_features = metadata.get("features")

    if metadata_features != FEATURES:
        raise ValueError(
            "Model metadata features do not match the expected features. "
            "Retrain the model before continuing."
        )

    if metadata.get("reference_period_months") != REFERENCE_MONTHS:
        raise ValueError(
            "The model was not trained with the expected 12-month period."
        )

    if metadata.get("require_complete_reference_period") is not True:
        raise ValueError(
            "Model metadata does not confirm complete 12-month coverage. "
            "Retrain the model before continuing."
        )

    # Verify reference and summary columns.
    required_reference_columns = [
        "customer_id",
        "segment_id",
        "months_available",
        *FEATURES,
    ]

    required_summary_columns = [
        "segment_id",
        "customers",
        "monthly_income_mean",
        "monthly_expenses_mean",
        "monthly_emi_mean",
        "outstanding_loan_mean",
    ]

    missing_reference = [
        column
        for column in required_reference_columns
        if column not in reference.columns
    ]

    missing_summary = [
        column
        for column in required_summary_columns
        if column not in summary.columns
    ]

    if missing_reference:
        raise ValueError(
            "Reference file is missing columns: "
            + ", ".join(missing_reference)
        )

    if missing_summary:
        raise ValueError(
            "Summary file is missing columns: "
            + ", ".join(missing_summary)
        )

    if reference.empty:
        raise ValueError("The customer reference dataset is empty.")

    if reference["customer_id"].duplicated().any():
        raise ValueError(
            "Duplicate customer IDs exist in the reference dataset."
        )

    if not (
        pd.to_numeric(
            reference["months_available"],
            errors="coerce",
        ) == REFERENCE_MONTHS
    ).all():
        raise ValueError(
            "The reference dataset contains customers without "
            "complete 12-month coverage."
        )

    # Validate that all reference features are usable.
    reference[FEATURES] = reference[FEATURES].apply(
        pd.to_numeric,
        errors="coerce",
    )

    reference_values = reference[FEATURES].to_numpy(dtype=float)

    if not np.isfinite(reference_values).all():
        raise ValueError(
            "The reference dataset contains missing or non-finite features."
        )

    if (reference_values < 0).any():
        raise ValueError(
            "The reference dataset contains negative financial features."
        )

    if not set(reference["segment_id"].unique()).issubset(
        set(range(int(metadata["n_clusters"])))
    ):
        raise ValueError(
            "Reference segment IDs do not match the model metadata."
        )

    if len(FEATURES) != getattr(model, "n_features_in_", None):
        raise ValueError(
            "The trained model feature count does not match the input form."
        )

    if len(FEATURES) != getattr(scaler, "n_features_in_", None):
        raise ValueError(
            "The scaler feature count does not match the input form."
        )

    print("FinSight model artifacts loaded successfully.")
    print(
        "Reference customers:",
        f"{len(reference):,}",
    )
    print(
        "Reference period:",
        metadata["reference_start_month"],
        "to",
        metadata["reference_end_month"],
    )

    return model, scaler, metadata, reference, summary


# --------------------------------------------------
# 3. VALIDATE NEW CUSTOMER INPUT
# --------------------------------------------------

def validate_customer_input(
    monthly_income,
    monthly_expenses,
    monthly_emi,
    outstanding_loan,
):
    """Validate and normalize financial inputs."""

    values = {
        "monthly_income": monthly_income,
        "avg_monthly_expenses": monthly_expenses,
        "avg_monthly_emi": monthly_emi,
        "avg_outstanding_loan": outstanding_loan,
    }

    validated = {}

    for feature, value in values.items():
        if isinstance(value, (bool, np.bool_)):
            raise ValueError(
                f"{FEATURE_LABELS[feature]} must be a non-negative number."
            )

        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"{FEATURE_LABELS[feature]} must be a valid number."
            ) from None

        if not np.isfinite(numeric_value):
            raise ValueError(
                f"{FEATURE_LABELS[feature]} must be a finite number."
            )

        if numeric_value < 0:
            raise ValueError(
                f"{FEATURE_LABELS[feature]} cannot be negative."
            )

        validated[feature] = numeric_value

    # EMI is a component of expenses in typical household budgeting.
    # Warn rather than reject if EMI exceeds the supplied expenses.
    warnings = []

    if validated["avg_monthly_emi"] > validated["avg_monthly_expenses"]:
        warnings.append(
            "The entered EMI exceeds the entered monthly expenses. "
            "Check whether monthly expenses include EMI."
        )

    if (
        validated["monthly_income"] == 0
        and validated["avg_monthly_expenses"] > 0
    ):
        warnings.append(
            "Expenses are positive but recorded monthly income is zero. "
            "Verify the income figure before interpreting the result."
        )

    return validated, warnings


# --------------------------------------------------
# 4. COMPARE CUSTOMER WITH HISTORICAL PEERS
# --------------------------------------------------

def compare_customer(
    monthly_income,
    monthly_expenses,
    monthly_emi,
    outstanding_loan,
):
    """
    Assign a customer to a historical segment and compare
    the customer's financial inputs with that segment.
    """

    values, input_warnings = validate_customer_input(
        monthly_income=monthly_income,
        monthly_expenses=monthly_expenses,
        monthly_emi=monthly_emi,
        outstanding_loan=outstanding_loan,
    )

    model, scaler, metadata, reference, summary = load_artifacts()

    customer = pd.DataFrame(
        [values],
        columns=FEATURES,
    )

    # Use exactly the transformation applied during training.
    transformed = np.log1p(customer[FEATURES])
    scaled = scaler.transform(transformed)

    segment_id = int(model.predict(scaled)[0])

    # Select customers belonging to the assigned segment.
    peers = reference.loc[
        reference["segment_id"] == segment_id
    ].copy()

    if peers.empty:
        raise ValueError(
            f"No historical customers were found in segment {segment_id}."
        )

    comparisons = []

    for feature in FEATURES:
        customer_value = float(customer.iloc[0][feature])
        peer_mean = float(peers[feature].mean())
        peer_median = float(peers[feature].median())

        difference = customer_value - peer_mean

        if peer_mean > 0:
            difference_percent = (
                difference / peer_mean
            ) * 100
        elif customer_value == 0:
            difference_percent = 0.0
        else:
            difference_percent = None

        if customer_value > peer_mean:
            comparison_text = "Above segment average"
        elif customer_value < peer_mean:
            comparison_text = "Below segment average"
        else:
            comparison_text = "Equal to segment average"

        comparisons.append({
            "feature": feature,
            "label": FEATURE_LABELS[feature],
            "customer_value": round(customer_value, 2),
            "segment_mean": round(peer_mean, 2),
            "segment_median": round(peer_median, 2),
            "difference": round(difference, 2),
            "difference_percent": (
                round(difference_percent, 2)
                if difference_percent is not None
                else None
            ),
            "comparison": comparison_text,
        })

    segment_summary_rows = summary.loc[
        summary["segment_id"] == segment_id
    ]

    if segment_summary_rows.empty:
        segment_summary = {}
    else:
        segment_summary = (
            segment_summary_rows.iloc[0].to_dict()
        )

    # Calculate monthly cash flow as an input-based estimate.
    # This is not a model-trained prediction.
    estimated_monthly_cash_flow = (
        values["monthly_income"]
        - values["avg_monthly_expenses"]
    )

    # Generate cautious, descriptive insights.
    insights = []

    income_comparison = next(
        item for item in comparisons
        if item["feature"] == "monthly_income"
    )

    expense_comparison = next(
        item for item in comparisons
        if item["feature"] == "avg_monthly_expenses"
    )

    emi_comparison = next(
        item for item in comparisons
        if item["feature"] == "avg_monthly_emi"
    )

    loan_comparison = next(
        item for item in comparisons
        if item["feature"] == "avg_outstanding_loan"
    )

    if estimated_monthly_cash_flow < 0:
        insights.append(
            "Your entered monthly expenses exceed your entered income."
        )
    elif estimated_monthly_cash_flow == 0:
        insights.append(
            "Your entered income equals your entered monthly expenses."
        )
    else:
        insights.append(
            "Your entered income exceeds your entered monthly expenses."
        )

    if expense_comparison["customer_value"] > (
        expense_comparison["segment_mean"]
    ):
        insights.append(
            "Your entered monthly expenses are above the assigned "
            "segment average."
        )

    if emi_comparison["customer_value"] > (
        emi_comparison["segment_mean"]
    ):
        insights.append(
            "Your entered monthly EMI is above the assigned "
            "segment average."
        )

    if loan_comparison["customer_value"] > (
        loan_comparison["segment_mean"]
    ):
        insights.append(
            "Your entered outstanding loan is above the assigned "
            "segment average."
        )

    if income_comparison["customer_value"] < (
        income_comparison["segment_mean"]
    ):
        insights.append(
            "Your entered monthly income is below the assigned "
            "segment average."
        )

    return {
        "segment_id": segment_id,
        "segment_label": f"Segment {segment_id}",
        "segment_customer_count": int(len(peers)),
        "reference_customer_count": int(len(reference)),
        "reference_start_month": metadata["reference_start_month"],
        "reference_end_month": metadata["reference_end_month"],
        "reference_months": int(
            metadata["reference_period_months"]
        ),
        "model_features": FEATURES.copy(),
        "customer_input": values,
        "estimated_monthly_cash_flow": round(
            estimated_monthly_cash_flow,
            2,
        ),
        "comparisons": comparisons,
        "insights": insights,
        "input_warnings": input_warnings,
        "segment_summary": segment_summary,
        "disclaimer": (
            "This analysis compares entered financial information "
            "with a segment learned from synthetic historical data. "
            "Segment IDs are not credit grades. This tool does not "
            "predict loan default, guarantee outcomes, or provide "
            "personalized financial advice. Verify all inputs and "
            "consider the limitations of the source data."
        ),
    }


# --------------------------------------------------
# 5. DISPLAY TEST RESULTS
# --------------------------------------------------

def main():
    """Run a sample analysis to test the new-customer engine."""

    # Example values for software testing only.
    result = compare_customer(
        monthly_income=80000,
        monthly_expenses=25000,
        monthly_emi=5000,
        outstanding_loan=200000,
    )

    print("\n========== FINSIGHT NEW CUSTOMER ANALYSIS ==========")

    print("Assigned segment:", result["segment_label"])
    print(
        "Customers in this segment:",
        f"{result['segment_customer_count']:,}",
    )
    print(
        "Reference customers:",
        f"{result['reference_customer_count']:,}",
    )
    print(
        "Reference period:",
        result["reference_start_month"],
        "to",
        result["reference_end_month"],
    )

    print("\n========== CUSTOMER FINANCIAL INPUT ==========")

    for feature, value in result["customer_input"].items():
        print(
            f"{FEATURE_LABELS[feature]}: "
            f"₹{value:,.2f}"
        )

    print(
        "\nEstimated monthly cash flow: "
        f"₹{result['estimated_monthly_cash_flow']:,.2f}"
    )

    print(
        "\n========== CUSTOMER VS SEGMENT AVERAGE =========="
    )

    for item in result["comparisons"]:
        print(f"\n{item['label']}")
        print(
            f"  Customer value: "
            f"₹{item['customer_value']:,.2f}"
        )
        print(
            f"  Segment average: "
            f"₹{item['segment_mean']:,.2f}"
        )
        print(
            f"  Segment median: "
            f"₹{item['segment_median']:,.2f}"
        )
        print(f"  Comparison: {item['comparison']}")

        if item["difference_percent"] is not None:
            print(
                f"  Difference: "
                f"{item['difference_percent']:+.2f}%"
            )
        else:
            print(
                "  Percentage difference unavailable "
                "because the segment average is zero."
            )

    print("\n========== EXPLAINABLE INSIGHTS ==========")

    for insight in result["insights"]:
        print(f"- {insight}")

    if result["input_warnings"]:
        print("\n========== INPUT WARNINGS ==========")

        for warning in result["input_warnings"]:
            print(f"- {warning}")

    print("\n========== DISCLAIMER ==========")
    print(result["disclaimer"])


if __name__ == "__main__":
    main()
