"""
Authentication package for the Lookout Dashboard.
"""

from auth.manager import AuthManager
from auth.decorators import require_auth

__all__ = ['AuthManager', 'require_auth']
