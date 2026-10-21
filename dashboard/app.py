
from pathlib import Path
import sys

import pandas as pd
import streamlit as st


# --------------------------------------------------
# 1. PROJECT CONFIGURATION AND IMPORTS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_DIR = ROOT / "src" / "analytics"

if str(ANALYTICS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYTICS_DIR))

from new_customer_engine import compare_customer
from recovery_action_engine import generate_recovery_plan


# Descriptive names for the existing model clusters. These labels are for
# readability only; they do not indicate creditworthiness or financial health.
SEGMENT_LABELS = {
    0: "Higher-Income, Higher-EMI Group",
    1: "Low-Recorded-Credit, Low-Expense Group",
    2: "Moderate-Expense, Low-EMI Group",
    3: "High-EMI, High-Loan, Low-Recorded-Credit Group",
}


def get_segment_display_label(customer_result):
    """Return a readable label for the model's existing numeric cluster."""
    raw_label = customer_result.get("segment_label", "")
    raw_segment = customer_result.get("segment")

    # Prefer the explicit numeric segment field when the engine provides it.
    try:
        segment_id = int(raw_segment)
    except (TypeError, ValueError):
        segment_id = None

    # Otherwise, extract the ID from labels such as "Segment 2" or "2".
    if segment_id is None:
        label_text = str(raw_label).strip().lower()
        for candidate_id in SEGMENT_LABELS:
            if label_text in {str(candidate_id), f"segment {candidate_id}"}:
                segment_id = candidate_id
                break

    if segment_id in SEGMENT_LABELS:
        return SEGMENT_LABELS[segment_id]

    # Preserve any custom label provided by the engine if it is not one of
    # the numeric labels handled above.
    return str(raw_label) if raw_label else "Unlabelled customer group"


# --------------------------------------------------
# 2. PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="FinSight | Financial Intelligence",
    page_icon="💹",
    layout="wide",
)

st.title("💹 FinSight")
st.subheader("Financial Decision Support & Scenario Analysis")

st.caption(
    "Analyze a financial profile, compare it with historical "
    "synthetic customers, explore financial scenarios, and create "
    "a practical recovery action plan."
)

st.info(
    "FinSight is an educational decision-support tool. It does not "
    "provide a credit score, loan approval decision, loan-default "
    "prediction, or personalized financial advice."
)


# --------------------------------------------------
# 3. CUSTOMER FINANCIAL INPUT FORM
# --------------------------------------------------

st.header("1. Enter your financial information")

st.write(
    "Enter monthly amounts in Indian rupees. Monthly expenses should "
    "include current EMI exactly once."
)

with st.form("customer_financial_form"):
    col1, col2 = st.columns(2)

    with col1:
        monthly_income = st.number_input(
            "Monthly income (₹)",
            min_value=0.0,
            value=80000.0,
            step=1000.0,
            help=(
                "Enter total monthly income. The historical model uses "
                "non-self-transfer credits as an income proxy, which "
                "may not capture every type of income."
            ),
        )

        monthly_expenses = st.number_input(
            "Monthly expenses, including EMI (₹)",
            min_value=0.0,
            value=25000.0,
            step=1000.0,
            help=(
                "Enter total monthly expenses including EMI. Exclude "
                "transfers between your own accounts. Keep this "
                "definition consistent when reviewing comparisons."
            ),
        )

    with col2:
        monthly_emi = st.number_input(
            "Monthly EMI obligations (₹)",
            min_value=0.0,
            value=5000.0,
            step=500.0,
        )

        outstanding_loan = st.number_input(
            "Outstanding loan balance (₹)",
            min_value=0.0,
            value=200000.0,
            step=5000.0,
        )

    submitted = st.form_submit_button(
        "Analyze my financial profile",
        type="primary",
        use_container_width=True,
    )


# --------------------------------------------------
# 4. RUN CUSTOMER ANALYSIS
# --------------------------------------------------

