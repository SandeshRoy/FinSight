
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"
OUTPUT_PATH = ROOT / "output" / "customer_monthly_profile.csv"


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DB_PATH), read_only=True)

    query = """
    WITH transaction_monthly AS (
        SELECT
            customer_id,
            DATE_TRUNC('month', CAST(txn_timestamp AS TIMESTAMP))::DATE
                AS snapshot_month,

            SUM(CASE
                WHEN LOWER(direction) = 'credit'
                 AND is_salary_credit = TRUE
                THEN amount ELSE 0
            END) AS salary_income,

            SUM(CASE
                WHEN LOWER(direction) = 'credit'
                 AND COALESCE(is_salary_credit, FALSE) = FALSE
                THEN amount ELSE 0
            END) AS other_credits,

            SUM(CASE
                WHEN LOWER(direction) = 'credit'
                THEN amount ELSE 0
            END) AS total_credits,

            SUM(CASE
                WHEN LOWER(direction) = 'debit'
                THEN amount ELSE 0
            END) AS total_debits,

            COUNT(*) AS transaction_count,

            SUM(CASE
                WHEN is_reversal = TRUE THEN 1 ELSE 0
            END) AS reversal_count,

            SUM(CASE
                WHEN is_fee = TRUE THEN amount ELSE 0
            END) AS fee_amount

        FROM transaction_fact
        GROUP BY
            customer_id,
            DATE_TRUNC('month', CAST(txn_timestamp AS TIMESTAMP))::DATE
    ),

    account_balance_monthly AS (
        SELECT
            a.customer_id,
            CAST(s.snapshot_month AS DATE) AS snapshot_month,
            SUM(s.current_balance) AS month_end_balance,
            SUM(s.average_monthly_balance) AS average_account_balance,
            COUNT(*) AS account_snapshot_count

        FROM account_monthly_snapshot s
        JOIN account_master a
          ON s.account_id = a.account_id

        GROUP BY
            a.customer_id,
            CAST(s.snapshot_month AS DATE)
    ),

    combined AS (
        SELECT
            COALESCE(t.customer_id, b.customer_id) AS customer_id,
            COALESCE(t.snapshot_month, b.snapshot_month)
                AS snapshot_month,

            COALESCE(t.salary_income, 0) AS salary_income,
            COALESCE(t.other_credits, 0) AS other_credits,
            COALESCE(t.total_credits, 0) AS total_credits,
            COALESCE(t.total_debits, 0) AS total_debits,
            COALESCE(t.transaction_count, 0) AS transaction_count,
            COALESCE(t.reversal_count, 0) AS reversal_count,
            COALESCE(t.fee_amount, 0) AS fee_amount,

            b.month_end_balance,
            b.average_account_balance,
            COALESCE(b.account_snapshot_count, 0)
                AS account_snapshot_count

        FROM transaction_monthly t
        FULL OUTER JOIN account_balance_monthly b
          ON t.customer_id = b.customer_id
         AND t.snapshot_month = b.snapshot_month
    )

    SELECT
        customer_id,
        snapshot_month,
        salary_income,
        other_credits,
        total_credits,
        total_debits,
        total_credits - total_debits AS monthly_net_cash_flow,
        transaction_count,
        reversal_count,
        fee_amount,
        month_end_balance,
        average_account_balance,
        account_snapshot_count

    FROM combined
    ORDER BY customer_id, snapshot_month
    """

    try:
        print("Building customer-month financial profiles...")

        # Execute the query and retrieve the result.
        df = con.execute(query).fetchdf()

        print(f"Query completed. Rows retrieved: {len(df):,}")

        # Write using Python rather than DuckDB COPY.
        df.to_csv(OUTPUT_PATH, index=False)

        if not OUTPUT_PATH.exists():
            raise FileNotFoundError(
                f"CSV was not created: {OUTPUT_PATH}"
            )

        # Validate the generated data.
        duplicate_keys = int(
            df.duplicated(
                subset=["customer_id", "snapshot_month"]
            ).sum()
        )

        null_customer_ids = int(df["customer_id"].isna().sum())

        print("\n========== CUSTOMER-MONTH PROFILE ==========")
        print(f"Profile rows: {len(df):,}")
        print(f"Unique customers: {df['customer_id'].nunique():,}")
        print(
            f"Unique months: {df['snapshot_month'].nunique():,}"
        )
        print(f"Duplicate customer-month keys: {duplicate_keys:,}")
        print(f"NULL customer IDs: {null_customer_ids:,}")
        print(f"Output file: {OUTPUT_PATH}")
        print("Profile export completed.")

    finally:
        con.close()


if __name__ == "__main__":
    main()
