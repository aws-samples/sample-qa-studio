"""Logging filters for thread-based isolation and nova-act suppression."""

import logging


class ThreadLogFilter(logging.Filter):
    """Only accept log records from a specific thread."""

    def __init__(self, thread_id: int):
        super().__init__()
        self.thread_id = thread_id

    def filter(self, record: logging.LogRecord) -> bool:
        return record.thread == self.thread_id


class NovaActLogFilter(logging.Filter):
    """Reject log records from the nova_act logger hierarchy."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith('nova_act')
