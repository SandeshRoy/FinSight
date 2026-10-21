
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"
PROFILE_PATH = (
    ROOT / "output" / "customer_monthly_profile_spark.csv"
)
OUTPUT_PATH = ROOT / "output" / "financial_profile.csv"

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def main():
    for path in (DB_PATH, PROFILE_PATH):
        if not path.exists():
            raise FileNotFoundError(f"Required file not found: {path}")

    con = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        profile_path = PROFILE_PATH.as_posix().replace("'", "''")
        output_path = OUTPUT_PATH.as_posix().replace("'", "''")

        query = f"""
        COPY (
            WITH base AS (
                SELECT
                    p.*,
                    c.annual_income,
                    c.annual_income / 12.0
                        AS estimated_monthly_income
                FROM read_csv_auto('{profile_path}') p
                JOIN customer_master c
                  ON p.customer_id = c.customer_id
            ),

            loan_monthly AS (
                SELECT
                    l.customer_id,
                    CAST(s.snapshot_month AS DATE)
                        AS snapshot_month,

                    SUM(
                        CASE
                            WHEN COALESCE(s.outstanding_balance, 0) > 0
                             AND LOWER(COALESCE(s.loan_status, ''))
                                 = 'active'
                            THEN COALESCE(s.emi_amount, 0)
                            ELSE 0
                        END
                    ) AS monthly_emi_obligation,

                    SUM(
                        COALESCE(s.outstanding_balance, 0)
                    ) AS outstanding_loan_balance,

                    SUM(
                        COALESCE(s.overdue_amount, 0)
                    ) AS total_overdue_amount,

                    MAX(s.dpd_days) AS max_days_past_due,

                    COUNT(
                        DISTINCT CASE
                            WHEN COALESCE(s.outstanding_balance, 0) > 0
                             AND LOWER(COALESCE(s.loan_status, ''))
                                 = 'active'
                            THEN l.loan_id
                        END
                    ) AS active_loan_count

                FROM loan_monthly_snapshot s
                JOIN loan_master l
                  ON s.loan_id = l.loan_id

                GROUP BY
                    l.customer_id,
                    CAST(s.snapshot_month AS DATE)
            ),

            enriched AS (
                SELECT
                    b.*,
                    COALESCE(
                        lm.monthly_emi_obligation, 0
                    ) AS monthly_emi_obligation,

                    COALESCE(
                        lm.outstanding_loan_balance, 0
                    ) AS outstanding_loan_balance,

                    COALESCE(
                        lm.total_overdue_amount, 0
                    ) AS total_overdue_amount,

                    COALESCE(
                        lm.max_days_past_due, 0
                    ) AS max_days_past_due,

                    COALESCE(
                        lm.active_loan_count, 0
                    ) AS active_loan_count

                FROM base b
                LEFT JOIN loan_monthly lm
                  ON b.customer_id = lm.customer_id
                 AND CAST(b.snapshot_month AS DATE)
                     = lm.snapshot_month
            )

            SELECT
                *,
                CASE
                    WHEN total_credits > 0
                    THEN total_debits / total_credits
                    ELSE NULL
                END AS expense_to_credit_ratio,

                CASE
                    WHEN total_credits > 0
                    THEN monthly_net_cash_flow / total_credits
                    ELSE NULL
                END AS net_cash_flow_ratio,

                CASE
                    WHEN estimated_monthly_income > 0
                    THEN monthly_emi_obligation
                         / estimated_monthly_income
                    ELSE NULL
                END AS emi_to_estimated_income_ratio,

                CASE
                    WHEN salary_income > 0
                    THEN monthly_emi_obligation / salary_income
                    ELSE NULL
                END AS emi_to_salary_ratio,

                CASE
                    WHEN monthly_net_cash_flow < 0 THEN TRUE
                    ELSE FALSE
                END AS has_negative_cash_flow

            FROM enriched
            ORDER BY customer_id, snapshot_month

        ) TO '{output_path}'
        (HEADER, DELIMITER ',');
        """

        con.execute(query)

        summary = con.execute(f"""
            SELECT
                COUNT(*) AS rows,
                COUNT(DISTINCT customer_id) AS customers,
                COUNT(DISTINCT snapshot_month) AS months,
                SUM(CASE WHEN has_negative_cash_flow
                         THEN 1 ELSE 0 END) AS negative_cash_flow_rows,
                SUM(CASE WHEN emi_to_estimated_income_ratio IS NULL
                         THEN 1 ELSE 0 END) AS missing_emi_income_ratio,
                SUM(CASE WHEN outstanding_loan_balance > 0
                         THEN 1 ELSE 0 END) AS rows_with_outstanding_loans
            FROM read_csv_auto('{output_path}')
        """).fetchone()

        print("\\n========== FINSIGHT FINANCIAL PROFILE ENGINE ==========")
        print(f"Profile rows: {summary[0]:,}")
        print(f"Customers: {summary[1]:,}")
        print(f"Months: {summary[2]:,}")
        print(f"Negative cash-flow rows: {summary[3]:,}")
        print(f"Rows without EMI/income ratio: {summary[4]:,}")
        print(f"Rows with outstanding loans: {summary[5]:,}")
        print(f"Output saved to: {OUTPUT_PATH}")

    finally:
        con.close()


if __name__ == "__main__":
    main()
