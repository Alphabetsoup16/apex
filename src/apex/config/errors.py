"""Typed errors for stable classification (see ``top_level_errors``)."""


class ApexConfigurationError(RuntimeError):
    """Missing or invalid operator configuration (env, user config, optional deps)."""
