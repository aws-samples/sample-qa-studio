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
            "mypy-boto3-devicefarm",
            "requests>=2.32.0",
            "jsonschema>=4.18.0",
        ],
        # Opt-in extra for --browser=agentcore.  The bedrock_agentcore
        # dependency is heavy and pins its own boto3 range, so we keep it
        # out of the base [runner] surface.  Implies [runner] because the
        # AgentCore path only makes sense when NovaAct is installed.
        "agentcore": [
            "bedrock_agentcore>=1.4.0",
        ],
        # Opt-in extra for the interactive terminal UI (``qa-studio tui``).
        # Textual is pre-1.0 and ships breaking minor-version bumps, so
        # we pin a narrow range deliberately.
        "tui": [
            "textual>=0.80,<0.90",
        ],
    },
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "qa-studio=qa_studio_cli.cli:cli",
        ],
    },
)
