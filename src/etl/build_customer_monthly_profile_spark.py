
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[2]

DB_PATH = ROOT / "data" / "bank_data.db"
SPARK_PATH = (
    ROOT / "output" / "spark_validation"
    / "spark_customer_monthly_transactions_clean.csv"
)
OUTPUT_PATH = ROOT / "output" / "customer_monthly_profile_spark.csv"


def main():
    for path in (DB_PATH, SPARK_PATH):
        if not path.exists():
            raise FileNotFoundError(f"Required file not found: {path}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    spark_path = SPARK_PATH.as_posix().replace("'", "''")
    output_path = OUTPUT_PATH.as_posix().replace("'", "''")

    con = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        query = f"""
        COPY (
            WITH spark_transactions AS (
                SELECT
                    CAST(customer_id AS BIGINT) AS customer_id,
                    CAST(snapshot_month AS DATE) AS snapshot_month,
                    COALESCE(salary_income, 0) AS salary_income,
                    COALESCE(other_credits, 0) AS other_credits,
                    COALESCE(total_credits, 0) AS total_credits,
                    COALESCE(total_debits, 0) AS total_debits,
                    COALESCE(monthly_net_cash_flow, 0)
                        AS monthly_net_cash_flow,
                    COALESCE(transaction_count, 0)
                        AS transaction_count,
                    COALESCE(reversal_count, 0) AS reversal_count,
                    COALESCE(fee_amount, 0) AS fee_amount
                FROM read_csv_auto('{spark_path}')
            ),

            account_balance_monthly AS (
                SELECT
                    CAST(a.customer_id AS BIGINT) AS customer_id,
                    CAST(s.snapshot_month AS DATE) AS snapshot_month,
                    SUM(s.current_balance) AS month_end_balance,
                    SUM(s.average_monthly_balance)
                        AS average_account_balance,
                    COUNT(*) AS account_snapshot_count
                FROM account_monthly_snapshot s
                JOIN account_master a
                  ON s.account_id = a.account_id
                GROUP BY
                    CAST(a.customer_id AS BIGINT),
                    CAST(s.snapshot_month AS DATE)
            ),

            combined AS (
                SELECT
                    COALESCE(t.customer_id, b.customer_id)
                        AS customer_id,
                    COALESCE(t.snapshot_month, b.snapshot_month)
                        AS snapshot_month,

                    COALESCE(t.salary_income, 0) AS salary_income,
                    COALESCE(t.other_credits, 0) AS other_credits,
                    COALESCE(t.total_credits, 0) AS total_credits,
                    COALESCE(t.total_debits, 0) AS total_debits,
                    COALESCE(t.monthly_net_cash_flow, 0)
                        AS monthly_net_cash_flow,
                    COALESCE(t.transaction_count, 0)
                        AS transaction_count,
                    COALESCE(t.reversal_count, 0) AS reversal_count,
                    COALESCE(t.fee_amount, 0) AS fee_amount,

                    b.month_end_balance,
                    b.average_account_balance,
                    COALESCE(b.account_snapshot_count, 0)
                        AS account_snapshot_count

                FROM spark_transactions t
                FULL OUTER JOIN account_balance_monthly b
                  ON t.customer_id = b.customer_id
                 AND t.snapshot_month = b.snapshot_month
            )

            SELECT *
            FROM combined
            ORDER BY customer_id, snapshot_month
        ) TO '{output_path}'
        (HEADER, DELIMITER ',');
        """

        con.execute(query)

        # Validate the generated profile.
        result = con.execute(f"""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT customer_id) AS customers,
                COUNT(DISTINCT snapshot_month) AS months,
                COUNT(*) FILTER (
                    WHERE customer_id IS NULL
                ) AS missing_customer_ids,
                COUNT(*) FILTER (
                    WHERE snapshot_month IS NULL
                ) AS missing_months,
                COUNT(*) FILTER (
                    WHERE transaction_count = 0
                      AND account_snapshot_count > 0
                ) AS account_only_rows
            FROM read_csv_auto('{output_path}')
        """).fetchone()

        duplicate_count = con.execute(f"""
            SELECT COUNT(*)
            FROM (
                SELECT customer_id, snapshot_month
                FROM read_csv_auto('{output_path}')
                GROUP BY customer_id, snapshot_month
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]

        print("\\n========== FINSIGHT SPARK PROFILE ==========")
        print(f"Profile rows: {result[0]:,}")
        print(f"Unique customers: {result[1]:,}")
        print(f"Unique months: {result[2]:,}")
        print(f"Missing customer IDs: {result[3]:,}")
        print(f"Missing months: {result[4]:,}")
        print(f"Account-only rows preserved: {result[5]:,}")
        print(f"Duplicate customer-month keys: {duplicate_count:,}")
        print(f"Output: {OUTPUT_PATH}")

        if result[3] or result[4] or duplicate_count:
            raise ValueError(
                "Profile validation failed. Review the output before "
                "using it in downstream engines."
            )

        print("PROFILE VALIDATION: PASS")

    finally:
        con.close()


if __name__ == "__main__":
    main()
