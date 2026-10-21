
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"
INPUT_PATH = ROOT / "output" / "customer_monthly_profile.csv"
OUTPUT_PATH = ROOT / "output" / "customer_monthly_profile_v2.csv"

# Load the existing validated profile
profile = pd.read_csv(INPUT_PATH)
profile["snapshot_month"] = pd.to_datetime(
    profile["snapshot_month"]
).dt.to_period("M").dt.to_timestamp()

con = duckdb.connect(str(DB_PATH), read_only=True)

# Separate self-transfer flows from other recorded transactions
flows = con.execute("""
    SELECT
        customer_id,
        DATE_TRUNC('month', txn_timestamp)::DATE AS snapshot_month,

        SUM(CASE
            WHEN direction = 'Credit' THEN amount ELSE 0
        END) AS total_credits_check,

        SUM(CASE
            WHEN direction = 'Credit'
             AND LOWER(TRIM(COALESCE(counterparty_type, '')))
                 = 'self transfer'
            THEN amount ELSE 0
        END) AS self_transfer_credits,

        SUM(CASE
            WHEN direction = 'Credit'
             AND LOWER(TRIM(COALESCE(counterparty_type, '')))
                 <> 'self transfer'
            THEN amount ELSE 0
        END) AS non_self_transfer_credits,

        SUM(CASE
            WHEN direction = 'Debit' THEN amount ELSE 0
        END) AS total_debits_check,

        SUM(CASE
            WHEN direction = 'Debit'
             AND LOWER(TRIM(COALESCE(counterparty_type, '')))
                 = 'self transfer'
            THEN amount ELSE 0
        END) AS self_transfer_debits,

        SUM(CASE
            WHEN direction = 'Debit'
             AND LOWER(TRIM(COALESCE(counterparty_type, '')))
                 <> 'self transfer'
            THEN amount ELSE 0
        END) AS non_self_transfer_debits

    FROM transaction_fact
    GROUP BY customer_id, DATE_TRUNC('month', txn_timestamp)
""").df()

con.close()

flows["snapshot_month"] = pd.to_datetime(
    flows["snapshot_month"]
).dt.to_period("M").dt.to_timestamp()

# Keep every existing customer-month, including months with no transactions
profile_v2 = profile.merge(
    flows,
    on=["customer_id", "snapshot_month"],
    how="left",
    validate="one_to_one"
)

flow_columns = [
    "total_credits_check",
    "self_transfer_credits",
    "non_self_transfer_credits",
    "total_debits_check",
    "self_transfer_debits",
    "non_self_transfer_debits",
]

profile_v2[flow_columns] = profile_v2[flow_columns].fillna(0)

# Calculate cash flow after excluding transactions labelled as self-transfers
profile_v2["non_self_transfer_net_flow"] = (
    profile_v2["non_self_transfer_credits"]
    - profile_v2["non_self_transfer_debits"]
)

# Validate that the split reconciles with source transaction totals
credit_error = (
    profile_v2["total_credits_check"]
    - profile_v2["self_transfer_credits"]
    - profile_v2["non_self_transfer_credits"]
).abs()

debit_error = (
    profile_v2["total_debits_check"]
    - profile_v2["self_transfer_debits"]
    - profile_v2["non_self_transfer_debits"]
).abs()

print("\n========== TRANSFER-AWARE PROFILE VALIDATION ==========")
print("Profile rows:", len(profile_v2))
print("Duplicate customer-month keys:",
      int(profile_v2.duplicated(
          ["customer_id", "snapshot_month"]
      ).sum()))
print("Maximum credit reconciliation error:", round(credit_error.max(), 4))
print("Maximum debit reconciliation error:", round(debit_error.max(), 4))
print("Rows with no non-self-transfer credits:",
      int((profile_v2["non_self_transfer_credits"] == 0).sum()))

profile_v2.to_csv(OUTPUT_PATH, index=False)
print("\nSaved:", OUTPUT_PATH)
