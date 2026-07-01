"""Interactive terminal UI for QA Studio (``qa-studio tui``).

All Textual-dependent code lives under this package. The root CLI
never imports ``qa_studio_cli.tui`` directly — the ``tui`` subcommand
does a lazy import inside the Click handler so users without the
``[tui]`` extra see a friendly install hint rather than a traceback.
"""
