"""Shared pytest configuration.

Provides a non-secret default SF_API_HOST so tools that resolve the API host
before validating their own inputs work without a local .env (CI, fresh
worktrees). Real values from .env or the environment take precedence.
"""

import os

os.environ.setdefault("SF_API_HOST", "api8preview.sapsf.com")
