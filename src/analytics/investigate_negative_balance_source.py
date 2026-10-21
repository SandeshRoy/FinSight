import duckdb
import pandas as pd

DB_PATH = "data/bank_data.db"
CUSTOMER_ID = 1007416

con = duckdb.connect(DB_PATH, read_only=True)

print("\n========== ACCOUNT MASTER ==========")

account = con.execute("""
    SELECT *
    FROM account_master
    WHERE customer_id = ?
""", [CUSTOMER_ID]).df()

print(account.to_string(index=False))

account_ids = account["account_id"].tolist()

print("\n========== ACCOUNT MONTHLY SNAPSHOTS ==========")

snapshots = con.execute("""
    SELECT *
    FROM account_monthly_snapshot
    WHERE account_id IN (
        SELECT account_id
        FROM account_master
        WHERE customer_id = ?
    )
    ORDER BY snapshot_month
""", [CUSTOMER_ID]).df()

print(snapshots.to_string(index=False))

print("\n========== TRANSACTIONS ==========")

transactions = con.execute("""
    SELECT *
    FROM transaction_fact
    WHERE customer_id = ?
    ORDER BY txn_timestamp
""", [CUSTOMER_ID]).df()

print("Transaction count:", len(transactions))

if not transactions.empty:
    print("\nTransaction totals by direction:")

    print(
        transactions.groupby("direction")["amount"]
        .agg(["count", "sum", "min", "max"])
        .to_string()
    )

    print("\nFirst 20 transactions:")

    print(
        transactions.head(20).to_string(index=False)
    )

    print("\nLast 20 transactions:")

    print(
        transactions.tail(20).to_string(index=False)
    )

print("\n========== INVESTIGATION COMPLETE ==========")

con.close()