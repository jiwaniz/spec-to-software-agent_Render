"""
Shared Pydantic schemas for the Spec-to-Software Agent pipeline.

Every agent takes a typed input and returns a typed output built from
these models. Nothing passes between agents as raw text/dict — this is
what keeps the pipeline "structured" rather than "prompts chained together".
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Requirement Agent
# ---------------------------------------------------------------------------

class RequirementOutput(BaseModel):
    in_scope: bool = Field(..., description="False if the request is rejected as out-of-scope")
    rejection_reason: str | None = Field(None, description="Why the request was rejected, if in_scope is False")
    app_name: str = Field(..., description="Short, filesystem-safe app name, e.g. 'expense_tracker'")
    domain: str = Field(..., description="One of the supported domains, e.g. 'Inventory Management'")
    raw_description: str = Field(..., description="The user's original free-text requirement")
    auth_enabled: bool = Field(False, description="Whether the user asked for / toggled JWT auth")


# ---------------------------------------------------------------------------
# Specification Agent
# ---------------------------------------------------------------------------

class FieldDef(BaseModel):
    name: str
    type: Literal["str", "int", "float", "bool", "datetime"]
    required: bool = True
    unique: bool = False
    description: str | None = None


class EntityDef(BaseModel):
    name: str = Field(..., description="Singular PascalCase entity name, e.g. 'Product'")
    table_name: str = Field(..., description="Snake_case plural table name, e.g. 'products'")
    fields: list[FieldDef]


class FunctionalRequirement(BaseModel):
    id: str = Field(..., description="e.g. 'FR-01'")
    description: str
    acceptance_criteria: str


class EndpointDef(BaseModel):
    method: Literal["GET", "POST", "PUT", "DELETE"]
    path: str
    entity: str
    description: str
    fr_ids: list[str] = Field(default_factory=list, description="FR-IDs this endpoint implements")
    protected: bool = False


class SpecOutput(BaseModel):
    app_name: str
    domain: str
    auth_enabled: bool = False
    entities: list[EntityDef]
    endpoints: list[EndpointDef]
    functional_requirements: list[FunctionalRequirement]
    non_functional_requirements: list[str] = Field(default_factory=list)
    validation_rules: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Planning Agent
# ---------------------------------------------------------------------------

class PlanOutput(BaseModel):
    folder_structure: list[str] = Field(..., description="Relative file paths to be generated")
    db_schema_notes: str
    endpoint_summary: list[str]


# ---------------------------------------------------------------------------
# Task Agent
# ---------------------------------------------------------------------------

class TaskItem(BaseModel):
    id: str
    description: str
    depends_on: list[str] = Field(default_factory=list)


class TaskOutput(BaseModel):
    tasks: list[TaskItem]


# ---------------------------------------------------------------------------
# Coding Agent output (files it produced, before writing to disk)
# ---------------------------------------------------------------------------

class GeneratedFile(BaseModel):
    path: str
    content: str


class CodingOutput(BaseModel):
    files: list[GeneratedFile]


# ---------------------------------------------------------------------------
# Validation Agent
# ---------------------------------------------------------------------------

class ValidationReport(BaseModel):
    files_ok: bool
    syntax_errors: list[str] = Field(default_factory=list)
    endpoints_detected: int
    endpoints_required: int
    tests_passed: int
    tests_total: int
    failed_test_names: list[str] = Field(default_factory=list)
    requirement_coverage_pct: float
    avg_embedding_similarity: float | None = None
    correction_cycles_used: int = 0
    overall_status: Literal["PASS", "PARTIAL", "FAIL"]


# ---------------------------------------------------------------------------
# Refinement Agent (Day 7)
# ---------------------------------------------------------------------------

class RefinementPatch(BaseModel):
    add_fields: dict[str, list[FieldDef]] = Field(default_factory=dict, description="entity_name -> new fields")
    remove_fields: dict[str, list[str]] = Field(default_factory=dict, description="entity_name -> field names")
    rename_entities: dict[str, str] = Field(default_factory=dict, description="old_name -> new_name")
    add_endpoints: list[EndpointDef] = Field(default_factory=list)
    notes: str = Field("", description="Plain-language summary of what changed, shown back to the user")
