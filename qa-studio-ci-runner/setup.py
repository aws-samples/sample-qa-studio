from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="qa-studio-ci-runner",
    version="0.1.0",
    author="QA Studio Team",
    description="QA Studio CI Runner for executing test suites via Platform API",
    packages=find_packages(),
    install_requires=requirements,
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "qa-studio-ci-runner=src.cli.parser:main",
        ],
    },
)