if submitted:
    try:
        result = compare_customer(
            monthly_income=monthly_income,
            monthly_expenses=monthly_expenses,
            monthly_emi=monthly_emi,
            outstanding_loan=outstanding_loan,
        )

        st.session_state["finsight_result"] = result

        st.session_state["finsight_inputs"] = {
            "monthly_income": monthly_income,
            "monthly_expenses": monthly_expenses,
            "monthly_emi": monthly_emi,
            "outstanding_loan": outstanding_loan,
        }

        # Clear any old recovery plan when a new profile is submitted.
        st.session_state.pop("finsight_recovery", None)

    except (
        ValueError,
        FileNotFoundError,
        KeyError,
        OSError,
    ) as error:
        st.error(f"Could not analyze the profile: {error}")


result = st.session_state.get("finsight_result")
inputs = st.session_state.get("finsight_inputs")


# --------------------------------------------------
# 5. CUSTOMER ANALYSIS RESULTS
# --------------------------------------------------

if result and inputs:

    income = float(inputs["monthly_income"])
    expenses = float(inputs["monthly_expenses"])
    emi = float(inputs["monthly_emi"])
    loan = float(inputs["outstanding_loan"])

    baseline_cash_flow = income - expenses

    st.divider()
    st.header("2. Financial profile overview")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Assigned customer pattern",
            get_segment_display_label(result),
        )

    with col2:
        st.metric(
            "Historical peers in segment",
            f"{result['segment_customer_count']:,}",
        )

    with col3:
        st.metric(
            "Monthly cash flow",
            f"₹{baseline_cash_flow:,.2f}",
        )

    st.caption(
        f"Reference customers: {result['reference_customer_count']:,} | "
        f"Period: {result['reference_start_month']} to "
        f"{result['reference_end_month']}"
    )

    st.warning(
        "Segment IDs represent groups of similar historical financial "
        "patterns. They are not rankings of financial health or "
        "creditworthiness."
    )

    # --------------------------------------------------
    # 6. CUSTOMER VS HISTORICAL SEGMENT
    # --------------------------------------------------

    st.header("3. Customer vs. historical segment")

    comparison_df = pd.DataFrame(result["comparisons"])

    display_df = comparison_df[
        [
            "label",
            "customer_value",
            "segment_mean",
            "segment_median",
            "difference",
            "difference_percent",
            "comparison",
        ]
    ].copy()

    display_df.columns = [
        "Financial feature",
        "Your value (₹)",
        "Segment average (₹)",
        "Segment median (₹)",
        "Difference (₹)",
        "Difference (%)",
        "Comparison",
    ]

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
    )

    st.caption(
        "A higher or lower value is descriptive and is not automatically "
        "good or bad. Historical values come from synthetic data."
    )

    # --------------------------------------------------
    # 7. VISUAL COMPARISON
    # --------------------------------------------------

    st.header("4. Visual financial comparison")

    chart_df = comparison_df.set_index("label")[
        ["customer_value", "segment_mean"]
    ].rename(
        columns={
            "customer_value": "Your value",
            "segment_mean": "Segment average",
        }
    )

    st.bar_chart(
        chart_df,
        horizontal=True,
    )

    # --------------------------------------------------
    # 8. EXPLAINABLE INSIGHTS
    # --------------------------------------------------

    st.header("5. Explainable insights")

    insights = result.get("insights", [])

    if insights:
        for insight in insights:
            st.write(f"- {insight}")
    else:
        st.write("No additional insights were generated.")

    for warning in result.get("input_warnings", []):
        st.warning(warning)

    with st.expander("Understand each comparison"):
        for item in result["comparisons"]:
            st.markdown(f"**{item['label']}**")

            st.write(
                f"Your value is ₹{item['customer_value']:,.2f}. "
                f"The assigned segment average is "
                f"₹{item['segment_mean']:,.2f}, and its median is "
                f"₹{item['segment_median']:,.2f}."
            )

            if item["difference_percent"] is not None:
                st.write(
                    f"Difference from the segment average: "
                    f"{item['difference_percent']:+.2f}%."
                )
            else:
                st.write(
                    "A percentage difference is unavailable because "
                    "the segment average is zero."
                )

    # --------------------------------------------------
    # 9. BASIC MONTHLY CASH FLOW
    # --------------------------------------------------

    st.header("6. Basic monthly cash-flow view")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Income minus expenses",
            f"₹{baseline_cash_flow:,.2f}",
        )

    with col2:
        if income > 0:
            emi_ratio = emi / income * 100

            st.metric(
                "EMI / monthly income",
                f"{emi_ratio:.2f}%",
            )
        else:
            st.metric(
                "EMI / monthly income",
                "N/A",
            )

    if baseline_cash_flow < 0:
        st.error(
            "Your entered expenses exceed your entered income. "
            "Review your budget and prioritize essential needs."
        )
    elif baseline_cash_flow == 0:
        st.warning(
            "Your entered income equals expenses, leaving no "
            "planned monthly surplus."
        )
    else:
        st.caption(
            "Your entered income exceeds your entered expenses. "
            "Check whether irregular bills and essential costs "
            "are included before allocating the remaining amount."
        )

    if emi > expenses:
        st.warning(
            "Your EMI is greater than total entered expenses. "
            "Verify your inputs before interpreting the results."
        )

    st.caption(
        "EMI is displayed separately as a ratio. Because expenses "
        "should include EMI, it is not subtracted twice."
    )

    with st.expander("Review submitted financial information"):
        input_df = pd.DataFrame(
            [
                {
                    "Financial input": "Monthly income",
                    "Amount (₹)": income,
                },
                {
                    "Financial input": "Monthly expenses",
                    "Amount (₹)": expenses,
                },
                {
                    "Financial input": "Monthly EMI",
                    "Amount (₹)": emi,
                },
                {
                    "Financial input": "Outstanding loan",
                    "Amount (₹)": loan,
                },
            ]
        )

        st.dataframe(
            input_df,
            hide_index=True,
            use_container_width=True,
        )

    # --------------------------------------------------
    # 10. INTERACTIVE SCENARIO SIMULATOR
    # --------------------------------------------------

    st.divider()
    st.header("7. Financial scenario simulator")

    st.write(
        "Explore how hypothetical changes in income, expenses and EMI "
        "affect your estimated monthly cash flow."
    )

    st.info(
        "These are what-if calculations based on your entered values, "
        "not predictions of future financial outcomes."
    )

    slider_col1, slider_col2, slider_col3 = st.columns(3)

    with slider_col1:
        income_drop_pct = st.slider(
            "Income reduction (%)",
            min_value=0,
            max_value=50,
            value=10,
            step=5,
            key="scenario_income_drop",
        )

    with slider_col2:
        expense_increase_pct = st.slider(
            "Expense increase (%)",
            min_value=0,
            max_value=50,
            value=10,
            step=5,
            key="scenario_expense_increase",
        )

    with slider_col3:
        emi_increase_pct = st.slider(
            "EMI increase (%)",
            min_value=0,
            max_value=50,
            value=10,
            step=5,
            key="scenario_emi_increase",
        )

    # Assumption: entered expenses already include current EMI.
    non_emi_expenses = max(expenses - emi, 0.0)

    # Scenario A: current baseline.
    baseline = income - expenses

    # Scenario B: income decreases; expenses remain unchanged.
    income_down = (
        income * (1 - income_drop_pct / 100)
        - expenses
    )

    # Scenario C: total expenses increase.
    expenses_up = (
        income
        - expenses * (1 + expense_increase_pct / 100)
    )

    # Scenario D: only the additional EMI is added to expenses.
    emi_up = (
        income
        - expenses
        - emi * emi_increase_pct / 100
    )

    # Scenario E: combine income reduction, non-EMI expense increase,
    # and EMI increase. Count each expense component only once.
    stressed_income = income * (
        1 - income_drop_pct / 100
    )

    stressed_non_emi_expenses = non_emi_expenses * (
        1 + expense_increase_pct / 100
    )

    stressed_emi = emi * (
        1 + emi_increase_pct / 100
    )

    combined = (
        stressed_income
        - stressed_non_emi_expenses
        - stressed_emi
    )

    scenarios_df = pd.DataFrame(
        [
            {
                "Scenario": "Baseline",
                "Estimated income (₹)": income,
                "Estimated expenses (₹)": expenses,
                "Estimated cash flow (₹)": baseline,
            },
            {
                "Scenario": f"Income down {income_drop_pct}%",
                "Estimated income (₹)": stressed_income,
                "Estimated expenses (₹)": expenses,
                "Estimated cash flow (₹)": income_down,
            },
            {
                "Scenario": f"Expenses up {expense_increase_pct}%",
                "Estimated income (₹)": income,
                "Estimated expenses (₹)": (
                    expenses * (1 + expense_increase_pct / 100)
                ),
                "Estimated cash flow (₹)": expenses_up,
            },
            {
                "Scenario": f"EMI up {emi_increase_pct}%",
                "Estimated income (₹)": income,
                "Estimated expenses (₹)": (
                    expenses + emi * emi_increase_pct / 100
                ),
                "Estimated cash flow (₹)": emi_up,
            },
            {
                "Scenario": "Combined stress",
                "Estimated income (₹)": stressed_income,
                "Estimated expenses (₹)": (
                    stressed_non_emi_expenses + stressed_emi
                ),
                "Estimated cash flow (₹)": combined,
            },
        ]
    )

    scenarios_df["Change vs baseline (₹)"] = (
        scenarios_df["Estimated cash flow (₹)"] - baseline
    )

    st.subheader("Scenario summary")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Baseline cash flow",
            f"₹{baseline:,.2f}",
        )

    with col2:
        st.metric(
            "Combined stress cash flow",
            f"₹{combined:,.2f}",
            delta=f"₹{combined - baseline:,.2f}",
        )

    with col3:
        if combined < 0:
            combined_status = "Negative"
        elif combined == 0:
            combined_status = "Break-even"
        else:
            combined_status = "Positive"

        st.metric(
            "Combined scenario",
            combined_status,
        )

    st.subheader("Cash flow under each scenario")

    scenario_chart_df = scenarios_df.set_index("Scenario")[
        ["Estimated cash flow (₹)"]
    ]

    st.bar_chart(
        scenario_chart_df,
        horizontal=True,
    )

    st.subheader("Detailed scenario calculations")

    st.dataframe(
        scenarios_df,
        hide_index=True,
        use_container_width=True,
    )

    change = combined - baseline

    st.subheader("Combined scenario explanation")
    st.write(
        "This stress test combines three hypothetical changes: your income "
        "falls, your non-EMI expenses rise, and your EMI obligation rises. "
        "The calculations use the percentages selected above."
    )

    explanation_col1, explanation_col2 = st.columns(2)

    with explanation_col1:
        st.markdown("**Before stress (baseline)**")
        st.write(f"- Monthly income: ₹{income:,.2f}")
        st.write(f"- Non-EMI expenses: ₹{non_emi_expenses:,.2f}")
        st.write(f"- EMI: ₹{emi:,.2f}")
        st.write(f"- Total expenses: ₹{expenses:,.2f}")
        st.write(f"- Cash flow: ₹{baseline:,.2f}")

    with explanation_col2:
        st.markdown("**After all three changes**")
        st.write(f"- Income after {income_drop_pct}% reduction: ₹{stressed_income:,.2f}")
        st.write(
            f"- Non-EMI expenses after {expense_increase_pct}% increase: "
            f"₹{stressed_non_emi_expenses:,.2f}"
        )
        st.write(f"- EMI after {emi_increase_pct}% increase: ₹{stressed_emi:,.2f}")
        st.write(f"- Total stressed expenses: ₹{stressed_non_emi_expenses + stressed_emi:,.2f}")
        st.write(f"- Cash flow after stress: ₹{combined:,.2f}")

    st.metric(
        "Monthly cash-flow change",
        f"₹{change:,.2f}",
        delta=f"₹{change:,.2f}",
    )

    if combined < 0 <= baseline:
        st.error(
            "The combined scenario turns your baseline cash flow from "
            "zero or positive to a monthly deficit. Under these assumptions, "
            "total expenses would exceed income."
        )
        st.markdown("""**Suggested next steps**
- Review non-essential spending while protecting essential needs.
- Check upcoming EMI obligations and contact your lender early if repayment may become difficult.
- Avoid relying on additional borrowing to cover recurring expenses.
- Build emergency savings when your budget allows.""")
    elif combined < 0:
        st.error(
            "The combined scenario shows a monthly deficit, and your baseline "
            "is already negative. Focus first on understanding the existing "
            "shortfall and protecting essential expenses."
        )
        st.markdown("""**Suggested next steps**
- List essential and non-essential expenses separately.
- Review whether any spending can be reduced without compromising essential needs.
- Contact lenders early if you expect difficulty meeting repayments.""")
    elif combined == 0:
        st.warning(
            "Your income exactly covers expenses in the combined scenario. "
            "There is no monthly surplus for unexpected costs or savings."
        )
        st.markdown("""**Suggested next steps**
- Identify realistic expense reductions.
- Keep a buffer for irregular bills where possible.
- Recheck the budget when income or costs change.""")
    else:
        st.success(
            f"Your estimated monthly cash flow remains positive at ₹{combined:,.2f} "
            "under the selected combined-stress assumptions. This is a scenario "
            "result, not a guarantee of future surplus."
        )
        st.markdown("""**Suggested next steps**
- Check whether irregular bills and essential expenses are included.
- Consider building an emergency reserve before making new commitments.
- Re-run the scenario if your assumptions change.""")

    st.caption(
        "Assumption: entered monthly expenses already include EMI. For the "
        "combined scenario, non-EMI expenses are estimated as max(total expenses "
        "minus EMI, 0), then stressed separately from EMI to avoid double-counting. "
        "If EMI is greater than total entered expenses, verify your inputs. "
        "This is a hypothetical calculation using synthetic assumptions, not a "
        "forecast or personalized financial advice."
    )

    st.download_button(
        "Download scenario results (CSV)",
        data=scenarios_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="finsight_scenario_results.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # --------------------------------------------------
    # 11. FINANCIAL RECOVERY ACTION PLAN
    # --------------------------------------------------

    st.divider()
    st.header("8. Financial recovery action plan")

    st.write(
        "Generate prioritized actions based on your entered financial "
        "figures. Add emergency savings and essential monthly expenses "
        "to make the plan more informative."
    )

    with st.form("recovery_plan_form"):
        savings_input = st.number_input(
            "Current emergency savings (₹)",
            min_value=0.0,
            value=0.0,
            step=1000.0,
            help=(
                "Money readily available for unexpected essential "
                "expenses. Do not include unavailable credit limits."
            ),
        )

        essential_input = st.number_input(
            "Essential monthly expenses (₹)",
            min_value=0.0,
            value=min(15000.0, expenses),
            step=1000.0,
            help=(
                "Include essential housing, food, utilities, transport "
                "and healthcare. This amount cannot exceed total expenses."
            ),
        )

        generate_plan = st.form_submit_button(
            "Generate my recovery plan",
            type="primary",
            use_container_width=True,
        )

    if generate_plan:
        try:
            recovery = generate_recovery_plan(
                monthly_income=income,
                monthly_expenses=expenses,
                monthly_emi=emi,
                outstanding_loan=loan,
                emergency_savings=savings_input,
                essential_expenses=essential_input,
            )

            st.session_state["finsight_recovery"] = recovery

        except (ValueError, TypeError) as error:
            st.error(
                f"Could not generate the recovery plan: {error}"
            )

    recovery = st.session_state.get("finsight_recovery")

    if recovery:
        st.subheader("Your financial position")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Monthly cash flow",
                f"₹{recovery['monthly_cash_flow']:,.2f}",
            )

        with col2:
            ratio = recovery["emi_to_income_percent"]

            st.metric(
                "EMI / income",
                f"{ratio:.1f}%" if ratio is not None else "N/A",
            )

        with col3:
            coverage = recovery["essential_expense_coverage_months"]

            st.metric(
                "Emergency savings coverage",
                f"{coverage:.1f} months"
                if coverage is not None
                else "N/A",
            )

        if recovery["monthly_cash_flow"] < 0:
            st.error(
                "Priority: address the monthly deficit and protect "
                "essential needs before setting aggressive savings "
                "or extra debt-repayment targets."
            )
        elif recovery["monthly_cash_flow"] == 0:
            st.warning(
                "Your budget has no planned monthly surplus. "
                "Start by identifying a realistic route to positive "
                "cash flow."
            )
        else:
            st.success(
                "Your entered budget has positive cash flow. "
                "Check irregular expenses before allocating the surplus."
            )

        st.subheader("Recommended actions")

        for number, action in enumerate(
            recovery["actions"],
            start=1,
        ):
            with st.expander(
                f"{number}. {action['issue']} — {action['timeframe']}",
                expanded=(number == 1),
            ):
                st.write(f"**Priority:** {action['priority']}")
                st.write(f"**Action:** {action['action']}")
                st.write(f"**Target:** {action['target']}")

        recovery_df = pd.DataFrame(recovery["actions"])

        st.download_button(
            "Download financial recovery plan (CSV)",
            data=recovery_df.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="finsight_recovery_action_plan.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.warning(recovery["disclaimer"])

    # --------------------------------------------------
    # 12. DOWNLOAD CUSTOMER COMPARISON REPORT
    # --------------------------------------------------

    st.divider()
    st.header("9. Download customer comparison report")

    st.download_button(
        "Download comparison report (CSV)",
        data=comparison_df.to_csv(
            index=False
        ).encode("utf-8-sig"),
        file_name="finsight_customer_comparison.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # --------------------------------------------------
    # 13. DISCLAIMER
    # --------------------------------------------------

    st.divider()
    st.subheader("Important limitations")

    st.warning(result["disclaimer"])

    st.caption(
        "The historical reference dataset is synthetic. Financial "
        "classifications may not reflect real household income or "
        "expenses perfectly. Scenario results are hypothetical. "
        "Recovery actions are general rule-based guidance; verify "
        "your circumstances and loan terms before acting."
    )

else:
    # --------------------------------------------------
    # INITIAL DASHBOARD STATE
    # --------------------------------------------------

    st.divider()
    st.header("How FinSight works")

    st.markdown(
        """
        1. **Enter financial information:** Income, expenses, EMI
           and outstanding loan balance.
        2. **Compare historical patterns:** Find a similar group in
           the synthetic customer dataset.
        3. **Understand the results:** Review averages, medians,
           charts and explainable insights.
        4. **Simulate scenarios:** Explore changes to income,
           expenses and EMI.
        5. **Create an action plan:** Receive prioritized,
           rule-based financial recovery steps.
        6. **Download reports:** Export comparison, scenario
           and recovery-plan results as CSV files.
        """
    )

    st.caption(
        "Submit the form above to display your financial analysis, "
        "scenario simulator and recovery action plan."
    )
