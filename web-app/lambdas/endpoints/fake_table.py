"""In-memory stand-in for a boto3 DynamoDB ``Table`` for handler tests.

Stores items by ``(pk, sk)`` and understands the subset of the resource
API the template / usecase lambdas use: ``get_item``, ``put_item``,
``delete_item``, ``query`` with ``Key('pk').eq(...)`` optionally ``&
Key('sk').begins_with(...)`` or ``& Key('sk').between(...)``, and
``update_item`` with ``SET`` / ``ADD`` /
``REMOVE`` expressions plus ``attribute_exists(pk)`` or ``attr = :value``
conditions.  Anything else raises,
so a handler that starts using a new call fails loudly in its tests.
"""
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from boto3.dynamodb.conditions import ConditionBase
from botocore.exceptions import ClientError

_KEY = Tuple[str, str]


def _client_error(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


class FakeTable:
    def __init__(self, items: Iterable[Dict[str, Any]] = ()):
        self.items: Dict[_KEY, Dict[str, Any]] = {}
        self.put_calls: List[Dict[str, Any]] = []
        self.update_calls: List[Dict[str, Any]] = []
        self.delete_calls: List[Dict[str, Any]] = []
        for item in items:
            self.items[self._key(item)] = dict(item)

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _key(key: Dict[str, Any]) -> _KEY:
        return key["pk"], key["sk"]

    def get(self, pk: str, sk: str) -> Optional[Dict[str, Any]]:
        return self.items.get((pk, sk))

    def by_prefix(self, pk: str, sk_prefix: str) -> List[Dict[str, Any]]:
        return [dict(v) for (p, s), v in self.items.items() if p == pk and s.startswith(sk_prefix)]

    # -- Table API ---------------------------------------------------------
    def get_item(self, Key, **_):  # noqa: N803
        item = self.get(*self._key(Key))
        return {"Item": dict(item)} if item is not None else {}

    def put_item(self, Item, **_):  # noqa: N803
        self.items[self._key(Item)] = dict(Item)
        self.put_calls.append(dict(Item))
        return {}

    def delete_item(self, Key, **_):  # noqa: N803
        self.delete_calls.append(dict(Key))
        self.items.pop(self._key(Key), None)
        return {}

    def query(self, KeyConditionExpression, **_):  # noqa: N803
        pk, sk_matches = _parse_key_condition(KeyConditionExpression)
        return {"Items": [dict(v) for (p, s), v in self.items.items() if p == pk and sk_matches(s)]}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues=None,  # noqa: N803
                    ExpressionAttributeNames=None, ConditionExpression=None,
                    ReturnValues=None, **_):
        self.update_calls.append({
            "Key": dict(Key), "UpdateExpression": UpdateExpression,
            "ExpressionAttributeValues": ExpressionAttributeValues,
            "ExpressionAttributeNames": ExpressionAttributeNames,
            "ConditionExpression": ConditionExpression,
        })
        key = self._key(Key)
        if ConditionExpression is not None and not _condition_holds(
            _condition_text(ConditionExpression), self.items.get(key), ExpressionAttributeValues or {},
            ExpressionAttributeNames or {},
        ):
            raise _client_error("ConditionalCheckFailedException", "UpdateItem")
        item = self.items.setdefault(key, dict(Key))
        _apply_update(item, UpdateExpression, ExpressionAttributeValues or {}, ExpressionAttributeNames or {})
        if ReturnValues in ("ALL_NEW", "UPDATED_NEW"):
            return {"Attributes": dict(item)}
        return {}

    def batch_writer(self):
        """``with table.batch_writer() as batch`` — writes land in the table immediately."""
        table = self

        class _Writer:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def put_item(self, Item, **_):  # noqa: N803
                table.put_item(Item=Item)

            def delete_item(self, Key, **_):  # noqa: N803
                table.delete_item(Key=Key)

        return _Writer()


