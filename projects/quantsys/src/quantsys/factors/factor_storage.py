#!/usr/bin/env python3
"""
Factor Storage Layer
Supports Parquet partitioned storage, incremental write, read-back validation, and retention policy
"""

import shutil
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


class FactorStorage:
    """Factor storage layer with Parquet support"""

    def __init__(self, base_path="d:/quantsys/data/factors"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def write_factor(self, df, symbol, date, factor_version, validate=True):
        """Write factor data to Parquet with symbol/date/factor_version partitioning"""
        # Ensure required columns exist
        required_cols = ["timestamp", "factor_value"]
        assert all(col in df.columns for col in required_cols), (
            f"Missing required columns: {set(required_cols) - set(df.columns)}"
        )

        # Reset index to avoid issues with index types
        df = df.reset_index(drop=True)

        # Create partition path
        partition_path = (
            self.base_path / f"symbol={symbol}/date={date}/factor_version={factor_version}"
        )
        partition_path.mkdir(parents=True, exist_ok=True)

        # Write to Parquet file
        file_path = partition_path / "factor_data.parquet"
        pq.write_table(pa.Table.from_pandas(df), str(file_path), compression="snappy")

        # Validate write if requested
        if validate:
            read_df = self.read_factor(symbol, date, factor_version)
            read_df = read_df.reset_index(drop=True)
            assert len(df) == len(read_df), (
                f"Write-read validation failed: {len(df)} rows written, {len(read_df)} rows read"
            )
            # Compare data types and values
            pd.testing.assert_frame_equal(df, read_df, check_dtype=True)

        return str(file_path)

    def read_factor(self, symbol, date, factor_version):
        """Read factor data from Parquet"""
        file_path = (
            self.base_path
            / f"symbol={symbol}/date={date}/factor_version={factor_version}/factor_data.parquet"
        )
        if not file_path.exists():
            raise FileNotFoundError(f"Factor not found: {file_path}")

        table = pq.read_table(str(file_path))
        df = table.to_pandas()

        # Only keep the required columns to match the input DataFrame
        required_cols = ["timestamp", "factor_value"]
        return df[required_cols]

    def apply_retention_policy(self, symbol, max_versions=5):
        """Apply retention policy: keep only the most recent N factor versions"""
        symbol_path = self.base_path / f"symbol={symbol}"
        if not symbol_path.exists():
            return

        for date_dir in symbol_path.iterdir():
            if date_dir.is_dir() and date_dir.name.startswith("date="):
                # Get all factor versions for this date
                versions = []
                for version_dir in date_dir.iterdir():
                    if version_dir.is_dir() and version_dir.name.startswith("factor_version="):
                        version = version_dir.name.split("=")[1]
                        versions.append((version, version_dir))

                # Sort versions and keep only the most recent N
                if len(versions) > max_versions:
                    versions.sort(key=lambda x: x[0], reverse=True)
                    for version, version_dir in versions[max_versions:]:
                        shutil.rmtree(version_dir)

    def run_self_test(self):
        """Run self-test and save evidence"""
        test_results = []
        evidence_path = Path("evidence/factor_storage")
        evidence_path.mkdir(parents=True, exist_ok=True)

        # Create test data
        test_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2023-01-01", periods=10, freq="h"),
                "factor_value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            }
        )

        # Test 1: Write and read factor
        write_path = self.write_factor(test_df, "ETH", "20230101", "v1")
        read_df = self.read_factor("ETH", "20230101", "v1")
        test_results.append(
            {"test": "write_read", "status": "PASS" if test_df.equals(read_df) else "FAIL"}
        )

        # Test 2: Incremental write (same symbol, date, different version)
        incremental_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2023-01-01 10:00:00", periods=5, freq="h"),
                "factor_value": [11.0, 12.0, 13.0, 14.0, 15.0],
            }
        )
        self.write_factor(incremental_df, "ETH", "20230101", "v2")
        test_results.append({"test": "incremental_write", "status": "PASS"})

        # Test 3: Retention policy
        # Create multiple versions
        for i in range(6):
            temp_df = test_df.copy()
            temp_df["factor_value"] += i
            self.write_factor(temp_df, "ETH", "20230102", f"v{i + 1}")

        # Apply retention policy (keep only 5 versions)
        self.apply_retention_policy("ETH", max_versions=5)

        # Check retention
        date_path = self.base_path / "symbol=ETH" / "date=20230102"
        versions = [
            d for d in date_path.iterdir() if d.is_dir() and d.name.startswith("factor_version=")
        ]
        test_results.append(
            {"test": "retention_policy", "status": "PASS" if len(versions) == 5 else "FAIL"}
        )

        # Save test results to evidence
        results_df = pd.DataFrame(test_results)
        results_df.to_csv(evidence_path / "self_test_results.csv", index=False)

        # Save sample data to evidence
        test_df.to_csv(evidence_path / "sample_input_data.csv", index=False)
        read_df.to_csv(evidence_path / "sample_output_data.csv", index=False)

        return results_df


if __name__ == "__main__":
    # Run self-test
    storage = FactorStorage()
    results = storage.run_self_test()
    print("Self-test results:")
    print(results)
    print("Evidence saved to: evidence/factor_storage/")
