"""Independent behavior oracle, with no imports from the invoice model or tools."""


def expected(raw):
    answers = []
    for row in raw["cases"]:
        bad = not isinstance(row.get("customer"), str) or not row.get("customer", "").strip()
        values = {}
        for name in ("quantity", "unit_cents", "discount_cents"):
            value = row.get(name, 0 if name == "discount_cents" else None)
            if type(value) is int:
                values[name] = value
            elif type(value) is str and value and all("0" <= ch <= "9" for ch in value):
                values[name] = int(value)
            else:
                bad = True
                values[name] = 0
        q, u, d = values["quantity"], values["unit_cents"], values["discount_cents"]
        bad = bad or q < 1 or u < 0 or d < 0 or d > q * u
        note = row.get("note")
        bad = bad or (note is not None and type(note) is not str)
        if bad:
            answers.append({"ok": False, "error": "invalid_invoice"})
        else:
            answers.append(
                {
                    "ok": True,
                    "invoice": {
                        "customer": row["customer"].strip(),
                        "quantity": q,
                        "unit_cents": u,
                        "discount_cents": d,
                        "note": note,
                        "total_cents": q * u - d,
                    },
                }
            )
    return {
        "responses": answers,
        "installed_version": "2.13.4",
        "requirement": "pydantic==2.13.4",
        "model_uses_target": True,
    }
