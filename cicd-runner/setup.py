from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="cicd-runner",
    version="0.1.0",
    author="CI/CD Runner Team",
    description="CI/CD runner for executing test suites via Platform API",
    packages=find_packages(),
    install_requires=requirements,
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "cicd-runner=src.cli.parser:main",
        ],
    },
)
