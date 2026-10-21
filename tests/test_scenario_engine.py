
import sys
import unittest
from pathlib import Path

# Add the project root to Python's import path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analytics.scenario_engine import calculate_scenario


class TestScenarioEngine(unittest.TestCase):

    def setUp(self):
        self.profile = {
            "estimated_monthly_income": 50000.0,
            "total_debits": 30000.0,
            "monthly_net_cash_flow": 10000.0,
            "monthly_emi_obligation": 10000.0,
        }

    def test_baseline_is_unchanged(self):
        result = calculate_scenario(self.profile)

        self.assertAlmostEqual(
            result["scenario_cash_flow"], 10000.0
        )

    def test_income_reduction(self):
        result = calculate_scenario(
            self.profile,
            income_change_pct=-10,
        )

        self.assertAlmostEqual(
            result["scenario_cash_flow"], 5000.0
        )

    def test_expense_increase(self):
        result = calculate_scenario(
            self.profile,
            expense_change_pct=10,
        )

        # Non-EMI expenses = 30,000 - 10,000 = 20,000
        # 10% increase = 2,000
        self.assertAlmostEqual(
            result["scenario_cash_flow"], 8000.0
        )

    def test_emi_increase(self):
        result = calculate_scenario(
            self.profile,
            emi_change_pct=10,
        )

        # 10% of 10,000 EMI = 1,000
        self.assertAlmostEqual(
            result["scenario_cash_flow"], 9000.0
        )

    def test_combined_stress(self):
        result = calculate_scenario(
            self.profile,
            income_change_pct=-10,
            expense_change_pct=10,
            emi_change_pct=10,
        )

        # 10,000 - 5,000 - 2,000 - 1,000 = 2,000
        self.assertAlmostEqual(
            result["scenario_cash_flow"], 2000.0
        )

    def test_zero_emi_has_no_emi_impact(self):
        profile = {
            **self.profile,
            "monthly_emi_obligation": 0.0,
        }

        result = calculate_scenario(
            profile,
            emi_change_pct=10,
        )

        self.assertAlmostEqual(
            result["emi_impact"], 0.0
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
