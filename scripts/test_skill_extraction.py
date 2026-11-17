from pathlib import Path

from dotenv import load_dotenv

from backend.app.services.gemini_service import (
    extract_job_analysis,
)


ROOT = Path(__file__).resolve().parents[1]

load_dotenv(ROOT / ".env")


def main():

    description = """
    We are looking for a Python Backend Developer.

    Requirements:
    - Strong experience with Python.
    - Experience building REST APIs using FastAPI.
    - Knowledge of PostgreSQL databases.
    - Experience working with Docker.
    - Familiarity with AWS cloud services is preferred.
    """

    print("=" * 55)
    print("ROLERADAR AI - GEMINI SKILL EXTRACTION TEST")
    print("=" * 55)

    result = extract_job_analysis(
        title="Python Backend Developer",
        company="Example Technology",
        description=description,
    )

    print("\nROLE CATEGORY:")
    print(result.role_category)

    print("\nSENIORITY:")
    print(result.seniority)

    print("\nSUMMARY:")
    print(result.summary)

    print("\nEXTRACTED SKILLS:")

    for skill in result.skills:

        print(
            f"\nName: {skill.name}"
            f"\nCategory: {skill.category}"
            f"\nRequirement: {skill.requirement}"
            f"\nEvidence: {skill.evidence}"
        )

    print("\nTOTAL SKILLS:", len(result.skills))

    print("\nGEMINI SKILL EXTRACTION SUCCESSFUL")


if __name__ == "__main__":
    main()
