"""Pydantic v1-to-v2 invoice importer repair."""

import importlib.metadata

from plugin.worker import run

STARTER = {
    "requirements.txt": "pydantic==1.10.26\n",
    "invoice.py": """from pydantic import BaseModel, validator, root_validator

class Invoice(BaseModel):
    customer: str
    quantity: int
    unit_cents: int
    discount_cents: int = 0
    note: str | None = None

    @validator("customer", pre=True)
    def clean_customer(cls, value):
        if not isinstance(value, str):
            raise ValueError("text required")
        value = value.strip()
        if not value:
            raise ValueError("empty customer")
        return value

    @validator("quantity", "unit_cents", "discount_cents", pre=True)
    def integers(cls, value):
        if isinstance(value, bool) or not (isinstance(value, int) or isinstance(value, str) and value.isascii() and value.isdigit()):
            raise ValueError("integer required")
        return int(value)

    @validator("note", pre=True)
    def text_note(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError("text required")
        return value

    @root_validator
    def amounts(cls, values):
        q, u, d = values.get("quantity", 0), values.get("unit_cents", -1), values.get("discount_cents", -1)
        if q <= 0 or u < 0 or d < 0 or d > q * u:
            raise ValueError("invalid amount")
        return values

def process_invoice(payload):
    try:
        data = Invoice.parse_obj(payload).dict()
        data["total_cents"] = data["quantity"] * data["unit_cents"] - data["discount_cents"]
        return {"ok": True, "invoice": data}
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid_invoice"}
""",
}
RESULT_FILES = []
SPEC = """Upgrade requirements.txt to exactly pydantic==2.13.4 and repair invoice.py for native Pydantic v2 (not pydantic.v1).
Keep Invoice as a pydantic.BaseModel and expose process_invoice(payload). It will return {"ok":true,"invoice":...} or {"ok":false,"error":"invalid_invoice"}.
Invoice fields: customer (nonempty stripped string), quantity (>0), unit_cents (>=0), discount_cents (default 0, >=0 and <= quantity*unit_cents), note (default null; string or null). Integer fields accept actual ints or ASCII digit strings, reject bools/floats/negative strings. Unknown fields are ignored. customer must be a string. Canonical output contains exactly those five fields plus total_cents=quantity*unit_cents-discount_cents.
Only invoice.py and requirements.txt may change. Use pydantic, typing or json imports. No filesystem, dynamic imports, monkeypatching, reflection, processes or networking. assess uses the pinned target environment, checks its installed version and the candidate requirement, and runs fresh inputs. Work inspect_task -> edit_files -> assess -> submit the AssessmentOutput exactly; revise once if necessary."""


def fixture(scenario, seed):
    q = seed % 7 + 1
    u = seed * 13 + 101
    cases = [
        {"customer": f"  Customer {seed} ", "quantity": str(q), "unit_cents": u},
        {"customer": "Acme", "quantity": 1, "unit_cents": 0, "discount_cents": 0, "note": None},
        {"customer": "Beta", "quantity": 2, "unit_cents": 300, "discount_cents": 600, "note": "paid", "unused": True},
        {"customer": "C", "quantity": 0, "unit_cents": 5},
        {"customer": "C", "quantity": True, "unit_cents": 5},
        {"customer": "C", "quantity": 1.5, "unit_cents": 5},
        {"customer": "C", "quantity": "-1", "unit_cents": 5},
        {"customer": " ", "quantity": 1, "unit_cents": 5},
        {"quantity": 1, "unit_cents": 5},
        {"customer": "C", "quantity": 1, "unit_cents": 5, "discount_cents": 6},
        {"customer": "C", "quantity": 1, "unit_cents": None},
        {"customer": 12, "quantity": 1, "unit_cents": 5},
        {"customer": "C", "quantity": 1, "unit_cents": 5, "note": 99},
        {"customer": "C", "quantity": "٠١", "unit_cents": 5},
    ]
    if scenario == "empty":
        cases += [{}, {"customer": "", "quantity": "", "unit_cents": 0}]
    if scenario == "boundary":
        cases += [{"customer": "Boundary", "quantity": 2**35, "unit_cents": 2**20, "discount_cents": 1}]
    if scenario == "invalid":
        cases += [
            {"customer": "C", "quantity": 2, "unit_cents": -1},
            {"customer": "C", "quantity": "1.0", "unit_cents": 1},
        ]
    return {"scenario": scenario, "seed": seed, "cases": cases, "target": "2.13.4"}


def measure(files, raw, workspace):
    responses = run(
        files["invoice.py"],
        {"cases": raw["cases"]},
        """from pydantic import BaseModel, field_validator, model_validator
import pydantic, typing
class Warmup(BaseModel):
    customer: str
    quantity: int
    note: str | None = None
    @field_validator("quantity", mode="before")
    @classmethod
    def quantity_value(cls,value):
        return value
    @model_validator(mode="after")
    def finish(self):
        return self
Warmup(customer="warmup",quantity=1).model_dump()
""",
        """
answers = [namespace["process_invoice"](row) for row in request["cases"]]
uses_target = isinstance(namespace.get("Invoice"), type) and issubclass(namespace["Invoice"], BaseModel)
print(json.dumps({"responses":answers,"model_uses_target":uses_target}, allow_nan=False))
""",
    )
    return {
        **responses,
        "installed_version": importlib.metadata.version("pydantic"),
        "requirement": files["requirements.txt"].strip(),
    }
