
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"
SEGMENT_PATH = ROOT / "output" / "customer_segments.csv"
OUTPUT_DIR = ROOT / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    segments = pd.read_csv(SEGMENT_PATH)

    # Inspect the full cluster and retain a small sample for review.
    cluster3 = segments.loc[
        segments["segment_id"] == 3,
        ["customer_id", "segment_id", "annual_income",
         "avg_monthly_credits", "avg_monthly_debits",
         "avg_monthly_emi", "avg_outstanding_loan"]
    ].copy()

    con = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        con.register("cluster3_input", cluster3)

        query = """
        WITH transaction_stats AS (
            SELECT
                t.customer_id,
                COUNT(*) AS transaction_count,
                SUM(CASE WHEN LOWER(t.direction) = 'credit'
                         THEN t.amount ELSE 0 END) AS raw_credits,
                SUM(CASE WHEN LOWER(t.direction) = 'debit'
                         THEN t.amount ELSE 0 END) AS raw_debits,
                SUM(CASE WHEN t.is_salary_credit = TRUE
                         THEN t.amount ELSE 0 END) AS raw_salary_credits,
                SUM(CASE WHEN t.txn_type = 'Loan EMI Payment'
                         THEN 1 ELSE 0 END) AS emi_transaction_count,
                SUM(CASE WHEN t.txn_type = 'Loan EMI Payment'
                               AND t.amount = 0
                         THEN 1 ELSE 0 END) AS zero_amount_emi_count
            FROM transaction_fact t
            JOIN cluster3_input c
              ON t.customer_id = c.customer_id
            GROUP BY t.customer_id
        ),
        loan_stats AS (
            SELECT
                l.customer_id,
                COUNT(DISTINCT l.loan_id) AS loan_count,
                SUM(l.emi_amount) AS master_emi_sum
            FROM loan_master l
            JOIN cluster3_input c
              ON l.customer_id = c.customer_id
            GROUP BY l.customer_id
        ),
        snapshot_stats AS (
            SELECT
                l.customer_id,
                COUNT(*) AS snapshot_count,
                SUM(CASE WHEN s.outstanding_balance > 0
                         THEN 1 ELSE 0 END) AS positive_balance_snapshots,
                MAX(s.outstanding_balance) AS max_snapshot_balance,
                ARG_MAX(
                    s.outstanding_balance,
                    CAST(s.snapshot_month AS DATE)
                ) AS latest_snapshot_balance
            FROM loan_monthly_snapshot s
            JOIN loan_master l ON s.loan_id = l.loan_id
            JOIN cluster3_input c ON l.customer_id = c.customer_id
            GROUP BY l.customer_id
        )
        SELECT
            c.*,
            COALESCE(t.transaction_count, 0) AS raw_transaction_count,
            COALESCE(t.raw_credits, 0) AS raw_credits,
            COALESCE(t.raw_debits, 0) AS raw_debits,
            COALESCE(t.raw_salary_credits, 0) AS raw_salary_credits,
            COALESCE(t.emi_transaction_count, 0) AS emi_transaction_count,
            COALESCE(t.zero_amount_emi_count, 0) AS zero_amount_emi_count,
            COALESCE(l.loan_count, 0) AS loan_count,
            COALESCE(l.master_emi_sum, 0) AS master_emi_sum,
            COALESCE(s.snapshot_count, 0) AS loan_snapshot_count,
            COALESCE(s.positive_balance_snapshots, 0)
                AS positive_balance_snapshots,
            COALESCE(s.max_snapshot_balance, 0)
                AS max_snapshot_balance,
            COALESCE(s.latest_snapshot_balance, 0)
                AS latest_snapshot_balance
        FROM cluster3_input c
        LEFT JOIN transaction_stats t USING (customer_id)
        LEFT JOIN loan_stats l USING (customer_id)
        LEFT JOIN snapshot_stats s USING (customer_id)
        ORDER BY c.avg_monthly_debits ASC
        """

        result = con.execute(query).fetchdf()

        print("\n========== CLUSTER 3 SOURCE DATA CHECK ==========\n")
        print(f"Customers checked: {len(result):,}")
        print(
            f"Customers with no raw transactions: "
            f"{(result['raw_transaction_count'] == 0).sum():,}"
        )
        print(
            f"Customers with loans in loan_master: "
            f"{(result['loan_count'] > 0).sum():,}"
        )
        print(
            f"Customers with positive loan snapshots: "
            f"{(result['positive_balance_snapshots'] > 0).sum():,}"
        )
        print(
            f"Customers with zero-value EMI transactions: "
            f"{(result['zero_amount_emi_count'] > 0).sum():,}"
        )

        print("\nLowest-debit customer examples:")
        print(result.head(15).round(2).to_string(index=False))

        output_path = OUTPUT_DIR / "cluster3_source_diagnostics.csv"
        result.to_csv(output_path, index=False)
        print(f"\nFull diagnostic report saved to: {output_path}")

    finally:
        con.close()


if __name__ == "__main__":
    main()
