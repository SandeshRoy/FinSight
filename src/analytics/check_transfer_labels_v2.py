
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

segments = pd.read_csv(
    ROOT / "output" / "customer_segments_v2.csv"
)

con = duckdb.connect(
    str(ROOT / "data" / "bank_data.db"),
    read_only=True
)

con.register(
    "segments",
    segments[["customer_id", "segment_id"]]
)

# Compare transaction directions and counterparty labels
labels = con.execute("""
    SELECT
        s.segment_id,
        t.direction,
        COALESCE(t.counterparty_type, '<NULL>') AS counterparty_type,
        COALESCE(t.txn_type, '<NULL>') AS txn_type,
        COUNT(*) AS transaction_count,
        SUM(t.amount) AS total_amount,
        COUNT(DISTINCT t.customer_id) AS customers
    FROM transaction_fact t
    JOIN segments s
      ON s.customer_id = t.customer_id
    GROUP BY
        s.segment_id,
        t.direction,
        COALESCE(t.counterparty_type, '<NULL>'),
        COALESCE(t.txn_type, '<NULL>')
    ORDER BY s.segment_id, t.direction, transaction_count DESC
""").df()

print("\n========== TRANSACTION LABELS BY NEW CLUSTER ==========")
print(labels.to_string(index=False))

labels.to_csv(
    ROOT / "output" / "transfer_label_audit_v2.csv",
    index=False
)

# Inspect the customer schema for persona-related fields
schema = con.execute("""
    DESCRIBE SELECT * FROM customer_master
""").df()

print("\n========== CUSTOMER MASTER COLUMNS ==========")
print(schema[["column_name", "column_type"]].to_string(index=False))

con.close()
print("\nSaved: output/transfer_label_audit_v2.csv")
