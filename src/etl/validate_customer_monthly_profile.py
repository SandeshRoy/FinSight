
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "output" / "customer_monthly_profile.csv"


def main():
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(
            f"Profile CSV not found: {PROFILE_PATH}"
        )

    con = duckdb.connect(":memory:")

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
                "NULL customer IDs",
                """
                SELECT COUNT(*) FROM profile
                WHERE customer_id IS NULL
                """
            ),
            (
                "NULL snapshot months",
                """
                SELECT COUNT(*) FROM profile
                WHERE snapshot_month IS NULL
                """
            ),
            (
                "Negative transaction counts",
                """
                SELECT COUNT(*) FROM profile
                WHERE transaction_count < 0
                """
            ),
            (
                "Negative credit totals",
                """
                SELECT COUNT(*) FROM profile
                WHERE total_credits < 0
                """
            ),
            (
                "Negative debit totals",
                """
                SELECT COUNT(*) FROM profile
                WHERE total_debits < 0
                """
            ),
            (
                "Net cash flow calculation mismatches",
                """
                SELECT COUNT(*) FROM profile
                WHERE ABS(
                    monthly_net_cash_flow -
                    (total_credits - total_debits)
                ) > 0.01
                """
            ),
            (
                "Salary income exceeds total credits",
                """
                SELECT COUNT(*) FROM profile
                WHERE salary_income > total_credits + 0.01
                """
            ),
        ]

        print("\n========== PROFILE VALIDATION ==========\n")

        for name, sql in checks:
            count = con.execute(sql).fetchone()[0]
            status = "PASS" if count == 0 else "REVIEW"
            print(f"[{status}] {name}: {count:,}")

        print("\n========== PROFILE SUMMARY ==========\n")

        summary = con.execute("""
            SELECT
                COUNT(*) AS rows,
                COUNT(DISTINCT customer_id) AS customers,
                COUNT(DISTINCT snapshot_month) AS months,
                SUM(transaction_count) AS transactions,
                SUM(
                    CASE WHEN month_end_balance IS NULL
                         THEN 1 ELSE 0 END
                ) AS missing_month_end_balances,
                SUM(
                    CASE WHEN average_account_balance IS NULL
                         THEN 1 ELSE 0 END
                ) AS missing_average_balances,
                SUM(
                    CASE WHEN transaction_count = 0
                         THEN 1 ELSE 0 END
                ) AS months_without_transactions
            FROM profile
        """).fetchone()

        labels = [
            "Profile rows",
            "Unique customers",
            "Distinct months",
            "Total transactions represented",
            "Rows missing month-end balance",
            "Rows missing average balance",
            "Rows without transactions",
        ]

        for label, value in zip(labels, summary):
            print(f"{label}: {value:,}" if value is not None
                  else f"{label}: None")

    finally:
        con.close()


if __name__ == "__main__":
    main()
