"""Abstract base for objects that hold an Appium WebDriver instance."""

from abc import ABC, abstractmethod

from appium.webdriver.webdriver import WebDriver


class AppiumDriverManagerBase(ABC):
    """An object which maintains an Appium WebDriver instance."""

    @abstractmethod
    def get_driver(self) -> WebDriver:
        """Get the active Appium WebDriver instance."""

    @property
    @abstractmethod
    def driver(self) -> WebDriver:
        """The active Appium WebDriver managed by this instance."""
