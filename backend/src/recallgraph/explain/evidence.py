"""Evidence packs: the ONLY facts an explanation may use, each with a citable id (E1, E2...)."""

from dataclasses import dataclass

from recallgraph.search.service import RecallDetail


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    id: str
    kind: str
    text: str


def build_evidence(detail: RecallDetail, max_chars: int = 600) -> list[EvidenceItem]:
    r = detail.recall
    facts: list[tuple[str, str]] = [
        ("title", r.title),
        ("source", f"{detail.source.agency}; record {r.source_record_id}; {detail.raw.source_url}"),
    ]
    if r.recall_date:
        facts.append(("date", f"Recall date {r.recall_date.isoformat()}"))
    if r.description:
        facts.append(("description", r.description))
    facts += [
        ("product", f"{p.name}" + (f" (model {p.model})" if p.model else "")) for p in r.products
    ]
    facts += [("hazard", h.description) for h in r.hazards]
    facts += [("remedy", m.description) for m in r.remedies]
    if r.identifiers:
        facts.append(("identifiers", ", ".join(sorted({i.value for i in r.identifiers}))))
    if r.consumer_contact:
        facts.append(("contact", r.consumer_contact))
    return [
        EvidenceItem(id=f"E{n}", kind=kind, text=text[:max_chars])
        for n, (kind, text) in enumerate(facts, 1)
        if text
    ]
