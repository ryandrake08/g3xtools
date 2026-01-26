#!/usr/bin/env python3
"""
Cross-Platform Cache Directory Utilities

Provides platform-specific cache directory paths with optional platformdirs integration.
Works on all platforms with or without platformdirs installed.

Usage:
    from cache import user_cache_path
    cache_dir = user_cache_path('g3xtools', 'g3xtools')

Dependencies:
    - platformdirs (optional): Preferred for cache directory paths
    - Falls back to built-in implementation if not available
"""

import pathlib
import sys
from typing import cast

# Public API
__all__ = [
    'user_cache_path',
]


def user_cache_path(appname: str, appauthor: str = '', ensure_exists: bool = True) -> pathlib.Path:
    """
    Get platform-specific user cache directory path.

    Attempts to use platformdirs library for proper platform-specific paths.
    Falls back to manual implementation if platformdirs is not installed.
    Creates the directory if it doesn't exist (unless ensure_exists=False).

    Args:
        appname: Application name for cache directory
        appauthor: Application author (used on Windows)
        ensure_exists: If True, create directory if it doesn't exist (default: True)

    Returns:
        Path to cache directory as pathlib.Path

    Examples:
        >>> cache_dir = user_cache_path('g3xtools', 'g3xtools')
        >>> # macOS: ~/Library/Caches/g3xtools
        >>> # Linux: ~/.cache/g3xtools
        >>> # Windows: ~\\AppData\\Local\\g3xtools\\g3xtools\\Cache
    """
    try:
        from platformdirs import user_cache_path as _platformdirs_cache

        return cast(pathlib.Path, _platformdirs_cache(appname, appauthor, ensure_exists=ensure_exists))
    except ImportError:
        # Fallback implementation for manual platform detection
        if sys.platform == 'darwin':
            cache_path = pathlib.Path.home() / 'Library' / 'Caches' / appname
        elif sys.platform == 'win32':
            if appauthor:
                cache_path = pathlib.Path.home() / 'AppData' / 'Local' / appauthor / appname / 'Cache'
            else:
                cache_path = pathlib.Path.home() / 'AppData' / 'Local' / appname / 'Cache'
        else:
            # Linux and other Unix-like systems
            cache_path = pathlib.Path.home() / '.cache' / appname

        if ensure_exists:
            cache_path.mkdir(parents=True, exist_ok=True)

        return cache_path
