
from pathlib import Path
import duckdb
import csv

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    results = []

    def record(check, count, details):
        results.append({
            "check": check,
            "issue_count": count,
            "details": details
        })
        status = "PASS" if count == 0 else "REVIEW"
        print(f"[{status}] {check}: {count:,} issue(s)")
        if details:
            print(f"       {details}")

    try:
        # 1. Candidate primary-key uniqueness and NULL checks
        primary_keys = {
            "customer_master": ["customer_id"],
            "account_master": ["account_id"],
            "transaction_fact": ["transaction_id"],
            "loan_master": ["loan_id"],
            "branch_master": ["branch_code"],
        }

        for table, keys in primary_keys.items():
            table_q = quote(table)
            key_expr = ", ".join(quote(k) for k in keys)

            null_condition = " OR ".join(
                f"{quote(k)} IS NULL" for k in keys
            )

            nulls = con.execute(
                f"SELECT COUNT(*) FROM {table_q} "
                f"WHERE {null_condition}"
            ).fetchone()[0]

            duplicates = con.execute(
                f"""
                SELECT COUNT(*) FROM (
                    SELECT {key_expr}
                    FROM {table_q}
                    GROUP BY {key_expr}
                    HAVING COUNT(*) > 1
                ) d
                """
            ).fetchone()[0]

            record(
                f"{table}: NULL key values",
                nulls,
                f"Candidate key: {', '.join(keys)}"
            )
            record(
                f"{table}: duplicate key groups",
                duplicates,
                f"Candidate key: {', '.join(keys)}"
            )

        # 2. Foreign-key relationship checks
        relationships = [
            ("account_master", "customer_id",
             "customer_master", "customer_id"),

            ("transaction_fact", "customer_id",
             "customer_master", "customer_id"),

            ("transaction_fact", "account_id",
             "account_master", "account_id"),

            ("account_monthly_snapshot", "account_id",
             "account_master", "account_id"),

            ("loan_master", "customer_id",
             "customer_master", "customer_id"),

            ("loan_monthly_snapshot", "loan_id",
             "loan_master", "loan_id"),

            ("customer_monthly_activity", "customer_id",
             "customer_master", "customer_id"),

            ("digital_engagement_monthly", "customer_id",
             "customer_master", "customer_id"),

            ("product_holdings_monthly", "customer_id",
             "customer_master", "customer_id"),

            ("churn_feature_snapshot", "customer_id",
             "customer_master", "customer_id"),

            ("customer_churn_label", "customer_id",
             "customer_master", "customer_id"),

            ("churn_simulation_state", "customer_id",
             "customer_master", "customer_id"),

            ("customer_complaints", "customer_id",
             "customer_master", "customer_id"),

            ("customer_feedback", "customer_id",
             "customer_master", "customer_id"),

            ("card_portfolio", "customer_id",
             "customer_master", "customer_id"),
        ]

        for child, child_col, parent, parent_col in relationships:
            child_q = quote(child)
            parent_q = quote(parent)
            child_c = quote(child_col)
            parent_c = quote(parent_col)

            child_columns = {
                row[0] for row in con.execute(
                    f"DESCRIBE {child_q}"
                ).fetchall()
            }
            parent_columns = {
                row[0] for row in con.execute(
                    f"DESCRIBE {parent_q}"
                ).fetchall()
            }

            if child_col not in child_columns:
                record(
                    f"{child}.{child_col} relationship",
                    1,
                    "Child column not found; verify schema"
                )
                continue

            if parent_col not in parent_columns:
                record(
                    f"{parent}.{parent_col} relationship",
                    1,
                    "Parent column not found; verify schema"
                )
                continue

            orphan_count = con.execute(
                f"""
                SELECT COUNT(*)
                FROM {child_q} c
                LEFT JOIN {parent_q} p
                  ON c.{child_c} = p.{parent_c}
                WHERE c.{child_c} IS NOT NULL
                  AND p.{parent_c} IS NULL
                """
            ).fetchone()[0]

            record(
                f"{child}.{child_col} -> {parent}.{parent_col}",
                orphan_count,
                "Non-NULL child references without a parent"
            )

        # 3. Check that each transaction's account belongs
        #    to the same customer recorded on the transaction.
        mismatch_count = con.execute(
            """
            SELECT COUNT(*)
            FROM transaction_fact t
            JOIN account_master a
              ON t.account_id = a.account_id
            WHERE t.customer_id <> a.customer_id
            """
        ).fetchone()[0]

        record(
            "Transaction/account customer consistency",
            mismatch_count,
            "Transactions whose customer differs from account owner"
        )

        # Save all checks
        report = OUTPUT_DIR / "relationship_validation.csv"
        with report.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["check", "issue_count", "details"]
            )
            writer.writeheader()
            writer.writerows(results)

        print(f"\nReport saved to: {report}")
        print(f"Checks performed: {len(results)}")
        print(
            "Checks needing review: "
            f"{sum(r['issue_count'] > 0 for r in results)}"
        )

    finally:
        con.close()


if __name__ == "__main__":
    main()
