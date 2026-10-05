"""The bundled NovaGear sample, shared by the tests: its PDFs, their text, and its saved stage answers."""

import copy
from pathlib import Path

import pipeline
from guard import extract_pdf_text, load_fixture
from schemas import DepartmentMap, Organization, Workflow, WorkflowPlan

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "demo_assets" / "en"
POLICY_NAMES = ["NovaGear_Purchasing_Policy.pdf", "NovaGear_Procurement_Payment_Procedures.pdf",
                "NovaGear_Sales_Discount_Policy.pdf"]
ORG_PDF = (EN / "NovaGear_Organization_Chart.pdf").read_bytes()
POLICY_PDFS = [(EN / name).read_bytes() for name in POLICY_NAMES]
PURCHASING_PDF = POLICY_PDFS[0]
DOCS = pipeline.Docs(ORG_PDF, POLICY_PDFS)
ORG_TEXT = extract_pdf_text(ORG_PDF)
DOC_TEXT = "\n".join([ORG_TEXT, *(extract_pdf_text(p) for p in POLICY_PDFS)])

# Workflow ids in the saved plan, along the Operations -> Procurement -> Finance chain
OPERATIONS = "operations_purchase_request_submission"
PROCUREMENT = "procurement_purchasing_and_order_placement"
PAYMENT = "finance_supplier_invoice_payment"
DISCOUNT = "sales_quote_discount_approval"
CREDIT = "finance_customer_credit_check"


def fixture(name: str) -> dict:
    """A deep copy of a saved NovaGear stage answer, safe to change in a test."""
    return copy.deepcopy(load_fixture(f"novagear/{name}"))


def org() -> Organization:
    return Organization.model_validate(fixture("organization.json"))


def department_map() -> DepartmentMap:
    return DepartmentMap.model_validate(fixture("department_map.json"))


def plan() -> WorkflowPlan:
    return WorkflowPlan.model_validate(fixture("workflow_plan.json"))


def planned(workflow_id: str):
    return next(w for w in plan().workflows if w.id == workflow_id)


def workflow(workflow_id: str) -> Workflow:
    return Workflow.model_validate(fixture(f"workflows/{workflow_id}.json"))


def all_workflows() -> list[Workflow]:
    return [workflow(i) for i in (OPERATIONS, PROCUREMENT, PAYMENT, DISCOUNT, CREDIT)]


def upload_files(org_pdf: bytes = ORG_PDF, policies: list[bytes] | None = None) -> list:
    """Multipart files for the API: one org chart and every policy under the same field name."""
    policies = POLICY_PDFS if policies is None else policies
    return [("org_chart", ("org.pdf", org_pdf, "application/pdf")),
            *(("policies", (f"policy_{i}.pdf", p, "application/pdf")) for i, p in enumerate(policies, 1))]
