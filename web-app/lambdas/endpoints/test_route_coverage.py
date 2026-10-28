"""
Route coverage guard (H-2): every handler routed through API Gateway must
enforce resource ownership with @require_resource_access, unless it is on
the explicit allowlist below of routes that are global, admin-only, team
management (require_team_role) or filtered lists.

Routes are read from web-app/lib/api-stack.ts (addMethod calls), the Lambda
behind each route from the stacks' createPythonLambda({path, handler}), and
the application router's ROUTE_MAP for /applications, /teams, /users and
/dashboard. A new route whose handler skips the check fails this test.
"""
import os
import re
from pathlib import Path

ENDPOINTS_DIR = Path(__file__).resolve().parent
LIB_DIR = ENDPOINTS_DIR.parent.parent / 'lib'
ROUTER_MODULE = 'application_router'

# module -> (why it doesn't use require_resource_access, marker its source must contain)
ALLOWLIST = {
    # Filtered lists: return only what the caller may see (per item).
    'list_usecases': ('filtered list + per-test-case override batch', 'can_view_testcase_batch'),
    'list_test_suites': ('filtered list by owner team / shares', 'require_scopes'),
    'handlers.list_applications': ('filtered list (filter_visible_apps)', 'filter_visible_apps'),
    'handlers.get_dashboard_overview': ('filtered list of visible apps', 'require_scopes'),
    'list_oauth_clients': ('admins all; others only clients of their editor+ teams', 'require_scopes'),
    # Global catalogues: no team-owned resource behind them.
    'list_models': ('global Bedrock / Nova model catalogue', 'require_scopes'),
    'list_device_farm_devices': ('global Device Farm catalogue', 'require_scopes'),
    'list_scopes': ('global OAuth scope list', 'require_scopes'),
    'generate_usecase': ('Bedrock generation, no stored resource; manifest key via authorize_session',
                         'authorize_session'),
    # Templates stay studio-global (decision 4); apply_template is checked.
    'list_templates': ('studio-global templates (decision 4)', 'require_scopes'),
    'create_template': ('studio-global templates (decision 4)', 'require_scopes'),
    'get_template': ('studio-global templates (decision 4)', 'require_scopes'),
    'update_template': ('studio-global templates (decision 4)', 'require_scopes'),
    'delete_template': ('studio-global templates (decision 4)', 'require_scopes'),
    'list_template_steps': ('studio-global templates (decision 4)', 'require_scopes'),
    'create_template_step': ('studio-global templates (decision 4)', 'require_scopes'),
    'reorder_template_steps': ('studio-global templates (decision 4)', 'require_scopes'),
    'update_template_step': ('studio-global templates (decision 4)', 'require_scopes'),
    'delete_template_step': ('studio-global templates (decision 4)', 'require_scopes'),
    'get_template_variables': ('studio-global templates (decision 4)', 'require_scopes'),
    'create_template_variables': ('studio-global templates (decision 4)', 'require_scopes'),
    # OAuth clients: bound to a team, checked against that team.
    'create_oauth_client': ('editor+ of the body teamId', 'require_team_role'),
    'delete_oauth_client': ('creator, team lead of the client team, or admin', 'require_oauth_client_manager'),
    'rotate_client_secret': ('creator, team lead of the client team, or admin', 'require_oauth_client_manager'),
    # Team management: checked against the path / body team.
    'handlers.create_application': ('team lead of the body teamId (H-3)', 'require_team_role'),
    'handlers.list_teams': ('admins all; team leads a minimal list', 'has_team_role'),
    'handlers.get_team': ('team membership', 'require_team_role'),
    'handlers.list_team_members': ('team lead of the path team', 'require_team_role'),
    'handlers.list_team_applications': ('team membership', 'require_team_role'),
    'handlers.add_team_member': ('team lead of the path team (C-1)', 'require_team_role'),
    'handlers.set_member_role': ('team lead of the path team (C-1)', 'require_team_role'),
    'handlers.remove_team_member': ('team lead of the path team', 'require_team_role'),
    'handlers.list_shared_access': ('team lead of the path team', 'require_team_role'),
    'handlers.grant_shared_access': ('team lead of the path team', 'require_team_role'),
    'handlers.revoke_shared_access': ('team lead of the path team', 'require_team_role'),
    # Studio admin only.
    'handlers.create_team': ('admin only', "'api/admin'"),
    'handlers.update_team': ('admin only', "'api/admin'"),
    'handlers.delete_team': ('admin only', "'api/admin'"),
    'handlers.reassign_application': ('admin only', "'api/admin'"),
    'handlers.list_users': ('admin only', "'api/admin'"),
    'handlers.create_user': ('admin only', "'api/admin'"),
    'handlers.update_user': ('admin only', "'api/admin'"),
    'get_user': ('admin only', "'api/admin'"),
    'delete_user': ('admin only', "'api/admin'"),
    'update_user_groups': ('admin only', "'api/admin'"),
}

