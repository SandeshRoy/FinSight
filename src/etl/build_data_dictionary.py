
from pathlib import Path
import duckdb
import csv

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"
OUTPUT_PATH = ROOT / "output" / "data_dictionary.csv"

# Initial descriptions for the core FinSight tables.
DESCRIPTIONS = {
    "customer_master": "Master details of bank customers.",
    "account_master": "Bank accounts linked to customers.",
    "transaction_fact": "Individual banking transactions.",
    "account_monthly_snapshot": "Monthly account balance and activity summaries.",
    "loan_master": "Loan details, terms and EMI information.",
    "loan_monthly_snapshot": "Monthly loan balances and repayment details.",
    "customer_monthly_activity": "Monthly customer transaction and engagement metrics.",
    "digital_engagement_monthly": "Monthly digital banking engagement.",
    "product_holdings_monthly": "Monthly customer product holdings.",
    "card_portfolio": "Customer card portfolio details.",
    "card_monthly_snapshot": "Monthly card activity summaries.",
    "churn_feature_snapshot": "Customer features and labels used in churn simulation.",
    "customer_churn_label": "Customer churn labels and associated dates.",
    "churn_simulation_state": "State maintained by the churn simulator.",
    "customer_complaints": "Customer complaint records.",
    "customer_feedback": "Customer feedback records.",
    "branch_master": "Bank branch reference information.",
}

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    con = duckdb.connect(str(DB_PATH), read_only=True)
    dictionary_rows = []

    try:
        tables = con.execute("SHOW TABLES").fetchall()

        for (table_name,) in tables:
            table_q = '"' + table_name.replace('"', '""') + '"'

            row_count = con.execute(
                f"SELECT COUNT(*) FROM {table_q}"
            ).fetchone()[0]

            columns = con.execute(
                f"DESCRIBE SELECT * FROM {table_q}"
            ).fetchall()

            for column in columns:
                column_name = column[0]
                data_type = column[1]
                nullable = column[2]

                column_q = '"' + column_name.replace('"', '""') + '"'

                null_count = con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {table_q}
                    WHERE {column_q} IS NULL
                    """
                ).fetchone()[0]

                dictionary_rows.append({
                    "table_name": table_name,
                    "table_description": DESCRIPTIONS.get(
                        table_name, "Description to be reviewed."
                    ),
                    "row_count": row_count,
                    "column_name": column_name,
                    "data_type": data_type,
                    "nullable_metadata": nullable,
                    "null_count": null_count,
                    "business_meaning": "",
                })

        fieldnames = [
            "table_name",
            "table_description",
            "row_count",
            "column_name",
            "data_type",
            "nullable_metadata",
            "null_count",
            "business_meaning",
        ]

        with OUTPUT_PATH.open(
            "w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(dictionary_rows)

        print("========== FINSIGHT DATA DICTIONARY ==========")
        print(f"Tables documented: {len(tables)}")
        print(f"Columns documented: {len(dictionary_rows)}")
        print(f"Saved to: {OUTPUT_PATH}")
        print("Fill in the business_meaning column for each field.")

    finally:
        con.close()


if __name__ == "__main__":
    main()
