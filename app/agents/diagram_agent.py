"""Diagram Agent -- deterministic Mermaid ER diagram from the spec. No LLM call."""

from app.schemas import SpecOutput

_TYPE_MAP = {"str": "string", "int": "int", "float": "float", "bool": "bool", "datetime": "datetime"}


def generate_er_diagram(spec: SpecOutput) -> str:
    lines = ["erDiagram"]
    for entity in spec.entities:
        lines.append(f"    {entity.name} {{")
        lines.append(f"        int id PK")
        for f in entity.fields:
            fk_suffix = " FK" if f.name.endswith("_id") else ""
            lines.append(f"        {_TYPE_MAP.get(f.type, 'string')} {f.name}{fk_suffix}")
        lines.append("    }")

    entity_names = {e.name.lower() for e in spec.entities}
    for entity in spec.entities:
        for f in entity.fields:
            if f.name.endswith("_id"):
                target = f.name[:-3]
                if target in entity_names:
                    target_name = next(e.name for e in spec.entities if e.name.lower() == target)
                    lines.append(f'    {target_name} ||--o{{ {entity.name} : "has"')

    return "\n".join(lines)


def run_diagram_agent(spec: SpecOutput) -> str:
    return generate_er_diagram(spec)


if __name__ == "__main__":
    from app.rag.example_bank import EXAMPLE_BANK
    print(run_diagram_agent(EXAMPLE_BANK[0]))
