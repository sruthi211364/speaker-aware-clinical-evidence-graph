from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import AttestationAction, NoteStatus, SoapSection


class SoapNoteLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    note_id: uuid.UUID
    section: SoapSection
    position: int
    text: str
    is_conflict: bool
    is_rejected: bool
    claim_ids: list[uuid.UUID]

    @staticmethod
    def from_line(line) -> "SoapNoteLineRead":
        return SoapNoteLineRead(
            id=line.id,
            note_id=line.note_id,
            section=line.section,
            position=line.position,
            text=line.text,
            is_conflict=line.is_conflict,
            is_rejected=line.is_rejected,
            claim_ids=[link.claim_id for link in line.claim_links],
        )


class SoapNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    encounter_id: uuid.UUID
    version: int
    status: NoteStatus
    signed_by: uuid.UUID | None
    signed_at: dt.datetime | None
    created_at: dt.datetime
    lines: list[SoapNoteLineRead]

    @staticmethod
    def from_note(note) -> "SoapNoteRead":
        ordered_lines = sorted(note.lines, key=lambda line: (line.section.value, line.position))
        return SoapNoteRead(
            id=note.id,
            encounter_id=note.encounter_id,
            version=note.version,
            status=note.status,
            signed_by=note.signed_by,
            signed_at=note.signed_at,
            created_at=note.created_at,
            lines=[SoapNoteLineRead.from_line(line) for line in ordered_lines],
        )


class SoapNoteLineEditRequest(BaseModel):
    text: str


class AttestationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    encounter_id: uuid.UUID
    note_version_id: uuid.UUID | None
    note_line_id: uuid.UUID | None
    claim_id: uuid.UUID | None
    actor_id: uuid.UUID
    action: AttestationAction
    before_value: str | None
    after_value: str | None
    created_at: dt.datetime
