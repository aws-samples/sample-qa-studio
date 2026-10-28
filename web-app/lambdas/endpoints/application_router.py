import json
import logging
import re
from typing import Any, Dict, Optional, Tuple
from utils import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ROUTE_MAP = {
    # Application CRUD
    ('GET', '/applications'): 'handlers.list_applications',
    ('POST', '/applications'): 'handlers.create_application',
    ('GET', '/applications/{id}'): 'handlers.get_application',
    ('PATCH', '/applications/{id}'): 'handlers.update_application',
    ('DELETE', '/applications/{id}'): 'handlers.delete_application',
    ('POST', '/applications/{id}/usecases'): 'handlers.associate_usecases',
    ('DELETE', '/applications/{id}/usecases/{usecaseId}'): 'handlers.remove_usecase_association',
    ('GET', '/applications/{id}/metrics'): 'handlers.get_application_metrics',
    ('GET', '/applications/{id}/failures'): 'handlers.get_application_failures',
    ('GET', '/applications/{id}/flaky'): 'handlers.get_application_flaky',
    ('POST', '/applications/{id}/reassign'): 'handlers.reassign_application',
    # Dashboard
    ('GET', '/dashboard/overview'): 'handlers.get_dashboard_overview',
    # Team CRUD
    ('GET', '/teams'): 'handlers.list_teams',
    ('POST', '/teams'): 'handlers.create_team',
    ('GET', '/teams/{id}'): 'handlers.get_team',
    ('PATCH', '/teams/{id}'): 'handlers.update_team',
    ('DELETE', '/teams/{id}'): 'handlers.delete_team',
    # Team members
    ('GET', '/teams/{id}/members'): 'handlers.list_team_members',
    ('POST', '/teams/{id}/members'): 'handlers.add_team_member',
    ('PATCH', '/teams/{id}/members/{userId}'): 'handlers.set_member_role',
    ('DELETE', '/teams/{id}/members/{userId}'): 'handlers.remove_team_member',
    # Team applications
    ('GET', '/teams/{id}/applications'): 'handlers.list_team_applications',
    # Shared access
    ('GET', '/teams/{id}/shared-access'): 'handlers.list_shared_access',
    ('POST', '/teams/{id}/shared-access'): 'handlers.grant_shared_access',
    ('DELETE', '/teams/{id}/shared-access/{grantId}'): 'handlers.revoke_shared_access',
    # User management (new permissions-aware handlers)
    ('GET', '/users'): 'handlers.list_users',
    ('POST', '/users'): 'handlers.create_user',
    ('PATCH', '/users/{userId}'): 'handlers.update_user',
}

_handler_cache: Dict[str, Any] = {}
_route_patterns: Optional[list] = None


def _get_handler(module_path: str):
    if module_path not in _handler_cache:
        module = __import__(module_path, fromlist=['handle', 'handler'])
        if hasattr(module, 'handle'):
            _handler_cache[module_path] = module.handle
        elif hasattr(module, 'handler'):
            _handler_cache[module_path] = module.handler
        else:
            raise ImportError(f"Module {module_path} has neither 'handle' nor 'handler'")
    return _handler_cache[module_path]


def _compile_route_patterns():
    """Compile ROUTE_MAP templates into regex patterns with named capture groups."""
    global _route_patterns
    if _route_patterns is not None:
        return _route_patterns
    _route_patterns = []
    for (method, template), module_path in ROUTE_MAP.items():
        regex_str = re.sub(r'\{([^}]+)\}', r'(?P<\1>[^/]+)', template)
        regex = re.compile(f'^{regex_str}$')
        _route_patterns.append((method, regex, module_path))
    return _route_patterns


def _match_route(method: str, resource: str, path: str) -> Tuple[Optional[str], Dict[str, str]]:
    """Match request to handler. Returns (module_path, extracted_path_params)."""
    route_key = (method, resource)
    module_path = ROUTE_MAP.get(route_key)
    if module_path:
        return module_path, {}

    for route_method, regex, mod_path in _compile_route_patterns():
        if route_method == method:
            match = regex.match(path)
            if match:
                return mod_path, match.groupdict()
    return None, {}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    method = event.get('httpMethod', '')
    resource = event.get('resource', '')
    path = event.get('path', resource)

    logger.info(f"Routing: {method} {resource} (path: {path})")

    module_path, extracted_params = _match_route(method, resource, path)

    if not module_path:
        return create_response(404, {'error': f'Route not found: {method} {path}'})

    if extracted_params:
        params = event.get('pathParameters') or {}
        params.update(extracted_params)
        event['pathParameters'] = params

    try:
        handle_fn = _get_handler(module_path)
        return handle_fn(event)
    except Exception as e:
        logger.error(f"Unhandled error in {module_path}: {e}", exc_info=True)
        return create_response(500, {'error': str(e), 'handler': module_path})
