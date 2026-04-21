"""
Shared authentication decorators for route blueprints.
"""

from functools import wraps
from flask import jsonify, request, g, current_app


def require_auth(f):
    """Decorator to require authentication on a route"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_manager = current_app.extensions['auth_manager']
        config_class = current_app.extensions['config_class']

        if not getattr(config_class, 'AUTH_ENABLED', True):
            g.current_user = 'anonymous'
            return f(*args, **kwargs)

        auth = request.authorization
        if not auth or not auth_manager.check_auth(auth.username, auth.password):
            response = jsonify({'error': {'code': 'AUTH_REQUIRED', 'message': 'Authentication required'}})
            response.headers['WWW-Authenticate'] = 'Basic realm="Lookout Dashboard"'
            return response, 401
        g.current_user = auth.username
        return f(*args, **kwargs)
    return decorated
