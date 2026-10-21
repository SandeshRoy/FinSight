
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"

TRANSACTION_IDS = [
    40135554,
    40163827,
    65045355,
    115073913,
]


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        placeholders = ", ".join("?" for _ in TRANSACTION_IDS)

        query = f"""
            SELECT
                t.transaction_id,
                t.customer_id,
                t.txn_timestamp,
                t.amount AS transaction_amount,
                t.direction,
                t.txn_type,
                l.loan_id,
                l.loan_type,
                l.emi_amount AS master_emi_amount,
                l.loan_status AS master_loan_status,
                s.snapshot_month,
                s.installment_due_amount,
                s.installment_paid_amount,
                s.emi_amount AS snapshot_emi_amount,
                s.outstanding_balance,
                s.loan_status AS snapshot_loan_status
            FROM transaction_fact t
            LEFT JOIN loan_master l
                ON t.customer_id = l.customer_id
            LEFT JOIN loan_monthly_snapshot s
                ON l.loan_id = s.loan_id
                AND DATE_TRUNC(
                    'month', CAST(s.snapshot_month AS DATE)
                ) = DATE_TRUNC(
                    'month', CAST(t.txn_timestamp AS TIMESTAMP)
                )
            WHERE t.transaction_id IN ({placeholders})
            ORDER BY t.transaction_id, l.loan_id
        """

        result = con.execute(
            query, TRANSACTION_IDS
        ).fetchdf()

        print("\n========== ZERO-EMI INVESTIGATION ==========\n")

        if result.empty:
            print("No matching records found.")
        else:
            print(result.to_string(index=False))

    finally:
        con.close()


if __name__ == "__main__":
    main()
