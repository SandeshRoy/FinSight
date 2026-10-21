
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

spark_path = (
    ROOT / "output" / "bigdata"
    / "spark_customer_monthly_transactions.csv"
)
baseline_path = ROOT / "output" / "customer_monthly_profile.csv"

key_columns = ["customer_id", "snapshot_month"]

metric_columns = [
    "salary_income",
    "other_credits",
    "total_credits",
    "total_debits",
    "monthly_net_cash_flow",
    "transaction_count",
    "reversal_count",
    "fee_amount",
]


def main():
    spark_df = pd.read_csv(spark_path, parse_dates=["snapshot_month"])
    baseline_df = pd.read_csv(
        baseline_path, parse_dates=["snapshot_month"]
    )

    for name, df in [("Spark", spark_df), ("Baseline", baseline_df)]:
        if df.duplicated(key_columns).any():
            raise ValueError(f"{name} output has duplicate customer-month keys")

    comparison = baseline_df.merge(
        spark_df,
        on=key_columns,
        how="outer",
        suffixes=("_baseline", "_spark"),
        indicator=True,
        validate="one_to_one",
    )

    common = comparison[comparison["_merge"] == "both"].copy()

    print("=== ROW COVERAGE ===")
    print(f"Existing profile rows: {len(baseline_df):,}")
    print(f"Spark transaction groups: {len(spark_df):,}")
    print(f"Matching customer-month keys: {len(common):,}")
    print(
        "Existing-profile rows without Spark transaction group:",
        int((comparison["_merge"] == "left_only").sum()),
    )
    print(
        "Spark groups absent from existing profile:",
        int((comparison["_merge"] == "right_only").sum()),
    )

    print("\n=== METRIC COMPARISON ===")
    all_passed = True

    for metric in metric_columns:
        expected = common[f"{metric}_baseline"].to_numpy(dtype=float)
        actual = common[f"{metric}_spark"].to_numpy(dtype=float)

        passed = np.isclose(
            expected, actual, rtol=1e-9, atol=0.01, equal_nan=True
        )
        mismatch_count = int((~passed).sum())

        valid = np.isfinite(expected) & np.isfinite(actual)
        if valid.any():
            max_difference = float(
                np.max(np.abs(expected[valid] - actual[valid]))
            )
        else:
            max_difference = float("nan")

        status = "PASS" if mismatch_count == 0 else "CHECK"
        print(
            f"{metric}: {status} | "
            f"mismatches={mismatch_count:,} | "
            f"max_abs_difference={max_difference:.6f}"
        )

        if mismatch_count:
            all_passed = False

    print("\n=== OVERALL RESULT ===")
    if all_passed and len(common) == len(spark_df):
        print("PASS: Spark metrics match the existing profile on shared keys.")
    else:
        print("CHECK: Review metric differences or unmatched customer-month keys.")

    print(
        "\nNote: rows in the existing profile without transactions may be "
        "valid account-snapshot-only rows."
    )


if __name__ == "__main__":
    main()
