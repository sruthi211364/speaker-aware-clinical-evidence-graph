"""Seeds the terminology normalization index: a small, curated subset of
RxNorm, SNOMED CT, and LOINC codes covering this prototype's demo scenarios.

This is NOT a full vocabulary download -- RxNorm/SNOMED CT/LOINC are large,
licensed terminologies unsuitable for bundling into a portfolio prototype.
The codes below are well-known, commonly cited concept IDs (the kind that
appear throughout public FHIR examples and clinical terminology tutorials);
verify against an authoritative UMLS/NLM/SNOMED International source before
any real clinical use.

Usage: python -m app.seed_vocabulary
"""

from app.db import SessionLocal
from app.models import VocabularyTerm
from app.services.embedding_service import embed_texts

# (code_system, code, display)
VOCABULARY_TERMS = [
    # RxNorm -- medication ingredients
    ("RxNorm", "723", "Amoxicillin"),
    ("RxNorm", "7980", "Penicillin G"),
    ("RxNorm", "5640", "Ibuprofen"),
    ("RxNorm", "7258", "Naproxen"),
    ("RxNorm", "1191", "Aspirin"),
    ("RxNorm", "6918", "Metoprolol"),
    ("RxNorm", "855288", "Amoxicillin and clavulanate potassium"),
    # SNOMED CT -- conditions / findings
    ("SNOMED", "29857009", "Chest pain"),
    ("SNOMED", "25064002", "Headache"),
    ("SNOMED", "267036007", "Dyspnea (shortness of breath)"),
    ("SNOMED", "91936005", "Allergy to penicillin"),
    ("SNOMED", "38341003", "Hypertensive disorder"),
    ("SNOMED", "73211009", "Diabetes mellitus"),
    ("SNOMED", "195967001", "Asthma"),
    ("SNOMED", "271807003", "Skin rash"),
    ("SNOMED", "422587007", "Nausea"),
    # LOINC -- observations / vitals
    ("LOINC", "8480-6", "Systolic blood pressure"),
    ("LOINC", "8462-4", "Diastolic blood pressure"),
    ("LOINC", "8867-4", "Heart rate"),
    ("LOINC", "9279-1", "Respiratory rate"),
    ("LOINC", "8310-5", "Body temperature"),
    ("LOINC", "29463-7", "Body weight"),
]


def run() -> None:
    db = SessionLocal()
    try:
        if db.query(VocabularyTerm).first():
            print("Vocabulary index already seeded, skipping.")
            return

        embeddings = embed_texts([display for _, _, display in VOCABULARY_TERMS])
        for (code_system, code, display), vec in zip(VOCABULARY_TERMS, embeddings):
            db.add(VocabularyTerm(code_system=code_system, code=code, display=display, embedding=vec))

        db.commit()
        print(f"Seeded {len(VOCABULARY_TERMS)} vocabulary terms.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
