"""QA Studio CLI package.

Exports ``__version__`` — the single source of truth for the
installed CLI version, read from the package metadata at runtime so
it always matches what ``pip show qa-studio`` reports. Falls back to
``"dev"`` when the package is not installed (running out of a raw
source checkout, e.g. inside the test tree), so downstream code can
always render *something*.
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__: str = _pkg_version("qa-studio")
except PackageNotFoundError:  # unreleased / editable source checkout
    __version__ = "dev"

__all__ = ["__version__"]
