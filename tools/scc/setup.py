"""Setup script for SCC tools."""
from setuptools import setup, find_packages

setup(
    name="scc-tools",
    version="0.1.0",
    description="SCC (Self-Contained Code) Tools",
    packages=find_packages(),
    install_requires=[
        "pyyaml",
        "requests",
    ],
    python_requires=">=3.10",
)
