
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"

segments = pd.read_csv(
    ROOT / "output" / "customer_segments_v3.csv"
)

con = duckdb.connect(str(DB_PATH), read_only=True)
con.register("segments", segments[["customer_id", "segment_id"]])

# Compare recorded balances with account overdraft limits
audit = con.execute("""
    SELECT
        s.segment_id,
        m.account_type,
        COUNT(DISTINCT m.account_id) AS accounts,
        COUNT(*) AS snapshot_count,

        SUM(CASE WHEN a.current_balance < 0
                 THEN 1 ELSE 0 END) AS negative_balance_snapshots,

        SUM(CASE WHEN a.current_balance < 0
                   AND m.overdraft_limit IS NOT NULL
                 THEN 1 ELSE 0 END) AS negative_with_known_limit,

        SUM(CASE WHEN m.overdraft_limit IS NULL
                 THEN 1 ELSE 0 END) AS snapshots_without_limit,

        SUM(CASE WHEN a.current_balance < -m.overdraft_limit
                   AND m.overdraft_limit IS NOT NULL
                 THEN 1 ELSE 0 END) AS below_overdraft_limit,

        MIN(a.current_balance) AS minimum_current_balance,
        MAX(m.overdraft_limit) AS maximum_overdraft_limit

    FROM segments s
    JOIN account_master m
      ON m.customer_id = s.customer_id
    JOIN account_monthly_snapshot a
      ON a.account_id = m.account_id
    GROUP BY s.segment_id, m.account_type
    ORDER BY s.segment_id, m.account_type
""").df()

print("\n========== OVERDRAFT CONSISTENCY BY CLUSTER ==========")
print(audit.round(2).to_string(index=False))

audit.to_csv(
    ROOT / "output" / "overdraft_consistency_by_cluster.csv",
    index=False
)

# Detailed account-level view for V3 Cluster 3
details = con.execute("""
    SELECT
        s.customer_id,
        m.account_id,
        m.account_type,
        m.overdraft_limit,
        COUNT(*) AS snapshot_count,

        SUM(CASE WHEN a.current_balance < 0
                 THEN 1 ELSE 0 END) AS negative_snapshots,

        SUM(CASE WHEN a.current_balance < -m.overdraft_limit
                   AND m.overdraft_limit IS NOT NULL
                 THEN 1 ELSE 0 END) AS below_limit_snapshots,

        MIN(a.current_balance) AS minimum_current_balance,
        AVG(a.current_balance) AS average_current_balance

    FROM segments s
    JOIN account_master m
      ON m.customer_id = s.customer_id
    JOIN account_monthly_snapshot a
      ON a.account_id = m.account_id
    WHERE s.segment_id = 3
    GROUP BY
        s.customer_id,
        m.account_id,
        m.account_type,
        m.overdraft_limit
    ORDER BY minimum_current_balance
""").df()

print("\n========== CLUSTER 3 ACCOUNTS ==========")
print(details.head(25).round(2).to_string(index=False))

details.to_csv(
    ROOT / "output" / "cluster3_overdraft_details.csv",
    index=False
)

con.close()
print("\nReports saved in output/")
