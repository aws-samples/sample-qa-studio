import json
import logging
from typing import Any, Dict
from utils import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ROUTE_MAP = {
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
    ('GET', '/dashboard/overview'): 'handlers.get_dashboard_overview',
}

_handler_cache: Dict[str, Any] = {}


def _get_handler(module_path: str):
    if module_path not in _handler_cache:
        module = __import__(module_path, fromlist=['handle'])
        _handler_cache[module_path] = module.handle
    return _handler_cache[module_path]


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    method = event.get('httpMethod', '')
    resource = event.get('resource', '')

    logger.info(f"Routing: {method} {resource}")

    route_key = (method, resource)
    module_path = ROUTE_MAP.get(route_key)

    if not module_path:
        return create_response(404, {'error': f'Route not found: {method} {resource}'})

    try:
        handle_fn = _get_handler(module_path)
        return handle_fn(event)
    except Exception as e:
        logger.error(f"Unhandled error in {module_path}: {e}", exc_info=True)
        return create_response(500, {'error': str(e), 'handler': module_path})
