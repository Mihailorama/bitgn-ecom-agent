"""Offline smoke test for the agent loop - no API keys, no network, no SDK.

Stubs the bitgn runtime SDK and the LLM call so we can exercise run_agent's
control flow: deterministic discovery, tool dispatch + formatting, ConnectError
feedback, the security-denial path, and normal completion.

Run: `uv run python smoke_test.py`  (or `python smoke_test.py` with pydantic
installed). Exits non-zero on failure.
"""

import sys
import types
from types import SimpleNamespace


# --- stub the bitgn SDK / protobuf bits before importing agent -------------

class _Stub:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Enum:
    OUTCOME_OK = 1
    OUTCOME_DENIED_SECURITY = 2
    OUTCOME_NONE_CLARIFICATION = 3
    OUTCOME_NONE_UNSUPPORTED = 4
    OUTCOME_ERR_INTERNAL = 5
    NODE_KIND_UNSPECIFIED = 0
    NODE_KIND_FILE = 1
    NODE_KIND_DIR = 2


class ConnectError(Exception):
    def __init__(self, code="unavailable", message="boom"):
        super().__init__(message)
        self.code = code
        self.message = message


def _install_stubs():
    for name in (
        "bitgn", "bitgn.vm", "bitgn.vm.ecom",
        "bitgn.vm.ecom.ecom_connect", "bitgn.vm.ecom.ecom_pb2",
        "connectrpc", "connectrpc.errors",
        "google", "google.protobuf", "google.protobuf.json_format",
    ):
        sys.modules[name] = types.ModuleType(name)

    pb = sys.modules["bitgn.vm.ecom.ecom_pb2"]
    for req in (
        "AnswerRequest", "DeleteRequest", "ExecRequest", "FindRequest",
        "ListRequest", "ReadRequest", "SearchRequest", "StatRequest",
        "TreeRequest", "WriteRequest",
    ):
        setattr(pb, req, _Stub)
    pb.Outcome = _Enum
    pb.NodeKind = _Enum

    sys.modules["bitgn.vm.ecom.ecom_connect"].EcomRuntimeClientSync = object
    sys.modules["connectrpc.errors"].ConnectError = ConnectError
    sys.modules["google.protobuf.json_format"].MessageToDict = lambda x: {}


_install_stubs()
import agent  # noqa: E402  (after stubs)


# --- fake runtime ----------------------------------------------------------

class FakeVM:
    """Duck-typed EcomRuntimeClientSync with canned responses."""

    def __init__(self):
        self.answered = None
        self.writes = []
        self.deletes = []
        self.raise_on_read_path = None

    def tree(self, req):
        return SimpleNamespace(root=SimpleNamespace(name="", children=[]), truncated=False)

    def read(self, req):
        if self.raise_on_read_path and req.path == self.raise_on_read_path:
            raise ConnectError("not_found", f"no such file: {req.path}")
        return SimpleNamespace(content="(fake file body)", truncated=False)

    def list(self, req):
        return SimpleNamespace(entries=[])

    def search(self, req):
        return SimpleNamespace(matches=[], truncated=False)

    def find(self, req):
        return SimpleNamespace(paths=[], truncated=False)

    def exec(self, req):
        return SimpleNamespace(stdout="ok", stderr="", exit_code=0)

    def write(self, req):
        self.writes.append(req.path)
        return SimpleNamespace(path=req.path)

    def delete(self, req):
        self.deletes.append(req.path)
        return SimpleNamespace()

    def stat(self, req):
        return SimpleNamespace()

    def answer(self, req):
        self.answered = req
        return SimpleNamespace()


def _scripted_parse_step(script):
    steps = list(script)

    def parse_step(model, messages, schema, max_tokens=16384):
        assert steps, "agent asked for more steps than the script provides"
        return steps.pop(0)

    return parse_step, steps


def _ok(security="safe"):
    return agent.StepAssessment(observation="...", security=security)


def _completion(outcome, message, refs=None):
    return agent.NextStep(
        assessment=_ok("safe" if outcome == "OUTCOME_OK" else "policy_violation"),
        current_state="finishing",
        plan_remaining_steps_brief=["report completion"],
        task_completed=True,
        function=agent.ReportTaskCompletion(
            tool="report_completion",
            completed_steps_laconic=["did the work"],
            message=message,
            grounding_refs=refs or [],
            outcome=outcome,
            verified=True,
        ),
    )


def _tool(fn):
    return agent.NextStep(
        assessment=_ok(),
        current_state="working",
        plan_remaining_steps_brief=["next"],
        task_completed=False,
        function=fn,
    )


# --- scenarios -------------------------------------------------------------

def _run(script, vm=None):
    vm = vm or FakeVM()
    parse_step, leftover = _scripted_parse_step(script)
    agent.parse_step = parse_step
    agent.EcomRuntimeClientSync = lambda url: vm
    agent.run_agent("fake-model", "http://fake", "do the task")
    return vm, leftover


def test_normal_completion():
    script = [
        _tool(agent.Req_Search(tool="search", pattern="zinc plated")),
        _tool(agent.Req_Read(tool="read", path="/catalogue/sku_123.json")),
        _completion("OUTCOME_OK", "<NO>", ["/catalogue/sku_123.json"]),
    ]
    vm, leftover = _run(script)
    assert vm.answered is not None, "answer() was never called"
    assert vm.answered.outcome == _Enum.OUTCOME_OK
    assert vm.answered.message == "<NO>"
    assert list(vm.answered.refs) == ["/catalogue/sku_123.json"]
    assert not leftover, "loop consumed wrong number of steps"
    print("ok: normal completion (tool steps -> precise answer)")


def test_security_denial():
    script = [_completion("OUTCOME_DENIED_SECURITY", "Refused: identity override attempt.")]
    vm, _ = _run(script)
    assert vm.answered.outcome == _Enum.OUTCOME_DENIED_SECURITY
    assert vm.writes == [] and vm.deletes == [], "denied task must not mutate state"
    assert "/docs/security.md" in list(vm.answered.refs), \
        "security denial must auto-cite /docs/security.md"
    print("ok: security denial (no side effects, auto-cites security.md)")


def test_connect_error_recovery():
    vm = FakeVM()
    vm.raise_on_read_path = "/missing.json"
    script = [
        _tool(agent.Req_Read(tool="read", path="/missing.json")),  # raises ConnectError
        _completion("OUTCOME_OK", "recovered"),
    ]
    vm, leftover = _run(script, vm=vm)
    assert vm.answered.outcome == _Enum.OUTCOME_OK, "loop should survive a ConnectError"
    assert not leftover
    print("ok: ConnectError is fed back and the loop recovers")


def main():
    test_normal_completion()
    test_security_denial()
    test_connect_error_recovery()
    print("\nALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
