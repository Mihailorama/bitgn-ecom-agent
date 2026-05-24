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
        self.stat_not_found = set()

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
        if req.path in self.stat_not_found:
            raise ConnectError("not_found", f"no such: {req.path}")
        return SimpleNamespace(path=req.path)

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

def _run(script, vm=None, task="do the task"):
    vm = vm or FakeVM()
    parse_step, leftover = _scripted_parse_step(script)
    agent.parse_step = parse_step
    agent.EcomRuntimeClientSync = lambda url: vm
    agent.run_agent("fake-model", "http://fake", task)
    return vm, leftover


def _mk_completion(message, outcome="OUTCOME_OK", refs=None):
    return agent.ReportTaskCompletion(
        tool="report_completion",
        completed_steps_laconic=["x"],
        message=message,
        grounding_refs=refs or [],
        outcome=outcome,
        verified=True,
    )


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


def test_sql_path_extraction():
    csv_out = (
        "sku,path,brand,name\n"
        "FST-1HE3ZSQ6,/proc/catalog/FST-1HE3ZSQ6.json,Heco,Wood Screw\n"
        "WRK-24ARZRCH,/proc/catalog/Engelbert Strauss/WRK-24ARZRCH.json,Engelbert Strauss,Work Trousers\n"
    )
    pairs = agent._extract_paths_with_labels(csv_out)
    paths = [p for p, _ in pairs]
    assert paths == [
        "/proc/catalog/FST-1HE3ZSQ6.json",
        "/proc/catalog/Engelbert Strauss/WRK-24ARZRCH.json",
    ], f"space-in-path must survive; got {paths}"
    assert "sku=FST-1HE3ZSQ6" in pairs[0][1]
    # scalar aggregate (no path column) -> nothing
    assert agent._extract_paths_with_labels("count(*)\n7\n") == []
    # header only -> nothing
    assert agent._extract_paths_with_labels("sku,path,brand\n") == []
    # non-/proc or non-.json values skipped
    assert agent._extract_paths_with_labels("sku,path\nX,not_a_path\n") == []
    # path column resolved by header name, not position
    one = agent._extract_paths_with_labels("a,b,path\n1,2,/proc/stores/s1.json\n")
    assert one == [("/proc/stores/s1.json", "")], one
    print("ok: SQL path extraction (header-index, spaces, scalars, ragged)")


def test_format_enforcement():
    fn = _mk_completion("<COUNT:7>")
    assert agent._enforce_format_inplace("Answer exactly as <COUNT:%d>", fn) is None
    assert fn.message == "<COUNT:7>", "already-valid must be untouched"

    fn = _mk_completion("The store has 7 units.")
    assert agent._enforce_format_inplace("Answer exactly as <COUNT:%d>", fn) is None
    assert fn.message == "<COUNT:7>", "single int must coerce into the tag"

    fn = _mk_completion("9")
    assert agent._enforce_format_inplace("reply [QTY:%d]", fn) is None
    assert fn.message == "[QTY:9]"

    fn = _mk_completion("7 of 12")
    corr = agent._enforce_format_inplace("Answer exactly as <COUNT:%d>", fn)
    assert corr is not None and "FORMAT REQUIRED" in corr, "ambiguous ints must not coerce"

    fn = _mk_completion("some prose answer")
    assert agent._enforce_format_inplace("Describe the policy", fn) is None
    assert fn.message == "some prose answer", "free-form answers must never be touched"

    fn = _mk_completion("It is not stocked")
    assert agent._enforce_format_inplace("answer <YES> or <NO>", fn) is not None, \
        "malformed yes/no must re-prompt (cannot coerce polarity)"
    print("ok: format detection + safe coercion + conservative re-prompt")


def test_verify_refs_drop_safety():
    vm = FakeVM()
    vm.stat_not_found = {"/proc/baskets/ghost.json"}
    kept = agent._verify_refs(
        vm, ["/proc/baskets/ghost.json", "/docs/security.md", "/proc/stores/store_x.json"]
    )
    assert "/proc/baskets/ghost.json" not in kept, "must drop a not_found ref"
    assert "/docs/security.md" in kept, "must keep a stat-valid doc absent from any ledger"
    assert "/proc/stores/store_x.json" in kept
    print("ok: _verify_refs drops only not_found, keeps stat-valid refs")


def test_format_loopback():
    # First answer is ambiguous (two ints, cannot coerce) -> gate re-prompts once;
    # second answer conforms -> submitted. Exactly one extra step consumed.
    script = [
        _completion("OUTCOME_OK", "7 of 12 match", []),
        _completion("OUTCOME_OK", "<COUNT:7>", []),
    ]
    vm, leftover = _run(script, task="How many match? Answer exactly as <COUNT:%d>")
    assert vm.answered is not None and vm.answered.message == "<COUNT:7>"
    assert not leftover, "should consume exactly the two scripted steps"
    print("ok: format re-prompt loop-back (one correction, then submit)")


def main():
    test_normal_completion()
    test_security_denial()
    test_connect_error_recovery()
    test_sql_path_extraction()
    test_format_enforcement()
    test_verify_refs_drop_safety()
    test_format_loopback()
    print("\nALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
