"""Guard: a Lambda that (transitively) imports pydantic must ``import lambda_init`` first.

``lambda_init`` adds ``dependencies/`` (where pydantic lives in the deployed
package) to ``sys.path``.  ``conftest.py`` stubs it and the tests use the
system pydantic, so a wrong import order never fails a unit test — only the
cold start in AWS.  This test walks the static import graph of every handler
module and fails when a pydantic-importing module is reached before
``lambda_init``.
"""
import ast
import os
from typing import Dict, List, Optional, Set

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_MODULES = {
    name[:-3] for name in os.listdir(HERE) if name.endswith('.py')
} | {
    f'handlers.{name[:-3]}' for name in os.listdir(os.path.join(HERE, 'handlers')) if name.endswith('.py')
}


def _module_path(module: str) -> str:
    return os.path.join(HERE, *module.split('.')) + '.py'


def _top_level_imports(module: str) -> List[str]:
    """Imported module names of ``module`` at module level, in source order."""
    with open(_module_path(module), encoding='utf-8') as handle:
        tree = ast.parse(handle.read())
    names: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


_cache: Dict[str, Optional[str]] = {}


def first_pydantic_import_before_lambda_init(module: str, seen: Optional[Set[str]] = None) -> Optional[str]:
    """The first module in import order that imports pydantic before ``lambda_init`` was imported.

    Returns ``None`` when the module is safe (``lambda_init`` comes first, or
    pydantic is never reached).
    """
    if module in _cache:
        return _cache[module]
    seen = seen or set()
    if module in seen:
        return None
    seen.add(module)
    for name in _top_level_imports(module):
        if name == 'lambda_init':
            _cache[module] = None
            return None
        if name == 'pydantic' or name.startswith('pydantic.'):
            _cache[module] = module
            return module
        if name in LOCAL_MODULES:
            offender = first_pydantic_import_before_lambda_init(name, seen)
            if offender is not None:
                _cache[module] = offender
                return offender
    _cache[module] = None
    return None


def _defines_entry_point(module: str) -> bool:
    """True when ``module`` defines a top-level ``handler`` / ``handle`` (a Lambda entry point)."""
    with open(_module_path(module), encoding='utf-8') as handle:
        tree = ast.parse(handle.read())
    return any(
        isinstance(node, ast.FunctionDef) and node.name in ('handler', 'handle')
        for node in tree.body
    )


HANDLER_MODULES = sorted(
    module for module in LOCAL_MODULES
    if not module.split('.')[-1].startswith(('test_', 'conftest', 'fake_table', 'authz_test_support'))
    and os.path.exists(_module_path(module))
    and _defines_entry_point(module)
)


@pytest.mark.parametrize('module', HANDLER_MODULES)
def test_pydantic_is_only_reached_after_lambda_init(module):
    offender = first_pydantic_import_before_lambda_init(module)
    assert offender is None, (
        f'{module} reaches pydantic through {offender} before importing lambda_init; '
        f'add `import lambda_init  # noqa: F401` as its first import'
    )


def test_guard_detects_the_execute_lambda_shape(tmp_path, monkeypatch):
    """Sanity check of the walker on a minimal reproduction of the execute Lambda layout."""
    (tmp_path / 'handlers').mkdir()
    (tmp_path / 'lambda_init.py').write_text('')
    (tmp_path / 'models_mod.py').write_text('from pydantic import BaseModel\n')
    (tmp_path / 'steps_mod.py').write_text('from models_mod import x\n')
    (tmp_path / 'bad_lambda.py').write_text('import steps_mod\nimport auth_mod\n')
    (tmp_path / 'auth_mod.py').write_text('import lambda_init\nimport models_mod\n')
    (tmp_path / 'good_lambda.py').write_text('import lambda_init\nimport steps_mod\n')
    monkeypatch.setattr(__import__(__name__), 'HERE', str(tmp_path))
    monkeypatch.setattr(__import__(__name__), 'LOCAL_MODULES',
                        {'lambda_init', 'models_mod', 'steps_mod', 'bad_lambda', 'auth_mod', 'good_lambda'})
    _cache.clear()
    assert first_pydantic_import_before_lambda_init('bad_lambda') == 'models_mod'
    assert first_pydantic_import_before_lambda_init('good_lambda') is None
    assert first_pydantic_import_before_lambda_init('auth_mod') is None
    _cache.clear()
