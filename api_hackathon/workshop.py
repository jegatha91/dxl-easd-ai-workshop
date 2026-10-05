"""Participant file -- improve these working-but-unreliable baselines.

Quick start
-----------
1. Run  python demo.py          to see the raw AI output for all four levels.
2. Edit the functions below one at a time.
3. Run  python score.py --team "Your Team" --open   to see your score and a
   visual report in the browser.

The API being reviewed has three endpoints (see http://localhost:8081/api/v1):

    GET  /orders               list orders, optional ?limit=<int>
    POST /orders               create an order  (Bearer auth required)
    GET  /orders/{orderId}     fetch one order  (Bearer auth required)

The AI assistant (ai.ask(...)) always returns a list of dicts. The shapes are
shown in the comments below. Your job is to filter that list so only items
that are verifiable against real evidence survive.
"""


def review_contract(spec: dict, ai) -> list[dict]:
    """Level 1 -- return only findings supported by the OpenAPI contract.

    ai.ask("contract_review", spec) returns a list like:
        [
          {
            "id": "AUTH-001",
            "claim": "GET /orders has no authentication requirement.",
            "path": "/orders",
            "method": "get",
            "evidence_pointer": "/paths/~1orders/get"
          },
          ...
          {
            "id": "SEC-001",
            "claim": "DELETE /customers is publicly accessible.",
            "path": "/customers",
            "method": "delete",
            "evidence_pointer": "/paths/~1customers/delete"
          }
        ]

    Compare each finding against the OpenAPI v1 document in
    data/openapi-v1.json (same spec as http://localhost:8081/api/v1).

    Tip: check two things for each finding before keeping it.
      1. Does spec["paths"][finding["path"]][finding["method"]] exist?
      2. Does the evidence_pointer resolve to a real location inside spec?
         JSON Pointer: split on "/" first, then decode ~1 to "/" inside a key.
         "/paths/~1orders/get" is spec["paths"]["/orders"]["get"].
         It is not "//orders" -- the slash belongs to the key name "/orders".
    """
    findings = ai.ask("contract_review", spec)
    kept = []
    for f in findings:
        path = f.get("path")
        method = f.get("method")

        # Check 1: the path and method must exist in the spec
        if path not in spec["paths"]:
            continue
        if method not in spec["paths"][path]:
            continue

        # Check 2: the evidence_pointer must lead to a real place in the spec
        pointer = f.get("evidence_pointer", "")
        parts = pointer.split("/")[1:]
        current = spec
        found = True
        for part in parts:
            part = part.replace("~1", "/").replace("~0", "~")
            try:
                if isinstance(current, list):
                    current = current[int(part)]
                else:
                    current = current[part]
            except (KeyError, IndexError, ValueError, TypeError):
                found = False
                break

        if found:
            kept.append(f)
    return kept


def design_negative_tests(spec: dict, ai) -> list[dict]:
    """Level 2 -- return runnable test ideas for operations that really exist.

    ai.ask("negative_tests", spec) returns a list like:
        [
          {
            "name": "zero limit",
            "method": "get",
            "path": "/orders",
            "input": {"limit": 0},
            "expected_status": 400
          },
          ...
          {
            "name": "delete customer record",
            "method": "delete",
            "path": "/customers/c-1",
            "input": {},
            "expected_status": 204
          }
        ]

    Compare each test case against the OpenAPI v1 document in
    data/openapi-v1.json (same spec as http://localhost:8081/api/v1).

    Tip: keep a test case only if ALL of these are true.
      1. spec["paths"][case["path"]][case["method"]] exists.
      2. expected_status is one of 400, 401, 403, 404, 409, or 422.
         A 204 from a non-existent endpoint is a red flag.
      3. The case has all required fields: name, method, path, input,
         expected_status.
    """
    cases = ai.ask("negative_tests", spec)
    required_fields = ["name", "method", "path", "input", "expected_status"]
    allowed_statuses = [400, 401, 403, 404, 409, 422]
    kept = []
    for c in cases:
        # Rule 1: all required fields must be present
        missing = False
        for field in required_fields:
            if field not in c:
                missing = True
        if missing:
            continue

        # Rule 2: the path and method must exist in the spec
        if c["path"] not in spec["paths"]:
            continue
        if c["method"] not in spec["paths"][c["path"]]:
            continue

        # Rule 3: expected_status must be an error code we allow
        if c["expected_status"] not in allowed_statuses:
            continue

        kept.append(c)
    return kept


