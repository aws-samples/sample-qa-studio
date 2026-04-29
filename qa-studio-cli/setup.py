from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="qa-studio",
    version="0.2.0",
    author="QA Studio Team",
    description="QA Studio CLI — authenticate, manage, and execute QA Studio tests",
    packages=find_packages(),
    package_data={"": ["skills/**/*.md"]},
    include_package_data=True,
    install_requires=requirements,
    extras_require={
        "runner": [
            "nova-act~=3.3",
            "boto3>=1.34.0",
            "tenacity>=8.2.0",
            "playwright",
            "Appium-Python-Client>=4.0.0",
            "requests>=2.32.0",
        ],
    },
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "qa-studio=qa_studio_cli.cli:cli",
        ],
    },
)
