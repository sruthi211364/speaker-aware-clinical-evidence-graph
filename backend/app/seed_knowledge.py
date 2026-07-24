"""Seeds the two RAG indexes: a clinical knowledge corpus (guideline
snippets, drug interaction facts, per-symptom documentation requirements)
and a longitudinal patient history corpus (prior encounter notes for the
demo patient). Both are embedded locally via app.services.embedding_service.

Usage: python -m app.seed_knowledge
"""

from app.db import SessionLocal
from app.models import ClinicalKnowledgeChunk, PatientHistoryChunk, User
from app.services.embedding_service import embed_texts

# (source_identifier, title, content, category)
# category is "documentation_standard" or "drug_interaction" -- it drives
# whether a retrieval hit becomes a GroundingCitation tagged `guideline` or
# `drug_data`, which Phase 5's clinical safety check depends on.
CLINICAL_KNOWLEDGE = [
    (
        "chest_pain_documentation_standard",
        "Chest pain documentation requirements",
        "Chest pain documentation should include severity (using a 0-10 scale or "
        "mild/moderate/severe), radiation (whether it spreads to the arm, jaw, neck, "
        "or back), associated symptoms (shortness of breath, diaphoresis, nausea, "
        "palpitations), and any relationship to exertion or rest.",
        "documentation_standard",
    ),
    (
        "headache_documentation_standard",
        "Headache documentation requirements",
        "Headache documentation should include onset (sudden vs. gradual), location, "
        "quality, duration, associated neurological symptoms (vision changes, "
        "weakness, numbness), and any history of similar episodes.",
        "documentation_standard",
    ),
    (
        "shortness_of_breath_documentation_standard",
        "Shortness of breath documentation requirements",
        "Shortness of breath documentation should include onset, whether it occurs "
        "at rest or with exertion, associated chest pain, and exercise tolerance "
        "(e.g. distance walked before symptoms occur).",
        "documentation_standard",
    ),
    (
        "penicillin_allergy_cross_reactivity",
        "Penicillin allergy and cephalosporin cross-reactivity",
        "Patients with a documented penicillin allergy should avoid amoxicillin, "
        "ampicillin, and other penicillin-class antibiotics. Cephalosporins carry an "
        "estimated 1-10% cross-reactivity risk in penicillin-allergic patients and "
        "should be prescribed cautiously, with a preference for third-generation "
        "agents when a cephalosporin is necessary.",
        "drug_interaction",
    ),
    (
        "nsaid_gi_bleed_anticoagulant_risk",
        "NSAID risk with anticoagulants or GI bleed history",
        "NSAIDs such as ibuprofen and naproxen increase gastrointestinal bleeding "
        "risk and should be avoided or used with caution in patients on "
        "anticoagulant therapy (e.g. warfarin, apixaban) or with a history of GI "
        "bleeding or peptic ulcer disease.",
        "drug_interaction",
    ),
    (
        "chest_pain_cardiac_risk_screening",
        "Cardiac risk screening for new chest pain",
        "Any new chest pain in a patient over 40 should prompt screening for "
        "cardiac risk factors including hypertension, diabetes, smoking history, "
        "hyperlipidemia, and family history of premature coronary artery disease.",
        "documentation_standard",
    ),
    (
        "beta_blocker_asthma_caution",
        "Beta blocker caution in reactive airway disease",
        "Non-selective beta blockers can worsen bronchospasm and should be used "
        "cautiously, or avoided, in patients with a history of asthma or reactive "
        "airway disease.",
        "drug_interaction",
    ),
]

PATIENT_HISTORY = [
    (
        "prior visit 2026-04-02",
        "At a visit on 2026-04-02, the patient described brief episodes of chest "
        "tightness lasting only a few seconds, occurring intermittently and unrelated "
        "to exertion, which resolved on their own without treatment.",
    ),
    (
        "prior visit 2025-11-14",
        "At a visit on 2025-11-14, the patient reported no chest pain or cardiac "
        "symptoms. Review of systems was negative for chest pain, palpitations, or "
        "shortness of breath.",
    ),
]


def run() -> None:
    """Each corpus is seeded and checked for idempotency independently, so
    re-running after only one of the two was populated (e.g. during a schema
    migration) doesn't skip the other or duplicate it."""
    db = SessionLocal()
    try:
        knowledge_seeded = 0
        if not db.query(ClinicalKnowledgeChunk).first():
            knowledge_embeddings = embed_texts([content for _, _, content, _ in CLINICAL_KNOWLEDGE])
            for (source_id, title, content, category), vec in zip(CLINICAL_KNOWLEDGE, knowledge_embeddings):
                db.add(
                    ClinicalKnowledgeChunk(
                        source_identifier=source_id,
                        title=title,
                        content=content,
                        category=category,
                        embedding=vec,
                    )
                )
            knowledge_seeded = len(CLINICAL_KNOWLEDGE)

        demo_patient = db.query(User).filter_by(email="demo.patient@example.com").first()
        if demo_patient is None:
            demo_patient = User(
                display_name="Demo Patient", role="patient", email="demo.patient@example.com"
            )
            db.add(demo_patient)
            db.flush()

        history_seeded = 0
        if not db.query(PatientHistoryChunk).filter_by(patient_id=demo_patient.id).first():
            history_embeddings = embed_texts([content for _, content in PATIENT_HISTORY])
            for (label, content), vec in zip(PATIENT_HISTORY, history_embeddings):
                db.add(
                    PatientHistoryChunk(
                        patient_id=demo_patient.id,
                        source_encounter_label=label,
                        content=content,
                        embedding=vec,
                    )
                )
            history_seeded = len(PATIENT_HISTORY)

        if knowledge_seeded == 0 and history_seeded == 0:
            print("Knowledge base already seeded, skipping.")
            return

        db.commit()
        print(f"Seeded {knowledge_seeded} clinical knowledge chunks and {history_seeded} patient history chunks.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
