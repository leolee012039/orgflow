from typing import Literal, Optional, Union, Any
from pydantic import BaseModel, ConfigDict, Field

# Origin indicator for responses
OriginType = Literal["live", "repaired", "fixture"]

# -----------------------------------------------------------------------------
# 1. Organization Schemas
# -----------------------------------------------------------------------------

class Evidence(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    doc: str
    quote: str

class Department(BaseModel):
    name: str
    head_role_id: str

class Role(BaseModel):
    id: str
    title: str
    department: Optional[str] = None
    reports_to: Optional[str] = None
    responsibilities: list[str] = Field(default_factory=list)

class Relationship(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_dept: str = Field(..., alias="from")
    to: str
    description: str
    evidence: Evidence

class Organization(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    company: str
    departments: list[Department]
    roles: list[Role]
    relationships: list[Relationship] = Field(default_factory=list)

class OrganizationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    company: str
    departments: list[Department]
    roles: list[Role]
    relationships: list[Relationship] = Field(default_factory=list)
    origin: OriginType = "live"

# -----------------------------------------------------------------------------
# 2. Opportunities Schemas
# -----------------------------------------------------------------------------

class Opportunity(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    name: str
    departments: list[str]
    manual_handoffs: int
    impact: Literal["HIGH", "MEDIUM", "LOW"]
    why: str
    executable: bool
    evidence: list[Evidence] = Field(default_factory=list)

class Opportunities(BaseModel):
    opportunities: list[Opportunity]

class OpportunitiesResponse(BaseModel):
    opportunities: list[Opportunity]
    origin: OriginType = "live"

# -----------------------------------------------------------------------------
# 3. Workflow Schemas
# -----------------------------------------------------------------------------

class RuleWhen(BaseModel):
    field: str
    op: Literal["<", "<=", ">", ">=", "=="]
    value: Union[int, float, str]

class Rule(BaseModel):
    id: str
    when: RuleWhen
    source: str

StepType = Literal["approval", "ai_review", "task", "notification"]

class Step(BaseModel):
    id: str
    type: StepType
    actor: str
    only_if: Optional[str] = None
    check: Optional[str] = None
    on_fail: Optional[str] = None

class Workflow(BaseModel):
    workflow_name: str
    opportunity_id: str
    required_fields: list[str]
    rules: list[Rule] = Field(default_factory=list)
    steps: list[Step]
    unresolved_actors: list[str] = Field(default_factory=list)
    explanation: str

class WorkflowResponse(BaseModel):
    workflow_name: str
    opportunity_id: str
    required_fields: list[str]
    rules: list[Rule] = Field(default_factory=list)
    steps: list[Step]
    unresolved_actors: list[str] = Field(default_factory=list)
    explanation: str
    origin: OriginType = "live"

# -----------------------------------------------------------------------------
# 4. Request Form & Execution Trace Schemas
# -----------------------------------------------------------------------------

class PurchaseRequestForm(BaseModel):
    model_config = ConfigDict(extra="allow")
    request_id: str = "PR-2026-0142"
    requester: str = "Emma Chen"
    department: str = "Operations"
    item: str = "MacBook Pro"
    estimated_cost: float = 2400.0
    business_justification: Optional[str] = None

StepResultType = Literal["PASSED", "SKIPPED", "DONE", "RETURNED", "HUMAN_REVIEW"]

class StepTrace(BaseModel):
    step_id: str
    type: str
    actor: str
    result: StepResultType
    reason: str
    rule_id: Optional[str] = None
    source: Optional[str] = None

TraceStatusType = Literal["COMPLETED", "RETURNED", "NEEDS_HUMAN_REVIEW"]

class TraceMetrics(BaseModel):
    manual_handoffs_before: int = 4
    human_approvals: int = 0
    ai_checks: int = 0

class ExecutionTrace(BaseModel):
    request_id: str
    status: TraceStatusType
    steps: list[StepTrace] = Field(default_factory=list)
    metrics: TraceMetrics = Field(default_factory=TraceMetrics)

# -----------------------------------------------------------------------------
# 5. AI Review Schemas
# -----------------------------------------------------------------------------

class AIReviewResponse(BaseModel):
    decision: Literal["PASS", "NEEDS_HUMAN_REVIEW"]
    reasons: list[str] = Field(default_factory=list)
