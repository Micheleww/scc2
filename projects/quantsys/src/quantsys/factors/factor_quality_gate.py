import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.stats import kstest, zscore


@dataclass
class QualityCheckResult:
    status: str  # PASS/FAIL
    reason: str
    recommended_action: str
    metric_value: float
    threshold: float


@dataclass
class QualityReport:
    factor_name: str
    timestamp: str
    overall_status: str  # PASS/FAIL
    missing_rate_check: QualityCheckResult
    constant_column_check: QualityCheckResult
    outlier_spike_check: QualityCheckResult
    distribution_drift_check: QualityCheckResult
    extreme_value_check: QualityCheckResult
    summary: str


class FactorQualityGate:
    def __init__(
        self,
        missing_rate_threshold: float = 0.1,  # 10% missing is allowed
        outlier_zscore_threshold: float = 3.0,  # 3 sigma
        ks_test_threshold: float = 0.05,  # p-value threshold
        extreme_value_percentile: float = 0.95,
    ):  # 95th percentile
        self.missing_rate_threshold = missing_rate_threshold
        self.outlier_zscore_threshold = outlier_zscore_threshold
        self.ks_test_threshold = ks_test_threshold
        self.extreme_value_percentile = extreme_value_percentile

    def check_missing_rate(self, factor: pd.Series) -> QualityCheckResult:
        missing_rate = factor.isna().mean()
        status = "PASS" if missing_rate <= self.missing_rate_threshold else "FAIL"
        reason = f"Missing rate: {missing_rate:.4f}, threshold: {self.missing_rate_threshold:.2f}"
        action = "No action needed" if status == "PASS" else "Investigate missing data reasons"
        return QualityCheckResult(status, reason, action, missing_rate, self.missing_rate_threshold)

    def check_constant_column(self, factor: pd.Series) -> QualityCheckResult:
        unique_values = factor.nunique()
        status = "PASS" if unique_values > 1 else "FAIL"
        reason = f"Unique values: {unique_values}, needs > 1"
        action = "No action needed" if status == "PASS" else "Remove constant factor"
        return QualityCheckResult(status, reason, action, unique_values, 1.0)

    def check_outlier_spikes(self, factor: pd.Series) -> QualityCheckResult:
        if len(factor) < 10:
            return QualityCheckResult(
                "PASS", "Insufficient data for spike detection", "No action needed", 0.0, 0.0
            )

        z_scores = zscore(factor.dropna())
        extreme_outliers = np.abs(z_scores) > self.outlier_zscore_threshold
        outlier_ratio = extreme_outliers.mean() if len(extreme_outliers) > 0 else 0

        status = "PASS" if outlier_ratio < 0.05 else "FAIL"  # 5% outliers allowed
        reason = f"Outlier ratio: {outlier_ratio:.4f}, threshold: 0.05"
        action = "No action needed" if status == "PASS" else "Smooth or remove outliers"
        return QualityCheckResult(status, reason, action, outlier_ratio, 0.05)

    def check_distribution_drift(self, factor: pd.Series) -> QualityCheckResult:
        if len(factor) < 100:
            return QualityCheckResult(
                "PASS",
                "Insufficient data for drift detection",
                "No action needed",
                0.0,
                self.ks_test_threshold,
            )

        # Split data into two halves for drift detection
        mid = len(factor) // 2
        data1 = factor[:mid].dropna()
        data2 = factor[mid:].dropna()

        if len(data1) < 10 or len(data2) < 10:
            return QualityCheckResult(
                "PASS",
                "Insufficient data after splitting",
                "No action needed",
                0.0,
                self.ks_test_threshold,
            )

        ks_stat, p_value = kstest(data1, data2)
        status = "PASS" if p_value > self.ks_test_threshold else "FAIL"
        reason = f"KS test p-value: {p_value:.4f}, threshold: {self.ks_test_threshold:.2f}"
        action = "No action needed" if status == "PASS" else "Investigate distribution change"
        return QualityCheckResult(status, reason, action, p_value, self.ks_test_threshold)

    def check_extreme_values(self, factor: pd.Series) -> QualityCheckResult:
        if len(factor) < 10:
            return QualityCheckResult(
                "PASS",
                "Insufficient data for extreme value detection",
                "No action needed",
                0.0,
                0.0,
            )

        factor_clean = factor.dropna()
        q1 = factor_clean.quantile(0.25)
        q3 = factor_clean.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        extreme_values = factor_clean[(factor_clean < lower_bound) | (factor_clean > upper_bound)]
        extreme_ratio = len(extreme_values) / len(factor_clean)

        status = "PASS" if extreme_ratio < 0.1 else "FAIL"  # 10% extreme values allowed
        reason = f"Extreme value ratio: {extreme_ratio:.4f}, threshold: 0.10"
        action = "No action needed" if status == "PASS" else "Investigate extreme values"
        return QualityCheckResult(status, reason, action, extreme_ratio, 0.1)

    def check_factor_quality(self, factor_name: str, factor: pd.Series) -> QualityReport:
        missing_result = self.check_missing_rate(factor)
        constant_result = self.check_constant_column(factor)
        outlier_result = self.check_outlier_spikes(factor)
        drift_result = self.check_distribution_drift(factor)
        extreme_result = self.check_extreme_values(factor)

        # Determine overall status
        all_results = [
            missing_result,
            constant_result,
            outlier_result,
            drift_result,
            extreme_result,
        ]
        overall_status = "PASS" if all(r.status == "PASS" for r in all_results) else "FAIL"

        # Create summary
        failed_checks = [
            f"{name[:-6]}"
            for name, r in zip(
                [
                    "missing_rate",
                    "constant_column",
                    "outlier_spike",
                    "distribution_drift",
                    "extreme_value",
                ],
                all_results,
            )
            if r.status == "FAIL"
        ]
        summary = f"Factor {factor_name}: {overall_status}. "
        if failed_checks:
            summary += f"Failed checks: {', '.join(failed_checks)}"
        else:
            summary += "All checks passed"

        report = QualityReport(
            factor_name=factor_name,
            timestamp=datetime.now().isoformat(),
            overall_status=overall_status,
            missing_rate_check=missing_result,
            constant_column_check=constant_result,
            outlier_spike_check=outlier_result,
            distribution_drift_check=drift_result,
            extreme_value_check=extreme_result,
            summary=summary,
        )

        # Store evidence
        self.store_evidence(report)

        return report

    def store_evidence(self, report: QualityReport) -> None:
        # Create reports directory if not exists
        os.makedirs("d:\\quantsys\\reports", exist_ok=True)

        # Convert dataclass to dict and save as JSON
        report_dict = asdict(report)
        filename = f"d:\\quantsys\\reports\\factor_quality_{report.factor_name}_{report.timestamp.replace(':', '-')}.json"
        with open(filename, "w") as f:
            json.dump(report_dict, f, indent=2, default=str)

    def should_block_downstream(self, report: QualityReport) -> bool:
        return report.overall_status == "FAIL"

    def run_self_test(self) -> dict:
        """Run self-test with mock factors"""
        results = {}

        # Test 1: Good factor
        good_factor = pd.Series(np.random.normal(0, 1, 1000))
        good_report = self.check_factor_quality("good_factor", good_factor)
        results["good_factor"] = good_report.overall_status

        # Test 2: Factor with high missing rate
        missing_factor = pd.Series(np.random.normal(0, 1, 1000))
        missing_factor.iloc[:300] = np.nan  # 30% missing
        missing_report = self.check_factor_quality("missing_factor", missing_factor)
        results["missing_factor"] = missing_report.overall_status

        # Test 3: Constant factor
        constant_factor = pd.Series([5.0] * 1000)
        constant_report = self.check_factor_quality("constant_factor", constant_factor)
        results["constant_factor"] = constant_report.overall_status

        # Test 4: Factor with outliers
        outlier_factor = pd.Series(np.random.normal(0, 1, 1000))
        outlier_factor.iloc[::10] = 10.0  # 10% outliers
        outlier_report = self.check_factor_quality("outlier_factor", outlier_factor)
        results["outlier_factor"] = outlier_report.overall_status

        # Test 5: Factor with distribution drift
        drift_factor1 = np.random.normal(0, 1, 500)
        drift_factor2 = np.random.normal(5, 1, 500)
        drift_factor = pd.Series(np.concatenate([drift_factor1, drift_factor2]))
        drift_report = self.check_factor_quality("drift_factor", drift_factor)
        results["drift_factor"] = drift_report.overall_status

        return results


# Example usage
if __name__ == "__main__":
    gate = FactorQualityGate()

    # Run self-test
    test_results = gate.run_self_test()
    print("Self-test results:")
    for factor, status in test_results.items():
        print(f"  {factor}: {status}")

    # Test with a sample factor
    sample_factor = pd.Series(np.random.normal(0, 1, 1000))
    report = gate.check_factor_quality("sample_factor", sample_factor)
    print("\nSample factor report:")
    print(f"  Overall status: {report.overall_status}")
    print(f"  Summary: {report.summary}")
    print(f"  Should block downstream: {gate.should_block_downstream(report)}")
