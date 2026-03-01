from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="qa-studio-cli",
    version="0.1.0",
    author="QA Studio Team",
    description="QA Studio CLI — authenticate and manage QA Studio from the terminal",
    packages=find_packages(),
    install_requires=requirements,
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "qa-studio=qa_studio_cli.cli:cli",
        ],
    },
)
