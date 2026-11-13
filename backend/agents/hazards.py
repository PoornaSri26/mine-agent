"""Domain knowledge for the analysis and compliance agents.

The LLM is asked to reason *over* this taxonomy rather than invent categories,
and the same taxonomy produces a deterministic assessment when no API key is
configured. That keeps every answer explainable and testable.
"""

from __future__ import annotations

import re
from typing import Any

TAXONOMY: list[dict[str, Any]] = [
    {
        "id": "roof-fall",
        "label": "Roof fall / strata failure",
        "keywords": ["roof fall", "fall of roof", "collapse", "strata", "overhang", "roof bolting",
                     "support", "caving", "spalling", "hanging wall", "dump failure", "overburden"],
        "drivers": [
            "Unsupported spans left after blasting",
            "Geological discontinuities not mapped before extraction",
            "Delayed or incomplete systematic support",
            "Water ingress weakening the immediate roof",
        ],
        "controls": [
            "Systematic roof bolting to a written support plan with pull-test records",
            "Pre-shift and post-blast examination of roof and sides by a competent person",
            "Scaling of loose rock before anyone enters the working place",
            "Strata monitoring (tell-tales, convergence stations) in high-risk zones",
        ],
        "statute": "Mines Act 1952; Metalliferous Mines Regulations 1961 (support of ground)",
        "checks": [
            ("Support of ground", "Written support plan for every working place, installed before exposure."),
            ("Examination of workings", "Roof and sides examined each shift and after blasting."),
            ("Strata monitoring", "Movement monitored where extraction leaves wide spans."),
        ],
    },
    {
        "id": "methane",
        "label": "Methane / firedamp accumulation and ignition",
        "keywords": ["methane", "firedamp", "gas", "gas leak", "gas accumulation", "explosion",
                     "ignition", "ventilation", "degassing", "goaf", "methanometer", "flammable"],
        "drivers": [
            "Inadequate air quantity or short-circuited ventilation at the face",
            "Sudden release from a sealed goaf or geological fault",
            "Open flame, smoking or non-permissible equipment underground",
            "Failure to detect gas before or during work",
        ],
        "controls": [
            "Continuous methane monitoring plus portable checks at face and return",
            "Withdrawal and de-energising above the permitted limit (commonly 1% at the face, 1.25% in the return)",
            "Permitted/flameproof equipment only; no smoking or open flame underground",
            "Written degassing plan with controlled goaf drainage",
        ],
        "statute": "Coal Mines Regulations 2017 (ventilation and gas limits); Mines Act 1952",
        "checks": [
            ("Ventilation", "Prescribed air quantity measured and recorded at every working place."),
            ("Gas limits", "Withdrawal limits enforced with de-energising above the limit."),
            ("Permissible equipment", "Only permitted apparatus in gassy workings, no ignition source."),
        ],
    },
    {
        "id": "coal-dust",
        "label": "Explosive dust / airborne dust",
        "keywords": ["dust", "coal dust", "stone dust", "dust explosion", "airborne", "silica",
                     "particulate", "dust suppression", "water spray"],
        "drivers": [
            "Settled fine dust raised by blasting or machinery",
            "Missing or depleted stone-dust barriers and water troughs",
            "Dry drilling or unsprayed transfer points",
        ],
        "controls": [
            "Stone-dusting to inert roadway dust; barriers and troughs maintained",
            "Water sprays at drilling, loading and transfer points",
            "Regular dust sampling against the applicable standard",
            "Respiratory protection and health surveillance for exposed workers",
        ],
        "statute": "Coal Mines Regulations 2017 (dust); DGMS dust-sampling standards",
        "checks": [
            ("Dust control", "Suppression at transfer points, drilling and loading, with sampling records."),
            ("Stone dusting", "Roadway dust inerted; barriers and troughs replenished."),
        ],
    },
    {
        "id": "machinery",
        "label": "Machinery, haulage and transport",
        "keywords": ["machinery", "machine", "dumper", "tipper", "truck", "haulage", "conveyor",
                     "belt", "winding", "rope", "crane", "vehicle", "crushing", "crusher",
                     "shovel", "excavator", "run over", "entanglement"],
        "drivers": [
            "No segregation between pedestrians and heavy vehicles",
            "Unguarded moving parts or unblocked conveyors run without isolation",
            "Fatigued or unlicensed operators on unchecked haul roads",
            "Winding/haulage rope deterioration beyond discard criteria",
        ],
        "controls": [
            "Traffic management plan with walkways and speed limits",
            "Lock-out/tag-out before maintenance; guards restored before restart",
            "Statutory examination of winding and haulage ropes at prescribed intervals",
            "Operator competence records, fatigue limits and reversing aids",
        ],
        "statute": "Mines Act 1952; Metalliferous Mines Regulations 1961 (machinery and haulage)",
        "checks": [
            ("Machinery guarding", "Moving parts guarded; isolation before maintenance and unblocking."),
            ("Haulage and winding", "Ropes, haulage and winding gear examined at prescribed intervals."),
            ("Transport rules", "Pedestrians separated from vehicles with enforceable speed limits."),
        ],
    },
    {
        "id": "blasting",
        "label": "Explosives and blasting",
        "keywords": ["blasting", "blast", "explosive", "detonator", "misfire", "charges",
                     "shot hole", "stemming", "magazine", "shotfirer"],
        "drivers": [
            "Misfires not accounted for before re-entry",
            "Excessive charge or poor stemming causing fly-rock",
            "Unqualified shotfirer or uncontrolled access to the blast zone",
            "Explosives stored or transported against permit conditions",
        ],
        "controls": [
            "Written blast design with charge limits and a guarded exclusion zone",
            "Misfire procedure with the statutory waiting period before re-entry",
            "Licensed shotfirer and explosives register reconciled after every blast",
            "Magazine security, segregation and approved transport",
        ],
        "statute": "Mines Act 1952; Explosives Act 1884 and rules; MMR 1961 (blasting)",
        "checks": [
            ("Blasting procedure", "Written design, exclusion zone and misfire procedure followed."),
            ("Explosives records", "Register reconciled; magazine security maintained."),
            ("Competent shotfirer", "Only a licensed shotfirer prepares and fires shots."),
        ],
    },
    {
        "id": "inundation",
        "label": "Inundation and flooding",
        "keywords": ["inundation", "flood", "flooding", "water", "pump", "sump", "aquifer",
                     "water inrush", "rainfall", "monsoon", "dam"],
        "drivers": [
            "Approaching old workings or water-bearing strata without a barrier",
            "Pumping capacity exceeded during monsoon inflow",
            "Waterlogged or abandoned workings not surveyed and marked",
        ],
        "controls": [
            "Maintained water barriers and a standing order near suspected water bodies",
            "Adequate sump capacity with standby pumping and power backup",
            "Survey plans updated; probe drilling ahead of the face",
            "Monsoon preparedness checks and surface drainage away from openings",
        ],
        "statute": "Metalliferous Mines Regulations 1961 (water barriers); DGMS monsoon circulars",
        "checks": [
            ("Water barriers", "Barriers maintained against old workings; plans updated."),
            ("Pumping", "Adequate capacity with standby power during monsoon."),
        ],
    },
    {
        "id": "fire",
        "label": "Mine fire and spontaneous heating",
        "keywords": ["fire", "burning", "smoke", "heating", "spontaneous combustion", "smouldering",
                     "sealed off", "hot spot", "carbon monoxide"],
        "drivers": [
            "Spontaneous heating of carbonaceous material in worked-out areas",
            "Electrical short circuit or friction heating on belt conveyors",
            "Welding/cutting without a hot-work permit underground",
        ],
        "controls": [
            "CO and temperature trending to detect heating early",
            "Fire-resistant belting, belt monitoring and adequate fire water",
            "Hot-work permits with fire watch and post-work inspection",
            "Sealing and inertisation plan for inaccessible heated areas",
        ],
        "statute": "Coal Mines Regulations 2017 (fire precautions); DGMS fire circulars",
        "checks": [
            ("Fire precautions", "Fire-fighting equipment, water supply and CO monitoring tested."),
            ("Hot work", "Hot-work permit with fire watch in flammable areas."),
        ],
    },
    {
        "id": "fall-of-person",
        "label": "Fall of person / working at height",
        "keywords": ["fall of person", "fell", "slipped", "ladder", "platform", "scaffold",
                     "height", "stairway", "manhole", "edge protection"],
        "drivers": [
            "Unguarded openings, platforms and ladderways",
            "Slippery or poorly lit walkways",
            "Work at height without a harness or anchor point",
        ],
        "controls": [
            "Guard rails, toe boards and covers over all openings",
            "Fall-arrest harness with inspected anchors above ground level",
            "Adequate illumination and non-slip walkway maintenance",
            "Permit and supervision for work at height",
        ],
        "statute": "Mines Act 1952; Metalliferous Mines Regulations 1961 (ladders and platforms)",
        "checks": [
            ("Openings and platforms", "All openings, platforms and ladderways guarded and maintained."),
            ("Work at height", "Fall-arrest equipment and permits above ground level."),
        ],
    },
    {
        "id": "electrical",
        "label": "Electrical shock and equipment failure",
        "keywords": ["electrical", "electric", "shock", "electrocution", "cable", "earthing",
                     "grounding", "switchgear", "transformer", "overload", "short circuit"],
        "drivers": [
            "Damaged trailing cables and inadequate earthing",
            "Live work without isolation or a permit",
            "Unauthorised modification of protective devices",
        ],
        "controls": [
            "Earthing and earth-leak protection tested on a fixed schedule",
            "Isolation, locking and proving dead before work",
            "Cable routing protected from machinery and falling rock",
            "Competent electrical supervisor with maintenance records",
        ],
        "statute": "Mines Act 1952; Metalliferous Mines Regulations 1961 (electricity)",
        "checks": [
            ("Earthing and protection", "Earth-leak protection and earthing tested and recorded."),
            ("Isolation", "Permit-to-work, locking and proving dead before electrical work."),
        ],
    },
    {
        "id": "health",
        "label": "Occupational health / dust disease",
        "keywords": ["pneumoconiosis", "silicosis", "tuberculosis", "health", "noise", "hearing",
                     "heat stress", "respiratory", "occupational disease", "medical"],
        "drivers": [
            "Long-term exposure to respirable silica or coal dust",
            "Noise above the permitted exposure level without protection",
            "Irregular medical examinations and weak dust control",
        ],
        "controls": [
            "Periodic medical examination including chest radiographs for dust-exposed workers",
            "Dust and noise monitoring with correction at source",
            "Respiratory and hearing protection as the last line of defence",
            "Record keeping and notification of occupational disease",
        ],
        "statute": "Mines Act 1952 (health); DGMS occupational health circulars",
        "checks": [
            ("Medical examination", "Periodic examination for dust-exposed workers, records retained."),
            ("Hygiene monitoring", "Dust and noise monitoring with corrective action at source."),
        ],
    },
]