_LAMBDA_DEF = re.compile(r"this\.(\w+)\s*=\s*this\.createPythonLambda\(\{(.*?)\}\)", re.S)
_ADD_METHOD = re.compile(r"this\.addMethod\((\w+), HttpMethod\.(\w+), (?:l|props)\.(\w+)")


def _lambda_modules() -> dict:
    """Lambda property name -> handler module, from every stack in lib/."""
    modules = {}
    for stack in LIB_DIR.glob('*.ts'):
        for name, body in _LAMBDA_DEF.findall(stack.read_text()):
            handler = re.search(r"handler:\s*'([^']+)'", body)
            path = re.search(r"path:\s*'([^']+)'", body)
            entry = handler.group(1) if handler else f"{path.group(1)}.handler"
            modules[name] = entry.rsplit('.', 1)[0]
    return modules


def api_routes() -> list:
    """[(http method, lambda property, handler module)] for every addMethod in api-stack.ts."""
    lambdas = _lambda_modules()
    source = (LIB_DIR / 'api-stack.ts').read_text()
    return [(method, prop, lambdas.get(prop)) for _res, method, prop in _ADD_METHOD.findall(source)]


def router_modules() -> set:
    from application_router import ROUTE_MAP
    return set(ROUTE_MAP.values())


def routed_handler_modules() -> set:
    """Every handler module reachable through API Gateway (router expanded)."""
    modules = {module for _m, _p, module in api_routes() if module and module != ROUTER_MODULE}
    return modules | router_modules()


def _source(module: str) -> str:
    return (ENDPOINTS_DIR / f"{module.replace('.', os.sep)}.py").read_text()


def test_api_stack_parsed():
    routes = api_routes()
    assert len(routes) >= 100, 'api-stack.ts parsing found too few routes'
    source = (LIB_DIR / 'api-stack.ts').read_text()
    assert len(routes) == source.count('this.addMethod('), 'an addMethod call did not match the parser'


def test_every_route_has_a_handler_module():
    unknown = [(m, p) for m, p, module in api_routes() if module is None]
    assert not unknown, f'routes whose Lambda has no createPythonLambda path: {unknown}'
    missing = [m for m in routed_handler_modules() if not (ENDPOINTS_DIR / f"{m.replace('.', os.sep)}.py").exists()]
    assert not missing, f'routed handler modules not found: {missing}'


def test_router_reached_through_api_stack():
    assert ROUTER_MODULE in {module for _m, _p, module in api_routes()}


def test_every_routed_handler_enforces_resource_access():
    unprotected = sorted(
        module for module in routed_handler_modules()
        if module not in ALLOWLIST and '@require_resource_access(' not in _source(module)
    )
    assert not unprotected, (
        f'routed handlers without @require_resource_access: {unprotected}. '
        'Protect them, or add them to ALLOWLIST with the reason they are global.')


def test_allowlisted_handlers_still_check_something():
    weak = sorted(module for module, (_why, marker) in ALLOWLIST.items()
                  if module in routed_handler_modules() and marker not in _source(module))
    assert not weak, f'allowlisted handlers missing their documented check: {weak}'


def test_allowlist_has_no_stale_entries():
    stale = sorted(set(ALLOWLIST) - routed_handler_modules())
    assert not stale, f'ALLOWLIST entries that are no longer routed: {stale}'


def test_allowlisted_handlers_do_not_also_use_the_decorator():
    both = sorted(m for m in ALLOWLIST if m in routed_handler_modules()
                  and '@require_resource_access(' in _source(m))
    assert not both, f'remove these from ALLOWLIST, they are protected: {both}'
