
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"

CASES = [
    (40135554, 30000337),
    (40163827, 30000302),
    (65045355, 30025508),
    (115073913, 30075261),
]


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        for transaction_id, loan_id in CASES:
            print(f"\n{'=' * 70}")
            print(f"Transaction {transaction_id} | Loan {loan_id}")
            print("=" * 70)

            transaction = con.execute(
                """
                SELECT transaction_id, txn_timestamp, customer_id,
                       account_id, amount, direction, txn_type,
                       is_reversal, balance_after_txn
                FROM transaction_fact
                WHERE transaction_id = ?
                """,
                [transaction_id],
            ).fetchdf()

            print("\nTransaction:")
            print(transaction.to_string(index=False))

            history = con.execute(
                """
                SELECT snapshot_month, emi_amount,
                       installment_due_amount,
                       installment_paid_amount,
                       outstanding_balance, dpd_days,
                       overdue_amount, loan_status
                FROM loan_monthly_snapshot
                WHERE loan_id = ?
                ORDER BY snapshot_month
                """,
                [loan_id],
            ).fetchdf()

            print("\nLoan snapshot history:")
            print(history.to_string(index=False))

    finally:
        con.close()


if __name__ == "__main__":
    main()