GENERAL: dict[str, Any] = {
    "id": "general",
    "label": "General mining safety",
    "keywords": [],
    "drivers": [
        "Incomplete hazard identification before the task",
        "Supervision and competence gaps",
        "Safety management system not followed at the workforce level",
    ],
    "controls": [
        "Risk assessment before starting non-routine work",
        "Documented supervision and competence verification",
        "Incident reporting and learning loop closed with the workforce",
    ],
    "statute": "Mines Act 1952; relevant Mines Regulations; DGMS circulars",
    "checks": [
        ("Risk assessment", "Task-level risk assessment before non-routine work."),
        ("Reporting", "Accidents and dangerous occurrences notified to DGMS in time."),
        ("Supervision", "Competent supervision and statutory examinations recorded."),
    ],
}

BY_ID = {hazard["id"]: hazard for hazard in TAXONOMY + [GENERAL]}

_FATAL_RE = re.compile(
    r"\b(fatal|fatality|fatalities|died|death|deaths|killed|toll)\b|(\d+)\s+(persons?|workers?|lives)\b",
    re.IGNORECASE,
)
_HIGH_SEVERITY_HINTS = ("explosion", "collapse", "inundation", "fire", "trapped", "multiple")


def classify(question: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Score the taxonomy against the question and retrieved evidence."""
    question_lower = question.lower()
    evidence = " ".join(doc.get("text", "") for doc in documents)[:12000].lower()
    combined = f"{question_lower} {evidence}"

    best = GENERAL
    best_score = 0
    best_hits: list[str] = []
    best_question_score = 0

    for hazard in TAXONOMY:
        score = 0
        question_score = 0
        hits: list[str] = []
        for keyword in hazard["keywords"]:
            if keyword in question_lower:
                score += 3
                question_score += 3
                hits.append(keyword)
            elif keyword in combined:
                score += 1
                hits.append(keyword)
        if score > best_score:
            best, best_score, best_hits = hazard, score, hits
            best_question_score = question_score

    # A DGMS statistics volume mentions every hazard somewhere, so evidence-only
    # matches produce confident nonsense (e.g. a fatal-accident totals question
    # labelled "machinery"). Only classify a specific hazard when the user's own
    # wording points at it.
    if best_question_score == 0:
        best, best_score, best_hits = GENERAL, 0, []

    severity_score = 0
    signals: list[str] = []
    if _FATAL_RE.search(combined):
        severity_score += 2
        signals.append("Fatalities referenced in the evidence")
    if best["id"] in {"methane", "roof-fall", "inundation", "fire", "coal-dust"}:
        # These mechanisms are life-threatening even before a fatality is recorded.
        severity_score += 2
    if any(hint in combined for hint in _HIGH_SEVERITY_HINTS):
        severity_score += 1
        signals.append("High-energy failure mode mentioned (explosion/collapse/inundation/fire)")
    if "fatal" in question_lower or "accident" in question_lower:
        severity_score += 1

    severity = "High" if severity_score >= 3 else "Medium" if severity_score == 2 else "Low"
    confidence = round(min(0.92, 0.32 + 0.09 * min(len(best_hits), 5) + (0.08 if documents else 0)), 3)

    return {
        "id": best["id"],
        "label": best["label"],
        "severity": severity,
        "confidence": confidence,
        "drivers": best["drivers"][:4],
        "controls": best["controls"][:4],
        "signals": signals + [f"Matched keyword: {hit}" for hit in best_hits[:3]],
        "statute": best["statute"],
        "checks": [{"clause": clause, "requirement": requirement} for clause, requirement in best["checks"]],
    }


def analysis_markdown(hazard: dict[str, Any]) -> str:
    """Format used by `GET /updates`; the alerts screen parses this exact shape."""
    risk = hazard.get("severity", "Low")
    label = hazard.get("label", GENERAL["label"])
    drivers = hazard.get("drivers", [])[:3]
    controls = hazard.get("controls", [])[:3]
    lines = [f"**Risk Level:** {risk}", f"**Hazard Type:** {label}", "**Description:**"]
    if drivers:
        lines.extend(f"{index}. {driver}" for index, driver in enumerate(drivers, start=1))
    if controls:
        lines.append("**Recommended Actions:**")
        lines.extend(f"{index}. {control}" for index, control in enumerate(controls, start=1))
    return "\n".join(lines)
