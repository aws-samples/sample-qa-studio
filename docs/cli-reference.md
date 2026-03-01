# CLI Reference

This guide provides detailed information about the QA Studio CI/CD Runner command-line interface, including all available options, usage patterns, exit codes, and output format.

## Basic Usage

The basic usage pattern for the CI/CD runner is:

```bash
qa-studio-ci-runner --suite-id <suite-id> [OPTIONS]
```

The runner requires authentication via environment variables (see [Configuration Reference](configuration.md)) and at minimum a test suite ID to execute.

## Quick Examples

### Simple Execution

Execute a test suite with default settings:

```bash
qa-studio-ci-runner --suite-id 01234567-89ab-cdef-0123-456789abcdef
```

### With Base URL Override

Override the base URL for all use cases in the suite:

```bash
qa-studio-ci-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --base-url https://staging.example.com
```

### With Variable Overrides

Override specific test variables:

```bash
qa-studio-ci-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --var username=testuser \
  --var password=testpass \
  --var environment=staging
```

### With Verbose Logging

Enable detailed debug logging:

```bash
qa-studio-ci-runner \
  --suite-id 01234567-89ab-cdef-0123-456789abcdef \
  --verbose
```
