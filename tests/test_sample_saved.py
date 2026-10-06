"""The sample opens from Gemini's saved reading; anyone else's documents are read live.

Agent calls are faked here: a stage that reaches the agent records it.
"""

import asyncio

import pipeline
from agents import organization_analyst
from agents.runtime import AgentResult
from sample_docs import DOCS, OPERATIONS, ORG_PDF, POLICY_PDFS, department_map, fixture, org, plan, planned

OTHER = pipeline.Docs(ORG_PDF + b"\n% another company's file\n", POLICY_PDFS)  # same text, not the sample


def test_the_sample_opens_from_saved_answers_without_calling_gemini(monkeypatch):
    monkeypatch.setattr(pipeline, "SAMPLE_LIVE", False)
    stages = [
        asyncio.run(pipeline.analyze_organization(DOCS)),
        asyncio.run(pipeline.map_departments(DOCS, org())),
        asyncio.run(pipeline.plan_workflows(DOCS, org(), department_map())),
        asyncio.run(pipeline.build_workflow(DOCS, org(), planned(OPERATIONS))),
    ]
    assert [s.origin for s in stages] == ["saved"] * 4
    assert stages[0].value.company == org().company
    assert len(stages[2].value.workflows) == len(plan().workflows)
    built = stages[3]
    # The saved workflow still gets every check: the missing Director is found by code
    assert [g["actor"] for g in built.extras["gaps"]] == ["Director"]


def test_other_documents_are_read_live(monkeypatch):
    monkeypatch.setattr(pipeline, "SAMPLE_LIVE", False)
    calls = []

    async def fake_analyze(docs):
        calls.append(len(docs))
        return AgentResult(fixture("organization.json"), None, 4000)

    monkeypatch.setattr(organization_analyst, "analyze", fake_analyze)
    result = asyncio.run(pipeline.analyze_organization(OTHER))
    assert calls and result.origin == "live"