class FakeDynamoResource:
    """Stand-in for ``boto3.resource('dynamodb')`` over one ``FakeTable``.

    Supports ``Table(name)`` and ``batch_get_item(RequestItems=...)`` (the
    resource-level call handlers use for ``BatchGetItem``): returns the items
    that exist, in request order, never any ``UnprocessedKeys``.  Enforces the
    real 100-key limit so a caller that forgets to chunk fails in its tests.
    """

    MAX_BATCH_GET_KEYS = 100

    def __init__(self, table: FakeTable, table_name: str):
        self.table = table
        self.table_name = table_name
        self.batch_get_calls: List[List[Dict[str, Any]]] = []

    def Table(self, name: str) -> FakeTable:  # noqa: N802
        if name != self.table_name:
            raise NotImplementedError(f"FakeDynamoResource: unknown table {name!r}")
        return self.table

    def batch_get_item(self, RequestItems, **_):  # noqa: N803
        if set(RequestItems) != {self.table_name}:
            raise NotImplementedError(f"FakeDynamoResource: unknown tables {sorted(RequestItems)!r}")
        keys = list(RequestItems[self.table_name]["Keys"])
        if len(keys) > self.MAX_BATCH_GET_KEYS:
            raise ValueError(f"batch_get_item: {len(keys)} keys exceeds the limit of {self.MAX_BATCH_GET_KEYS}")
        self.batch_get_calls.append([dict(k) for k in keys])
        found = [self.table.get(*self.table._key(k)) for k in keys]
        return {
            "Responses": {self.table_name: [dict(item) for item in found if item is not None]},
            "UnprocessedKeys": {},
        }


def _condition_text(condition) -> str:
    if isinstance(condition, str):
        return condition
    if isinstance(condition, ConditionBase) and condition.expression_operator == "attribute_exists":
        return f"attribute_exists({condition._values[0].name})"
    raise NotImplementedError(f"FakeTable: unsupported ConditionExpression {condition!r}")


_EQUALS_RE = re.compile(r"^\s*(#?\w+)\s*=\s*(:\w+)\s*$")


def _condition_holds(text: str, item: Optional[Dict[str, Any]], values: Dict[str, Any],
                     names: Dict[str, str]) -> bool:
    """``attribute_exists(pk)`` or ``attr = :value`` (also against a missing item)."""
    if text == "attribute_exists(pk)":
        return item is not None
    match = _EQUALS_RE.match(text)
    if match:
        attr, placeholder = match.groups()
        attr = names.get(attr, attr)
        return item is not None and attr in item and item[attr] == values[placeholder]
    raise NotImplementedError(f"FakeTable: unsupported ConditionExpression {text!r}")


def _parse_key_condition(condition) -> Tuple[str, Callable[[str], bool]]:
    """``Key('pk').eq(x)`` alone or ``& Key('sk').begins_with(y)`` / ``& Key('sk').between(lo, hi)``.

    Returns the partition key value and a predicate over the sort key.
    """
    if condition.expression_operator == "AND":
        left, right = condition._values
        pk, _ = _parse_key_condition(left)
        if right._values[0].name != "sk":
            raise NotImplementedError(f"FakeTable: unsupported sk condition {right!r}")
        if right.expression_operator == "begins_with":
            prefix = right._values[1]
            return pk, lambda sk: sk.startswith(prefix)
        if right.expression_operator == "BETWEEN":
            low, high = right._values[1], right._values[2]
            return pk, lambda sk: low <= sk <= high
        raise NotImplementedError(f"FakeTable: unsupported sk condition {right!r}")
    if condition.expression_operator == "=" and condition._values[0].name == "pk":
        return condition._values[1], lambda sk: True
    raise NotImplementedError(f"FakeTable: unsupported key condition {condition!r}")


_CLAUSE_RE = re.compile(r"\b(SET|ADD|REMOVE)\b")


def _apply_update(item: Dict[str, Any], expression: str, values: Dict[str, Any], names: Dict[str, str]) -> None:
    def resolve(name: str) -> str:
        name = name.strip()
        return names[name] if name.startswith("#") else name

    parts = _CLAUSE_RE.split(expression)
    # parts: ['', 'SET', ' a = :a, b = :b ', 'ADD', ' c :one']
    for keyword, body in zip(parts[1::2], parts[2::2]):
        for assignment in filter(None, (a.strip() for a in body.split(","))):
            if keyword == "SET":
                target, _, source = assignment.partition("=")
                source = source.strip()
                if source.startswith(":"):
                    item[resolve(target)] = values[source]
                else:
                    raise NotImplementedError(f"FakeTable: unsupported SET operand {source!r}")
            elif keyword == "ADD":
                target, _, operand = assignment.partition(" ")
                attr = resolve(target)
                item[attr] = item.get(attr, 0) + values[operand.strip()]
            elif keyword == "REMOVE":
                item.pop(resolve(assignment), None)
