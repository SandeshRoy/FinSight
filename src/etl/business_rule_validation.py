
from pathlib import Path
import duckdb
import csv

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"
OUTPUT_PATH = ROOT / "output" / "business_rule_validation.csv"

CHECKS = [
    (
        "Transaction amount is zero or negative",
        """
        SELECT transaction_id
        FROM transaction_fact
        WHERE amount <= 0
        """,
        "Review transaction sign conventions and reversal records."
    ),
    (
        "Transaction date does not match timestamp date",
        """
        SELECT transaction_id
        FROM transaction_fact
        WHERE TRY_CAST(txn_date AS DATE) IS NOT NULL
          AND TRY_CAST(txn_timestamp AS DATE) IS NOT NULL
          AND TRY_CAST(txn_date AS DATE)
              <> TRY_CAST(txn_timestamp AS DATE)
        """,
        "Transaction date should normally match its timestamp date."
    ),
    (
        "Transaction date cannot be parsed",
        """
        SELECT transaction_id
        FROM transaction_fact
        WHERE TRY_CAST(txn_date AS DATE) IS NULL
        """,
        "Check the stored format and validity of txn_date."
    ),
    (
        "Negative annual customer income",
        """
        SELECT customer_id
        FROM customer_master
        WHERE annual_income < 0
        """,
        "Verify customer income values."
    ),
    (
        "Non-positive loan sanctioned amount",
        """
        SELECT loan_id
        FROM loan_master
        WHERE sanctioned_amount <= 0
        """,
        "Review loan amount and loan-status conventions."
    ),
    (
        "Negative loan interest rate",
        """
        SELECT loan_id
        FROM loan_master
        WHERE interest_rate < 0
        """,
        "Verify loan interest-rate values."
    ),
    (
        "Loan interest rate above 100 percent",
        """
        SELECT loan_id
        FROM loan_master
        WHERE interest_rate > 100
        """,
        "Review the value and whether the rate is stored as a percentage."
    ),
    (
        "Non-positive loan tenure",
        """
        SELECT loan_id
        FROM loan_master
        WHERE tenure_months <= 0
        """,
        "Verify the recorded loan tenure."
    ),
    (
        "Negative loan EMI",
        """
        SELECT loan_id
        FROM loan_master
        WHERE emi_amount < 0
        """,
        "Verify the EMI amount."
    ),
    (
        "Negative outstanding loan balance",
        """
        SELECT loan_id
        FROM loan_monthly_snapshot
        WHERE outstanding_balance < 0
        """,
        "Review the loan balance and accounting conventions."
    ),
    (
        "Negative overdue amount",
        """
        SELECT loan_id
        FROM loan_monthly_snapshot
        WHERE overdue_amount < 0
        """,
        "Verify overdue amount conventions."
    ),
    (
        "Negative installment due or paid amount",
        """
        SELECT loan_id
        FROM loan_monthly_snapshot
        WHERE installment_due_amount < 0
           OR installment_paid_amount < 0
        """,
        "Review repayment values and adjustment conventions."
    ),
]

def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    results = []

    try:
        print("\n========== FINSIGHT BUSINESS RULE VALIDATION ==========\n")

        for name, sql, explanation in CHECKS:
            count = con.execute(
                f"SELECT COUNT(*) FROM ({sql}) AS flagged"
            ).fetchone()[0]

            sample_rows = con.execute(
                f"SELECT * FROM ({sql}) AS flagged LIMIT 5"
            ).fetchall()

            sample_text = "; ".join(
                ", ".join(str(value) for value in row)
                for row in sample_rows
            )

            results.append({
                "check": name,
                "flagged_count": count,
                "explanation": explanation,
                "sample_records": sample_text,
            })

            status = "PASS" if count == 0 else "REVIEW"
            print(f"[{status}] {name}: {count:,} record(s)")

            if sample_text:
                print(f"       Examples: {sample_text}")

        with OUTPUT_PATH.open(
            "w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "check",
                    "flagged_count",
                    "explanation",
                    "sample_records",
                ],
            )
            writer.writeheader()
            writer.writerows(results)

        print(f"\nChecks performed: {len(results)}")
        print(f"Report saved to: {OUTPUT_PATH}")
        print("No source records were modified.")

    finally:
        con.close()


if __name__ == "__main__":
    main()
