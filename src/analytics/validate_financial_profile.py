
from pathlib import Path
import duckdb
import csv

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "output" / "financial_profile.csv"
REPORT_PATH = ROOT / "output" / "financial_profile_validation.csv"


def main():
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(f"File not found: {PROFILE_PATH}")

    con = duckdb.connect(":memory:")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        path = PROFILE_PATH.as_posix().replace("'", "''")

        con.execute(f"""
            CREATE VIEW profile AS
            SELECT * FROM read_csv_auto('{path}')
        """)

        checks = [
            (
                "Duplicate customer-month keys",
                """
                SELECT COUNT(*) FROM (
                    SELECT customer_id, snapshot_month
                    FROM profile
                    GROUP BY customer_id, snapshot_month
                    HAVING COUNT(*) > 1
                ) x
                """
            ),
            (
                "NULL customer IDs or months",
                """
                SELECT COUNT(*) FROM profile
                WHERE customer_id IS NULL
                   OR snapshot_month IS NULL
                """
            ),
            (
                "Negative estimated monthly income",
                """
                SELECT COUNT(*) FROM profile
                WHERE estimated_monthly_income < 0
                """
            ),
            (
                "Negative credit or debit totals",
                """
                SELECT COUNT(*) FROM profile
                WHERE total_credits < 0
                   OR total_debits < 0
                """
            ),
            (
                "Net cash flow formula mismatch",
                """
                SELECT COUNT(*) FROM profile
                WHERE ABS(
                    monthly_net_cash_flow -
                    (total_credits - total_debits)
                ) > 0.01
                """
            ),
            (
                "Expense-to-credit ratio mismatch",
                """
                SELECT COUNT(*) FROM profile
                WHERE (
                    total_credits > 0
                    AND (
                        expense_to_credit_ratio IS NULL
                        OR ABS(
                            expense_to_credit_ratio -
                            total_debits / total_credits
                        ) > 0.000001
                    )
                ) OR (
                    total_credits <= 0
                    AND expense_to_credit_ratio IS NOT NULL
                )
                """
            ),
            (
                "EMI-to-income ratio mismatch",
                """
                SELECT COUNT(*) FROM profile
                WHERE (
                    estimated_monthly_income > 0
                    AND (
                        emi_to_estimated_income_ratio IS NULL
                        OR ABS(
                            emi_to_estimated_income_ratio -
                            monthly_emi_obligation /
                            estimated_monthly_income
                        ) > 0.000001
                    )
                ) OR (
                    estimated_monthly_income <= 0
                    AND emi_to_estimated_income_ratio IS NOT NULL
                )
                """
            ),
            (
                "Negative outstanding loan balances",
                """
                SELECT COUNT(*) FROM profile
                WHERE outstanding_loan_balance < 0
                """
            ),
            (
                "Negative EMI obligations",
                """
                SELECT COUNT(*) FROM profile
                WHERE monthly_emi_obligation < 0
                """
            ),
            (
                "EMI obligation exceeds estimated monthly income",
                """
                SELECT COUNT(*) FROM profile
                WHERE estimated_monthly_income > 0
                  AND monthly_emi_obligation >
                      estimated_monthly_income
                """
            ),
        ]

        results = []

        print("\n========== FINANCIAL PROFILE VALIDATION ==========\n")

        for name, sql in checks:
            count = con.execute(sql).fetchone()[0]

            results.append({
                "check": name,
                "flagged_count": count,
            })

            status = "PASS" if count == 0 else "REVIEW"
            print(f"[{status}] {name}: {count:,}")

        with REPORT_PATH.open(
            "w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["check", "flagged_count"],
            )
            writer.writeheader()
            writer.writerows(results)

        print(f"\nReport saved to: {REPORT_PATH}")

        print("\n========== FINANCIAL INDICATOR SUMMARY ==========\n")

        summary = con.execute("""
            SELECT
                ROUND(AVG(total_credits), 2),
                ROUND(AVG(total_debits), 2),
                ROUND(AVG(monthly_net_cash_flow), 2),
                ROUND(AVG(monthly_emi_obligation), 2),
                ROUND(AVG(outstanding_loan_balance), 2),
                ROUND(AVG(emi_to_estimated_income_ratio), 4)
            FROM profile
        """).fetchone()

        labels = [
            "Average monthly credits",
            "Average monthly debits",
            "Average monthly net cash flow",
            "Average monthly EMI obligation",
            "Average outstanding loan balance",
            "Average EMI-to-estimated-income ratio",
        ]

        for label, value in zip(labels, summary):
            print(f"{label}: {value}")

        print(
            "\nNote: These are averages across customer-month rows, "
            "not averages per unique customer."
        )

    finally:
        con.close()


if __name__ == "__main__":
    main()
