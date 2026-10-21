
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


INPUT_PATH = "hdfs://namenode:9000/finsight/raw/transaction_fact.csv"
OUTPUT_PATH = (
    "hdfs://namenode:9000/finsight/processed/"
    "spark_customer_monthly_transactions_v1"
)


def main():
    spark = (
        SparkSession.builder
        .appName("FinSight-HDFS-Transaction-Aggregation")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    print("Reading transaction data from HDFS...")

    transactions = (
        spark.read
        .option("header", True)
        .option("inferSchema", True)
        .csv(INPUT_PATH)
    )

    required = {
        "customer_id",
        "txn_timestamp",
        "direction",
        "amount",
        "is_salary_credit",
        "is_fee",
        "is_reversal",
    }

    missing = required - set(transactions.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    print(f"Input columns: {len(transactions.columns)}")

    # Match the existing Python ETL's month grouping.
    tx = transactions.withColumn(
        "snapshot_month",
        F.to_date(F.date_trunc("month", F.col("txn_timestamp")))
    )

    direction = F.lower(F.col("direction"))
    is_salary = F.coalesce(F.col("is_salary_credit"), F.lit(False))
    is_fee = F.coalesce(F.col("is_fee"), F.lit(False))
    is_reversal = F.coalesce(F.col("is_reversal"), F.lit(False))
    amount = F.col("amount").cast("double")

    print("Aggregating by customer and month...")

    monthly = (
        tx.groupBy("customer_id", "snapshot_month")
        .agg(
            F.sum(
                F.when(
                    (direction == "credit") & is_salary, amount
                ).otherwise(0.0)
            ).alias("salary_income"),
            F.sum(
                F.when(
                    (direction == "credit") & (~is_salary), amount
                ).otherwise(0.0)
            ).alias("other_credits"),
            F.sum(
                F.when(direction == "credit", amount).otherwise(0.0)
            ).alias("total_credits"),
            F.sum(
                F.when(direction == "debit", amount).otherwise(0.0)
            ).alias("total_debits"),
            F.count("*").alias("transaction_count"),
            F.sum(
                F.when(is_reversal, 1).otherwise(0)
            ).alias("reversal_count"),
            F.sum(
                F.when(is_fee, amount).otherwise(0.0)
            ).alias("fee_amount"),
        )
        .withColumn(
            "monthly_net_cash_flow",
            F.col("total_credits") - F.col("total_debits")
        )
    )

    # Write to a new HDFS directory; do not overwrite the raw input.
    print(f"Writing aggregated results to {OUTPUT_PATH}...")

    (
        monthly.write
        .mode("errorifexists")
        .option("header", True)
        .csv(OUTPUT_PATH)
    )

    print("Aggregation completed successfully.")
    print(f"Output: {OUTPUT_PATH}")
    print(f"Customer-month groups: {monthly.count():,}")

    spark.stop()


if __name__ == "__main__":
    main()