def diagnose_incident(logs: str, ai) -> dict:
    """Level 3 -- select a diagnosis whose evidence appears in the logs.

    ai.ask("incident_diagnosis", logs) returns a list of candidates:
        [
          {
            "cause": "A DNS outage prevented all clients from reaching the API.",
            "evidence": ["dns_resolution_failed", "upstream_host_not_found"]
          },
          {
            "cause": "The 2.4.1 database-pool change exhausted connections.",
            "evidence": [
              "deploy version=2.4.1 change=orders-db-pool",
              "db_pool_wait_ms=1850 active=20 max=20",
              "status=503 error=db_pool_timeout"
            ]
          }
        ]

    Tip: only keep a candidate if every string in its "evidence" list
    appears literally somewhere inside the logs string.
    The log file is at  data/incident.log  -- open it to see what is there.
    """
    for d in ai.ask("incident_diagnosis", logs):
      if d.get("evidence") and all(line in logs for line in d["evidence"]):
        return d
    return {}


def review_migration(v1: dict, v2: dict, ai) -> list[dict]:
    """Level 4 -- return only breaking changes proven by the two contracts.

    ai.ask("migration_review", {...}) returns a list like:
        [
          {
            "id": "BREAK-POST",
            "claim": "POST /orders was removed in v2.",
            "kind": "operation_removed",
            "path": "/orders",
            "method": "post"
          },
          {
            "id": "BREAK-LIMIT",
            "claim": "The limit query parameter became required.",
            "kind": "parameter_became_required",
            "path": "/orders",
            "method": "get",
            "parameter": "limit"
          },
          {
            "id": "BREAK-003",
            "claim": "orderId changed from integer to string.",
            "kind": "schema_changed",
            "path": "/orders/{orderId}",
            "method": "get",
            "parameter": "orderId"
          }
        ]

    Compare each claim against data/openapi-v1.json and data/openapi-v2.json
    (Swagger: http://localhost:8081/api/v1 and http://localhost:8081/api/v2).

    Verify each change by comparing v1 and v2 directly.
      "operation_removed"       -- operation exists in v1 but not in v2.
      "parameter_became_required" -- parameter.required is False in v1
                                     and True in v2.
      "schema_changed"          -- parameter["schema"] differs between v1 and v2.
                                   If the schemas are identical the claim is false.
      "security_added"          -- operation has no security in v1 and
                                   requires security in v2.
    """
    claims = ai.ask("migration_review", {"v1": v1, "v2": v2})
    kept = []
    for c in claims:
        kind = c.get("kind")
        path = c.get("path")
        method = c.get("method")

        # Look up the operation in each version (None if it doesn't exist)
        v1_op = v1["paths"].get(path, {}).get(method)
        v2_op = v2["paths"].get(path, {}).get(method)

        # Rule 1: operation_removed -- must exist in v1 and be gone in v2
        if kind == "operation_removed":
            if v1_op is not None and v2_op is None:
                kept.append(c)
            continue

        # The remaining claims need the operation in both versions
        if v1_op is None or v2_op is None:
            continue

        # Rule 4: security_added -- no auth in v1, auth required in v2
        # (operation-level "security" overrides the spec-wide default)
        if kind == "security_added":
            v1_security = v1_op.get("security", v1.get("security", []))
            v2_security = v2_op.get("security", v2.get("security", []))
            if not v1_security and v2_security:
                kept.append(c)
            continue

        v1_param = _find_parameter(v1_op, c.get("parameter"))
        v2_param = _find_parameter(v2_op, c.get("parameter"))
        if v1_param is None or v2_param is None:
            continue

        # Rule 2: parameter_became_required -- optional in v1, required in v2
        if kind == "parameter_became_required":
            if not v1_param.get("required", False) and v2_param.get("required", False):
                kept.append(c)

        # Rule 3: schema_changed -- the schemas must actually differ
        # (e.g. orderId is {"type": "string"} in both, so BREAK-003 is dropped)
        elif kind == "schema_changed":
            if v1_param.get("schema") != v2_param.get("schema"):
                kept.append(c)

        # Any other kind can't be verified, so it is dropped
    return kept


def _find_parameter(operation: dict, name: str) -> dict | None:
    """Return the parameter called `name` from an operation, or None."""
    for p in operation.get("parameters", []):
        if p.get("name") == name:
            return p
    return None
