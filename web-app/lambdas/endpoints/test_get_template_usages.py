"""``GET /templates/{id}/usages`` — which tests use a template (shown before deleting it)."""
import json
import os
from unittest.mock import patch

os.environ.setdefault("TABLE_NAME", "test-table")

import get_template_usages  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from template_usage import usage_item  # noqa: E402

TEMPLATE = {"pk": "TEMPLATES", "sk": "TEMPLATE#t1", "id": "t1", "name": "Login", "version": 3}


def _run(table, template_id="t1", scope="api/templates.read"):
    event = {"requestContext": {"authorizer": {"sub": "u1", "email": "qa@example.com", "scope": scope}},
             "pathParameters": {"id": template_id}}
    with patch.object(get_template_usages, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        return get_template_usages.handler(event, None)


class TestUsages:
    def test_lists_existing_use_cases_sorted_by_name_and_skips_stale(self):
        table = FakeTable([
            TEMPLATE,
            usage_item("t1", "uc-refund", "now"), usage_item("t1", "uc-checkout", "now"), usage_item("t1", "uc-gone", "now"),
            {"pk": "USECASES", "sk": "USECASE#uc-refund", "id": "uc-refund", "name": "Refund"},
            {"pk": "USECASES", "sk": "USECASE#uc-checkout", "id": "uc-checkout", "name": "Checkout"},
        ])
        response = _run(table)
        assert response["statusCode"] == 200, response["body"]
        body = json.loads(response["body"])
        assert body == {"usages": [{"usecase_id": "uc-checkout", "name": "Checkout"},
                                   {"usecase_id": "uc-refund", "name": "Refund"}], "count": 2}
        # a GET never writes
        assert table.put_calls == [] and table.delete_calls == [] and table.update_calls == []

    def test_no_usages(self):
        response = _run(FakeTable([TEMPLATE]))
        assert json.loads(response["body"]) == {"usages": [], "count": 0}

    def test_unknown_template_is_404(self):
        assert _run(FakeTable([TEMPLATE]), "ghost")["statusCode"] == 404

    def test_missing_scope_is_403(self):
        assert _run(FakeTable([TEMPLATE]), scope="api/usecases.read")["statusCode"] == 403
