from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    # None when the documents name a unit but not who leads it
    head_role_id: Optional[str] = None

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

# -----------------------------------------------------------------------------
# 2. Department map and workflow plan
# -----------------------------------------------------------------------------

class DepartmentWork(BaseModel):
    """One kind of work a department does, as the documents state it."""
    task: str
    evidence: Evidence

class DepartmentProfile(BaseModel):
    name: str
    summary: str
    work: list[DepartmentWork]

class Handoff(BaseModel):
    """Work passing from one department to another."""
    model_config = ConfigDict(populate_by_name=True)
    from_dept: str = Field(..., alias="from")
    to: str
    what: str
    evidence: Evidence

class DepartmentMap(BaseModel):
    departments: list[DepartmentProfile]
    handoffs: list[Handoff] = Field(default_factory=list)

BasisType = Literal["policy", "org_chart"]

class WorkflowCandidate(BaseModel):
    """A workflow one department could automate, before it is built."""
    id: str
    department: str
    name: str
    trigger: str
    starts_from: Optional[str] = None  # the department whose handoff starts it; None: a person submits a form
    hands_to: Optional[str] = None  # the department that receives its result
    output: str
    basis: BasisType  # "policy": rules written in a policy; "org_chart": only responsibilities describe it
    why: str
    manual_handoffs: int
    evidence: list[Evidence]

class WorkflowPlan(BaseModel):
    workflows: list[WorkflowCandidate]

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

class AmountTier(BaseModel):
    """One approval level of the policy, with the amounts it states at each end."""
    field: str = "estimated_cost"  # the form field the amounts apply to
    min: Optional[float] = None  # None: the tier has no lower end
    max: Optional[float] = None  # None: the tier has no upper end
    source: str

class FormField(BaseModel):
    """A field of the form that starts a workflow."""
    name: str  # snake_case
    label: str  # as the documents call it
    type: Literal["text", "number", "date", "choice"] = "text"
    options: list[str] = Field(default_factory=list)  # for "choice"

StepType = Literal["approval", "ai_review", "task", "notification"]

class Step(BaseModel):
    id: str
    type: StepType
    actor: str
    only_if: Optional[str] = None
    also_if: Optional[str] = None  # a second rule that must also hold, for a range of amounts
    check: Optional[str] = None
    on_fail: Optional[str] = None

class Workflow(BaseModel):
    workflow_name: str
    opportunity_id: str  # the candidate (or opportunity) it was built from
    department: str = ""  # the department that owns it
    fields: list[FormField] = Field(default_factory=list)  # empty: the original purchase request form
    required_fields: list[str]
    rules: list[Rule] = Field(default_factory=list)
    steps: list[Step]
    unresolved_actors: list[str] = Field(default_factory=list)
    amount_tiers: list[AmountTier] = Field(default_factory=list)
    starts_from: Optional[str] = None
    hands_to: Optional[str] = None
    output: str = ""
    explanation: str
    # Set by code, never by Gemini: the built workflow this one was built to receive cases from
    upstream_id: Optional[str] = None

# -----------------------------------------------------------------------------
# 4. Request Form & Execution Trace Schemas
# -----------------------------------------------------------------------------

MAX_FORM_NUMBER = 1e15  # no real amount or percentage is larger; bigger ones break float comparisons

class RequestForm(BaseModel):
    """What someone submits to start a workflow: who, from which department, plus the workflow's own fields."""
    model_config = ConfigDict(extra="allow")
    request_id: str = "REQ-0001"
    requester: str = ""
    department: str = ""

    @model_validator(mode="after")
    def _numbers_are_finite(self):
        for name, value in (self.model_extra or {}).items():
            # "not <" also catches infinity and NaN
            if isinstance(value, (int, float)) and not isinstance(value, bool) and not abs(value) < MAX_FORM_NUMBER:
                raise ValueError(f"{name} must be a number below {MAX_FORM_NUMBER:,.0f}")
        return self

STANDARD_FIELDS = {"requester", "department"}

class PurchaseRequestForm(RequestForm):
    """The original NovaGear purchase request form, used by workflows without their own fields."""
    request_id: str = "PR-2026-0142"
    requester: str = "Emma Chen"
    department: str = "Operations"
    item: str = "MacBook Pro"
    estimated_cost: float = 2400.0
    business_justification: Optional[str] = None

# -----------------------------------------------------------------------------
# Decisions: a person settles what the documents leave open, once, and cases follow it
# -----------------------------------------------------------------------------

class ApproverDecision(BaseModel):
    """A role in the organization approves in place of an approver the org chart doesn't have."""
    kind: Literal["approver"] = "approver"
    workflow_id: str
    actor: str  # the approver the policy names, e.g. "Director"
    role_id: str  # the organization's role that approves instead

class AmountDecision(BaseModel):
    """Which of two approval levels owns the exact amount where the policy leaves it in neither, or both."""
    kind: Literal["amount"] = "amount"
    workflow_id: str
    field: str
    amount: float
    level: Literal["below", "above"]

Decision = Annotated[Union[ApproverDecision, AmountDecision], Field(discriminator="kind")]

MAX_DECISIONS = 50

StepResultType = Literal["PASSED", "SKIPPED", "DONE", "RETURNED", "HUMAN_REVIEW"]

class StepTrace(BaseModel):
    step_id: str
    type: str
    actor: str
    result: StepResultType
    reason: str
    rule_id: Optional[str] = None
    source: Optional[str] = None
    # The approver the policy names, when a person chose this step's role to stand in for it
    stands_in_for: Optional[str] = None

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

class ChainLeg(BaseModel):
    """One department's workflow inside a chained run."""
    workflow_id: str
    workflow_name: str
    department: str
    trace: ExecutionTrace

class ChainTrace(BaseModel):
    """A case that moves from one department's workflow to the next."""
    request_id: str
    status: TraceStatusType
    legs: list[ChainLeg] = Field(default_factory=list)
    # When the last workflow hands to a department with no built workflow yet
    waiting_for: Optional[str] = None

# -----------------------------------------------------------------------------
# 5. AI Review Schemas
# -----------------------------------------------------------------------------

class AIReviewResponse(BaseModel):
    decision: Literal["PASS", "NEEDS_HUMAN_REVIEW"]
    reasons: list[str] = Field(default_factory=list)
