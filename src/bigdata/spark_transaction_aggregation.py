
import os
import sys
from pathlib import Path

import duckdb
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "bank_data.db"
OUTPUT_DIR = ROOT / "output" / "bigdata"
OUTPUT_CSV = OUTPUT_DIR / "spark_customer_monthly_transactions.csv"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    # Use the active virtual environment's Python executable.
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

    spark = (
        SparkSession.builder
        .appName("FinSight-Transaction-Aggregation")
        .master("local[2]")
        .config("spark.pyspark.python", sys.executable)
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.execution.arrow.pyspark.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    try:
        print("Reading transactions from read-only DuckDB...")

        con = duckdb.connect(str(DB_PATH), read_only=True)

        try:
            # Use txn_timestamp, matching the original ETL's month rule.
            transactions = con.execute("""
                SELECT
                    customer_id,
                    txn_timestamp,
                    amount,
                    direction,
                    is_salary_credit,
                    is_fee,
                    is_reversal
                FROM transaction_fact
            """).fetchdf()
        finally:
            con.close()

        print(f"Source transactions loaded: {len(transactions):,}")

        sdf = spark.createDataFrame(transactions)

        # Match the original ETL's case-insensitive direction checks.
        sdf = (
            sdf.withColumn(
                "snapshot_month",
                F.date_trunc("month", F.col("txn_timestamp")).cast("date")
            )
            .withColumn(
                "direction_norm",
                F.lower(F.col("direction"))
            )
        )

        result = (
            sdf.groupBy("customer_id", "snapshot_month")
            .agg(
                F.sum(
                    F.when(
                        (F.col("direction_norm") == "credit")
                        & (F.col("is_salary_credit") == True),
                        F.col("amount")
                    ).otherwise(F.lit(0.0))
                ).alias("salary_income"),

                F.sum(
                    F.when(
                        (F.col("direction_norm") == "credit")
                        & (
                            F.coalesce(
                                F.col("is_salary_credit"), F.lit(False)
                            ) == False
                        ),
                        F.col("amount")
                    ).otherwise(F.lit(0.0))
                ).alias("other_credits"),

                F.sum(
                    F.when(
                        F.col("direction_norm") == "credit",
                        F.col("amount")
                    ).otherwise(F.lit(0.0))
                ).alias("total_credits"),

                F.sum(
                    F.when(
                        F.col("direction_norm") == "debit",
                        F.col("amount")
                    ).otherwise(F.lit(0.0))
                ).alias("total_debits"),

                F.count(F.lit(1)).alias("transaction_count"),

                F.sum(
                    F.when(
                        F.col("is_reversal") == True, 1
                    ).otherwise(0)
                ).alias("reversal_count"),

                F.sum(
                    F.when(
                        F.col("is_fee") == True,
                        F.col("amount")
                    ).otherwise(F.lit(0.0))
                ).alias("fee_amount")
            )
            .withColumn(
                "monthly_net_cash_flow",
                F.col("total_credits") - F.col("total_debits")
            )
            .orderBy("customer_id", "snapshot_month")
        )

        # Output is for validation; existing profile is not overwritten.
        pandas_result = result.toPandas()
        pandas_result.to_csv(OUTPUT_CSV, index=False)

        print(f"Customer-month transaction groups: {len(pandas_result):,}")
        print(f"Saved: {OUTPUT_CSV}")
        print("\nSample:")
        print(pandas_result.head(5).to_string(index=False))

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
