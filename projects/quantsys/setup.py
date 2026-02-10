"""Setup script for Quantsys quantitative trading system."""
from setuptools import setup, find_packages

setup(
    name="quantsys",
    version="0.1.0",
    description="Quantitative Trading System",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "pyyaml>=6.0",
        "requests>=2.28.0",
        "pandas>=1.5.0",
        "numpy>=1.23.0",
        "fastapi>=0.100.0",
        "uvicorn>=0.23.0",
        "psycopg2-binary>=2.9.0",
        "sqlalchemy>=2.0.0",
        "pydantic>=2.0.0",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "quantsys-backtest=quantsys.backtest.unified_backtest_entry:main",
        ],
    },
)
