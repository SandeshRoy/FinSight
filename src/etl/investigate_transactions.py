
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"

transaction_ids = [
    65045355,
    115073913,
    40135554,
    40163827,
]

def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        placeholders = ", ".join("?" for _ in transaction_ids)

        query = f"""
            SELECT
                transaction_id,
                customer_id,
                account_id,
                txn_timestamp,
                txn_date,
                txn_type,
                direction,
                amount,
                is_reversal,
                is_fee,
                merchant_category,
                merchant_name,
                balance_after_txn
            FROM transaction_fact
            WHERE transaction_id IN ({placeholders})
            ORDER BY transaction_id
        """

        rows = con.execute(query, transaction_ids).fetchdf()

        print("\n========== FLAGGED TRANSACTIONS ==========\n")

        if rows.empty:
            print("No matching transaction IDs found.")
        else:
            print(rows.to_string(index=False))

        print("\n========== TRANSACTION SIGN SUMMARY ==========\n")
        print(
            con.execute("""
                SELECT
                    direction,
                    txn_type,
                    is_reversal,
                    COUNT(*) AS record_count,
                    MIN(amount) AS minimum_amount,
                    MAX(amount) AS maximum_amount
                FROM transaction_fact
                WHERE amount <= 0
                GROUP BY direction, txn_type, is_reversal
                ORDER BY record_count DESC
            """).fetchdf().to_string(index=False)
        )

    finally:
        con.close()

if __name__ == "__main__":
    main()
