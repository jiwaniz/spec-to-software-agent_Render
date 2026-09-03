"""
Refinement Agent -- Day 7.

Takes a follow-up message ("add an email field to Customer") plus the
current spec, returns a RefinementPatch, and applies it deterministically
to produce an updated SpecOutput. Downstream (Planning->Coding->Testing->
Validation->Diagram) then re-runs only against the patched spec -- not a
full restart from the Requirement Agent.
"""

from app.schemas import SpecOutput, RefinementPatch, EntityDef, FieldDef
from app.agents.llm_json import call_llm_for_json

SYSTEM_PROMPT = """You are the Refinement Agent in a spec-driven FastAPI generator.

Given the CURRENT spec and a user's follow-up request, output a minimal patch.
Only include what the user actually asked to change. Entity names in
add_fields/remove_fields/rename_entities must match existing entities exactly.

Return JSON matching:
{
  "add_fields": {"EntityName": [{"name": str, "type": "str"|"int"|"float"|"bool"|"datetime",
                                   "required": bool, "unique": bool, "description": null}]},
  "remove_fields": {"EntityName": [field_name, ...]},
  "rename_entities": {"OldName": "NewName"},
  "add_endpoints": [],
  "notes": "one plain-English sentence describing what changed"
}
Omit keys with nothing to change (use empty dict/list), never omit "notes".
"""


def run_refinement_agent(spec: SpecOutput, message: str) -> RefinementPatch:
    user_prompt = f"Current spec entities:\n{[e.name for e in spec.entities]}\n\nUser request: {message}"
    return call_llm_for_json(SYSTEM_PROMPT, user_prompt, RefinementPatch)  # type: ignore[return-value]


def apply_patch(spec: SpecOutput, patch: RefinementPatch) -> SpecOutput:
    new_spec = spec.model_copy(deep=True)

    for entity_name, fields in patch.add_fields.items():
        entity = next((e for e in new_spec.entities if e.name == entity_name), None)
        if entity:
            existing = {f.name for f in entity.fields}
            entity.fields.extend(f for f in fields if f.name not in existing)

    for entity_name, field_names in patch.remove_fields.items():
        entity = next((e for e in new_spec.entities if e.name == entity_name), None)
        if entity:
            entity.fields = [f for f in entity.fields if f.name not in field_names]

    for old_name, new_name in patch.rename_entities.items():
        entity = next((e for e in new_spec.entities if e.name == old_name), None)
        if entity:
            entity.name = new_name
            for ep in new_spec.endpoints:
                if ep.entity == old_name:
                    ep.entity = new_name

    new_spec.endpoints.extend(patch.add_endpoints)
    return new_spec


if __name__ == "__main__":
    from app.rag.example_bank import EXAMPLE_BANK
    spec = EXAMPLE_BANK[0]
    patch = run_refinement_agent(spec, "add an email field to Category")
    print(patch.model_dump_json(indent=2))
    updated = apply_patch(spec, patch)
    print([f.name for f in updated.entities[0].fields])
