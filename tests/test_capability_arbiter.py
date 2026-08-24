import pytest

from personal_agent.capability import CapabilityArbiter, FunctionWorker, Work


@pytest.mark.asyncio
async def test_arbiter_dispatches_any_capable_units_and_synthesizes():
    workers = [
        FunctionWorker("static", {"inspect"}, lambda work: "static evidence"),
        FunctionWorker("tests", {"inspect", "verify"}, lambda work: "tests evidence"),
        FunctionWorker("unrelated", {"write"}, lambda work: "should not run"),
    ]
    arbiter = CapabilityArbiter(workers)

    work = Work("inspect repository", frozenset({"inspect"}))
    assert {w.name for w in arbiter.select(work)} == {"static", "tests"}

    result = await arbiter.execute(work)
    assert len(result.results) == 2
    assert result.confidence == 1.0
    assert result.disagreements
    assert "static evidence" in result.conclusion
    assert "tests evidence" in result.conclusion


@pytest.mark.asyncio
async def test_arbiter_requires_capability_match():
    arbiter = CapabilityArbiter([FunctionWorker("worker", {"compile"}, lambda work: "ok")])
    with pytest.raises(LookupError):
        await arbiter.execute(Work("review", frozenset({"review"})))


@pytest.mark.asyncio
async def test_one_worker_is_a_complete_unit_of_work():
    arbiter = CapabilityArbiter([FunctionWorker("deterministic", {"check"}, lambda work: "PASS")])
    result = await arbiter.execute(Work("check", frozenset({"check"})))
    assert result.conclusion == "PASS"
    assert result.disagreements == ()
