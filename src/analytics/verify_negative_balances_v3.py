
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

# 1. Check negative balances directly in the source snapshots
cluster_summary = con.execute("""
    SELECT
        s.segment_id,
        COUNT(DISTINCT s.customer_id) AS customers,
        COUNT(*) AS account_month_snapshots,
        SUM(CASE WHEN a.current_balance < 0 THEN 1 ELSE 0 END)
            AS negative_current_balance_snapshots,
        SUM(CASE WHEN a.average_monthly_balance < 0 THEN 1 ELSE 0 END)
            AS negative_average_balance_snapshots,
        AVG(a.current_balance) AS mean_current_balance,
        AVG(a.average_monthly_balance) AS mean_average_monthly_balance,
        MIN(a.current_balance) AS minimum_current_balance,
        MIN(a.average_monthly_balance) AS minimum_average_monthly_balance
    FROM segments s
    JOIN account_master m
      ON m.customer_id = s.customer_id
    JOIN account_monthly_snapshot a
      ON a.account_id = m.account_id
    GROUP BY s.segment_id
    ORDER BY s.segment_id
""").df()

print("\n========== SOURCE ACCOUNT BALANCE AUDIT ==========")
print(cluster_summary.round(2).to_string(index=False))

cluster_summary.to_csv(
    ROOT / "output" / "source_balance_audit_v3.csv",
    index=False,
)

# 2. Inspect customers in V3 Cluster 3
cluster3 = con.execute("""
    SELECT
        s.customer_id,
        COUNT(a.account_id) AS snapshot_count,
        SUM(CASE WHEN a.current_balance < 0 THEN 1 ELSE 0 END)
            AS negative_current_snapshots,
        SUM(CASE WHEN a.average_monthly_balance < 0 THEN 1 ELSE 0 END)
            AS negative_average_snapshots,
        AVG(a.current_balance) AS mean_current_balance,
        AVG(a.average_monthly_balance) AS mean_average_monthly_balance,
        MIN(a.current_balance) AS minimum_current_balance,
        MAX(a.current_balance) AS maximum_current_balance
    FROM segments s
    JOIN account_master m
      ON m.customer_id = s.customer_id
    JOIN account_monthly_snapshot a
      ON a.account_id = m.account_id
    WHERE s.segment_id = 3
    GROUP BY s.customer_id
    ORDER BY mean_current_balance ASC
""").df()

print("\n========== CLUSTER 3 SOURCE BALANCES ==========")
print("Customers with account snapshots:", len(cluster3))
print("\nMost negative source balance averages:")
print(cluster3.head(15).round(2).to_string(index=False))

cluster3.to_csv(
    ROOT / "output" / "cluster3_source_balance_details.csv",
    index=False,
)

con.close()
print("\nReports saved in output/")
