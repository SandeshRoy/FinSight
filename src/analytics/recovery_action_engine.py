"""
FinSight Financial Recovery Action Engine
Rule-based, input-driven guidance. Not a forecast or professional financial advice.
"""
import math


def _number(name, value):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a valid non-negative number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric.") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and non-negative.")
    return number


def generate_recovery_plan(
    monthly_income,
    monthly_expenses,
    monthly_emi,
    outstanding_loan,
    emergency_savings=0.0,
    essential_expenses=None,
):
    """Generate dynamic actions from the supplied monthly financial values.

    monthly_expenses must include EMI exactly once. Recommendations are
    deterministic rules; this function does not access live bank data.
    """
    income = _number("monthly_income", monthly_income)
    expenses = _number("monthly_expenses", monthly_expenses)
    emi = _number("monthly_emi", monthly_emi)
    loan = _number("outstanding_loan", outstanding_loan)
    savings = _number("emergency_savings", emergency_savings)

    if emi > expenses:
        raise ValueError(
            "Monthly EMI cannot exceed total expenses when expenses already include EMI."
        )

    if essential_expenses is None:
        essential = None
    else:
        essential = _number("essential_expenses", essential_expenses)
        if essential > expenses:
            raise ValueError("Essential expenses cannot exceed total monthly expenses.")

    cash_flow = income - expenses
    expense_ratio = expenses / income * 100 if income > 0 else None
    emi_ratio = emi / income * 100 if income > 0 else None
    savings_months = (
        savings / essential if essential is not None and essential > 0 else None
    )
    reserve_target = essential * 3 if essential is not None else None
    reserve_gap = max(reserve_target - savings, 0) if reserve_target is not None else None

    actions = []

    def add(priority, timeframe, category, issue, reason, action, target):
        actions.append({
            "priority": priority,
            "timeframe": timeframe,
            "category": category,
            "issue": issue,
            "reason": reason,
            "action": action,
            "target": target,
        })

    # Cash-flow rules: urgent deficits come first.
    if income == 0 and expenses > 0:
        add(
            "Critical", "Today", "Cash flow", "Expenses with no recorded income",
            f"Expenses are ₹{expenses:,.2f} per month while recorded income is ₹0.",
            "Verify the inputs and identify how essential bills are funded. If a payment may be missed, contact the provider or lender early.",
            "Confirm actual income, available funds, essential bills, and due dates.",
        )
    elif cash_flow < 0:
        gap = abs(cash_flow)
        add(
            "Critical", "Today", "Cash flow", "Monthly cash-flow deficit",
            f"Monthly expenses exceed income by ₹{gap:,.2f}.",
            "Prioritize essential needs, review optional spending and irregular bills, and contact creditors before missing a payment if needed.",
            f"First target: close the ₹{gap:,.2f} monthly gap safely; do not cut essential needs without a safe alternative.",
        )
        add(
            "High", "Within 7 days", "Budget", "Identify the cause of the deficit",
            "A recurring deficit can make bills and repayments harder to manage.",
            "Track spending for seven days and separate essential costs, debt payments, optional spending, and irregular bills.",
            "Create a monthly budget based on actual amounts and payment dates.",
        )
    elif cash_flow == 0:
        add(
            "High", "Within 7 days", "Cash flow", "No monthly surplus",
            "Income equals expenses, leaving no planned margin for unexpected costs.",
            "Review actual spending and possible income changes. Reduce only costs that can realistically be changed safely.",
            "Identify a sustainable route to a small positive monthly surplus.",
        )
    else:
        add(
            "Medium", "Within 7 days", "Cash flow", "Protect the monthly surplus",
            f"The entered values leave ₹{cash_flow:,.2f} monthly before unlisted or irregular costs.",
            "Check annual bills and irregular expenses before allocating the full surplus.",
            f"Choose a sustainable target after reviewing costs; current calculated surplus is ₹{cash_flow:,.2f}.",
        )

    # EMI ratio and expense share.
    if income == 0 and emi > 0:
        add(
            "High", "Today", "Debt affordability", "EMI with no recorded income",
            "An EMI is entered but monthly income is zero.",
            "Verify the figures. If repayment may be difficult, contact the lender before missing a payment.",
            "Confirm actual income and upcoming repayment obligations.",
        )
    elif emi_ratio is not None and emi_ratio >= 40:
        add(
            "High", "Within 7 days", "Debt affordability", "High EMI-to-income ratio",
            f"EMI is {emi_ratio:.1f}% of recorded monthly income.",
            "Review debt obligations and essential costs. Ask the lender about available options if payments are difficult; compare fees, total interest, and term.",
            "List loan balances, rates, EMIs, due dates, and fees.",
        )
    elif emi_ratio is not None and emi_ratio >= 30:
        add(
            "Medium", "Within 30 days", "Debt affordability", "Review EMI affordability",
            f"EMI is {emi_ratio:.1f}% of recorded monthly income.",
            "Check whether income remaining after EMI covers essential costs, other debts, and irregular expenses.",
            "Maintain a budget accounting for all obligations.",
        )

    if income > 0 and expense_ratio >= 80:
        add(
            "High" if cash_flow < 0 else "Medium", "Within 7 days", "Spending",
            "Expenses consume most of income",
            f"Total expenses are {expense_ratio:.1f}% of recorded income.",
            "Review expenses by category and identify safe, realistic reductions; not all expenses are discretionary.",
            "Set a reduction target only after reviewing essential needs and actual spending.",
        )

    # Emergency reserve uses essential expenses supplied by the user.
    if essential is None:
        add(
            "Medium", "Within 30 days", "Emergency savings", "Estimate a reserve target",
            "Essential expenses were not supplied, so savings coverage cannot be calculated.",
            "Estimate essential housing, food, utilities, necessary transport, and healthcare costs.",
            "Enter essential monthly expenses to calculate coverage and an illustrative target.",
        )
    elif essential == 0:
        add(
            "Medium", "Within 30 days", "Emergency savings", "Verify essential expenses",
            "Savings coverage cannot be meaningfully assessed against zero essential expenses.",
            "Check whether essential costs were omitted or entered incorrectly.",
            "Enter a realistic estimate of essential monthly expenses.",
        )
    elif reserve_gap > 0:
        if savings_months < 1:
            priority, timeframe = ("High" if cash_flow <= 0 else "Medium"), "Within 30 days"
        elif savings_months < 3:
            priority, timeframe = "Medium", "Within 30–90 days"
        else:
            priority, timeframe = "Low", "Within 90 days"
        target_text = (
            f"Illustrative target: ₹{reserve_target:,.2f} (three months of essential costs); "
            f"current gap: ₹{reserve_gap:,.2f}. "
        )
        if cash_flow > 0:
            target_text += (
                f"A six-month catch-up benchmark is ₹{reserve_gap / 6:,.2f} monthly, "
                f"but only save what remains affordable after irregular and essential costs. "
                f"Calculated cash-flow ceiling: ₹{cash_flow:,.2f}."
            )
        else:
            target_text += "Do not set a savings contribution that worsens a monthly deficit."
        add(
            priority, timeframe, "Emergency savings", "Build an emergency reserve",
            f"Current savings cover approximately {savings_months:.2f} months of entered essential costs.",
            "Build an accessible reserve gradually when the budget allows. Keep essential bills current and do not count unavailable credit as savings.",
            target_text,
        )
    else:
        add(
            "Low", "Within 90 days", "Emergency savings", "Review emergency reserve",
            "Entered savings meet or exceed the illustrative three-month target.",
            "Check whether the reserve remains suitable for household needs and income stability.",
            f"Review savings against the current target of ₹{reserve_target:,.2f} when costs change.",
        )

    # Debt inventory; repayment order is not prescribed without rates/terms.
    if loan > 0:
        add(
            "Medium", "Within 30 days", "Debt management", "Create a debt inventory",
            f"Outstanding loan balance entered: ₹{loan:,.2f}.",
            "List each loan's remaining balance, interest rate, EMI, due date, fees, and prepayment conditions.",
            "Compare repayment options using verified terms; the largest balance is not automatically the best first target.",
        )

    add(
        "Medium", "Within 30 days", "Progress review", "Review actual spending and income",
        "The plan may omit irregular costs or changed circumstances.",
        "Compare actual income and spending with the budget and update changed values.",
        "Recalculate monthly cash flow using current figures.",
    )
    add(
        "Low", "Within 90 days", "Progress review", "Measure progress",
        "A review shows whether the actions remain practical.",
        "Compare cash flow, savings, payment status, and verified debt balances with the starting position.",
        "Record changes and keep, adjust, or replace actions based on evidence.",
    )

    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    actions.sort(key=lambda item: (order[item["priority"]], item["timeframe"]))

    return {
        "monthly_income": income,
        "monthly_expenses": expenses,
        "monthly_emi": emi,
        "outstanding_loan": loan,
        "emergency_savings": savings,
        "monthly_cash_flow": cash_flow,
        "expense_to_income_percent": expense_ratio,
        "emi_to_income_percent": emi_ratio,
        "essential_expenses": essential,
        "essential_expense_coverage_months": savings_months,
        "emergency_reserve_target": reserve_target,
        "emergency_reserve_gap": reserve_gap,
        "actions": actions,
        "disclaimer": (
            "This is a rule-based educational plan generated from entered values. "
            "It does not connect to bank accounts, verify loan terms, assess every "
            "household circumstance, or select specific loans for repayment. "
            "Targets are illustrative. Verify your figures and seek qualified "
            "assistance if you are struggling to meet essential bills or repayments."
        ),
    }


if __name__ == "__main__":
    example = generate_recovery_plan(
        monthly_income=80000,
        monthly_expenses=90000,
        monthly_emi=15000,
        outstanding_loan=500000,
        emergency_savings=10000,
        essential_expenses=40000,
    )
    print("\n========== FINSIGHT RECOVERY PLAN ==========")
    print(f"Monthly cash flow: ₹{example['monthly_cash_flow']:,.2f}")
    print(f"EMI / income: {example['emi_to_income_percent']}")
    print(f"Actions generated: {len(example['actions'])}")
    for i, action in enumerate(example["actions"], start=1):
        print(f"\n{i}. [{action['priority']}] {action['issue']} — {action['timeframe']}")
        print(f"   Reason: {action['reason']}")
        print(f"   Action: {action['action']}")
        print(f"   Target: {action['target']}")
    print("\nDisclaimer:", example["disclaimer"])
