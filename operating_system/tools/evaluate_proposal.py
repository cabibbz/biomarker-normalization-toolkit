import json
import sys
from pathlib import Path


WEIGHTS = {
    "compliance": 25,
    "speed": 20,
    "pain": 20,
    "reuse": 15,
    "delivery": 10,
    "revenue": 10,
}


def fail_reasons(data):
    reasons = []

    if data.get("is_consumer_product"):
        reasons.append("consumer-facing product at launch")
    if data.get("hosts_live_phi"):
        reasons.append("hosts live PHI at launch")
    if data.get("requires_hipaa_ops_before_revenue"):
        reasons.append("requires HIPAA operations before first revenue")
    if data.get("requires_clinicians_or_medical_structure"):
        reasons.append("requires clinicians, licensure, or medical-practice structure")
    if data.get("requires_clia_operations"):
        reasons.append("requires CLIA laboratory operations")
    if data.get("requires_fda_regulated_interpretation"):
        reasons.append("requires FDA-regulated interpretation behavior")
    if data.get("incremental_launch_cost_usd", 10**9) > 1000:
        reasons.append("launch cost exceeds $1,000")
    if data.get("needs_live_patient_data_in_our_env"):
        reasons.append("needs live patient data in our environment")
    if not data.get("improves_normalization_corpus"):
        reasons.append("does not improve the normalization corpus")
    if not data.get("repeatable_asset"):
        reasons.append("creates custom work without a repeatable asset")

    return reasons


def weighted_score(data):
    scores = data.get("scores", {})
    total = 0

    for key, weight in WEIGHTS.items():
        value = scores.get(key)
        if value is None:
            raise ValueError(f"missing score: {key}")
        if not isinstance(value, int) or value < 0 or value > 5:
            raise ValueError(f"score '{key}' must be an integer from 0 to 5")
        total += value * weight

    return total / 5


def recommendation(score):
    if score >= 85:
        return "BUILD NOW"
    if score >= 70:
        return "ONLY BUILD IF IT UNLOCKS A SIGNED CUSTOMER"
    if score >= 50:
        return "BACKLOG ONLY"
    return "REJECT"


def main():
    if len(sys.argv) != 2:
        print("Usage: python evaluate_proposal.py <proposal.json>")
        sys.exit(2)

    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))

    reasons = fail_reasons(data)
    score = weighted_score(data)

    print(f"Proposal: {data.get('name', 'unnamed')}")
    print(f"Weighted score: {score:.1f}/100")

    if reasons:
        print("Hard constraint result: FAIL")
        for reason in reasons:
            print(f"- {reason}")
        print("Final decision: REJECT")
        sys.exit(1)

    print("Hard constraint result: PASS")
    print(f"Final decision: {recommendation(score)}")


if __name__ == "__main__":
    main()
