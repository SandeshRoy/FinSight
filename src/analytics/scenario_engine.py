
from pathlib import Path
import argparse
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

PROFILE_PATH = ROOT / "output" / "financial_profile.csv"
OUTPUT_PATH = ROOT / "output" / "scenario_results.csv"
SUMMARY_PATH = ROOT / "output" / "scenario_summary.csv"

REQUIRED_COLUMNS = [
    "customer_id",
    "snapshot_month",
    "estimated_monthly_income",
    "total_debits",
    "monthly_net_cash_flow",
    "monthly_emi_obligation",
]


def calculate_scenario(
    row,
    income_change_pct=0,
    expense_change_pct=0,
    emi_change_pct=0,
):
    """
    Apply hypothetical percentage changes to a customer's
    latest financial profile.

    Income change: relative to estimated monthly income.
    Expense change: relative to estimated non-EMI expenses.
    EMI change: relative to the recorded monthly EMI obligation.

    Baseline cash flow remains the observed transaction cash flow.
    """

    income = max(float(row["estimated_monthly_income"] or 0), 0)
    debits = max(float(row["total_debits"] or 0), 0)
    emi = max(float(row["monthly_emi_obligation"] or 0), 0)
    baseline = float(row["monthly_net_cash_flow"] or 0)

    # Approximation: separate EMI obligations from recorded debits
    # to reduce overlap between expense and EMI scenario changes.
    non_emi_expenses = max(debits - emi, 0)

    income_impact = income * income_change_pct / 100
    expense_impact = non_emi_expenses * expense_change_pct / 100
    emi_impact = emi * emi_change_pct / 100

    scenario_cash_flow = (
        baseline
        + income_impact
        - expense_impact
        - emi_impact
    )

    return {
        "baseline_cash_flow": baseline,
        "estimated_monthly_income": income,
        "recorded_monthly_debits": debits,
        "estimated_non_emi_expenses": non_emi_expenses,
        "monthly_emi_obligation": emi,
        "income_change_pct": income_change_pct,
        "expense_change_pct": expense_change_pct,
        "emi_change_pct": emi_change_pct,
        "income_impact": income_impact,
        "expense_impact": expense_impact,
        "emi_impact": emi_impact,
        "scenario_cash_flow": scenario_cash_flow,
        "change_from_baseline": scenario_cash_flow - baseline,
        "negative_cash_flow_after_scenario": scenario_cash_flow < 0,
    }


def main():
    parser = argparse.ArgumentParser(
        description="FinSight Financial Scenario Engine"
    )
    parser.add_argument(
        "--customer-id",
        type=int,
        help="Customer ID to simulate. If omitted, process all customers."
    )
    args = parser.parse_args()

    if not PROFILE_PATH.exists():
        raise FileNotFoundError(
            f"Financial profile not found: {PROFILE_PATH}"
        )

    df = pd.read_csv(
        PROFILE_PATH,
        usecols=lambda column: column in REQUIRED_COLUMNS,
    )

    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["snapshot_month"] = pd.to_datetime(
        df["snapshot_month"], errors="coerce"
    )
    df = df.dropna(subset=["customer_id", "snapshot_month"])

    if args.customer_id is not None:
        df = df[df["customer_id"] == args.customer_id]

        if df.empty:
            raise ValueError(
                f"No financial profile found for customer "
                f"{args.customer_id}"
            )

    # Use each customer's latest available monthly profile.
    latest = (
        df.sort_values("snapshot_month")
        .drop_duplicates("customer_id", keep="last")
        .copy()
    )

    scenarios = [
        ("Baseline", 0, 0, 0),
        ("Income down 10%", -10, 0, 0),
        ("Expenses up 10%", 0, 10, 0),
        ("EMI up 10%", 0, 0, 10),
        ("Combined stress", -10, 10, 10),
    ]

    results = []

    for _, row in latest.iterrows():
        for name, income_pct, expense_pct, emi_pct in scenarios:
            result = calculate_scenario(
                row,
                income_change_pct=income_pct,
                expense_change_pct=expense_pct,
                emi_change_pct=emi_pct,
            )

            results.append({
                "customer_id": row["customer_id"],
                "snapshot_month": row["snapshot_month"].date().isoformat(),
                "scenario_name": name,
                **result,
            })

    output = pd.DataFrame(results)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(OUTPUT_PATH, index=False)

    summary = (
        output.groupby("scenario_name")
        .agg(
            customers=("customer_id", "nunique"),
            median_baseline_cash_flow=("baseline_cash_flow", "median"),
            median_scenario_cash_flow=("scenario_cash_flow", "median"),
            median_change=("change_from_baseline", "median"),
            customers_with_negative_cash_flow=(
                "negative_cash_flow_after_scenario", "sum"
            ),
        )
        .reset_index()
    )

    summary.to_csv(SUMMARY_PATH, index=False)

    print("\n========== FINSIGHT SCENARIO ENGINE ==========")
    print(f"Customers processed: {latest['customer_id'].nunique():,}")
    print(f"Scenarios per customer: {len(scenarios)}")
    print(f"Scenario rows: {len(output):,}")

    print("\n========== SCENARIO SUMMARY ==========")
    print(summary.round(2).to_string(index=False))

    print(f"\nDetailed results: {OUTPUT_PATH}")
    print(f"Summary report:   {SUMMARY_PATH}")

    print(
        "\nIMPORTANT: These are hypothetical estimates, not forecasts "
        "or professional financial advice. The baseline uses recorded "
        "transaction cash flow. Non-EMI expenses are approximated by "
        "subtracting recorded EMI obligations from total debits. "
        "Synthetic data limitations may affect interpretation."
    )


if __name__ == "__main__":
    main()
