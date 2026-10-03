"""Contract shape check against the DC-COLL-001 example requirements."""

import json
from pathlib import Path


def test_golden_contract_has_dc_coll_required_sections() -> None:
    contract = json.loads(Path("contracts/golden_c360_v1.json").read_text(encoding="utf-8"))
    for key in ("owner", "schema", "quality_rules", "allowed_uses", "refresh_frequency"):
        assert contract.get(key), f"missing required contract section: {key}"
    assert contract["schema"]["golden_customers"]["grain"]
    assert contract["schema"]["identity_crosswalk"]["grain"]
    assert contract["outputs"]["golden_customers"]["required_columns"]
    assert contract["outputs"]["identity_crosswalk"]["required_columns"]
    assert len(contract["quality_rules"]) >= 5
