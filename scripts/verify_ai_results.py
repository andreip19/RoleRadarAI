from sqlalchemy import func, select

from backend.app.db.session import SessionLocal, engine
from backend.app.models.job import Job
from backend.app.models.skill import Skill
from backend.app.models.job_skill import JobSkill
from backend.app.models.job_analysis import JobAnalysis


SAMPLE_JOB_IDS = [1124, 1125, 1123, 1114, 1119]


def main():
    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "Verification requires PostgreSQL."
        )

    with SessionLocal() as db:
        print("=" * 75)
        print("ROLERADAR AI - VERIFICARE SALVARE AI")
        print("=" * 75)
        print("Database: PostgreSQL")
        print("Mode: READ-ONLY - fara modificari")

        total_jobs = db.scalar(
            select(func.count()).select_from(Job)
        )

        total_analyses = db.scalar(
            select(func.count()).select_from(JobAnalysis)
        )

        total_skills = db.scalar(
            select(func.count()).select_from(Skill)
        )

        total_associations = db.scalar(
            select(func.count()).select_from(JobSkill)
        )

        print("\nTOTALURI IN BAZA DE DATE:")
        print(f"Joburi: {total_jobs}")
        print(f"Analize AI: {total_analyses}")
        print(f"Competente unice: {total_skills}")
        print(f"Asocieri job-competență: {total_associations}")

        jobs = db.scalars(
            select(Job)
            .where(Job.id.in_(SAMPLE_JOB_IDS))
            .order_by(Job.id)
        ).all()

        analyses = db.scalars(
            select(JobAnalysis).where(
                JobAnalysis.job_id.in_(SAMPLE_JOB_IDS)
            )
        ).all()

        analysis_by_job = {
            analysis.job_id: analysis
            for analysis in analyses
        }

        association_counts = dict(
            db.execute(
                select(
                    JobSkill.job_id,
                    func.count(JobSkill.skill_id),
                )
                .where(JobSkill.job_id.in_(SAMPLE_JOB_IDS))
                .group_by(JobSkill.job_id)
            ).all()
        )

        print("\nVERIFICARE PE FIECARE JOB:")
        print("-" * 75)

        successful = 0

        for job in jobs:
            analysis = analysis_by_job.get(job.id)
            skill_count = association_counts.get(job.id, 0)

            valid = (
                analysis is not None
                and analysis.status == "success"
                and analysis.result_json is not None
                and skill_count >= 0
            )

            print(f"\nID: {job.id}")
            print(f"Titlu: {job.title}")
            print(f"Companie: {job.company}")

            if analysis:
                print(f"Status analiza: {analysis.status}")
                print(f"Model: {analysis.model_name}")
                print(f"Categorie: {analysis.category}")
                print(f"Senioritate: {analysis.seniority}")
                print(f"Data analizarii: {analysis.analyzed_at}")
                print(
                    "Rezultat JSON: "
                    + ("prezent" if analysis.result_json else "LIPSA")
                )
            else:
                print("ANALIZA LIPSESTE")

            print(f"Competente asociate: {skill_count}")
            print(f"Verificare: {'OK' if valid else 'EROARE'}")

            if valid:
                successful += 1

        print("\nCOMPETENTELE SALVATE:")
        print("-" * 75)

        rows = db.execute(
            select(
                JobSkill.job_id,
                Skill.name,
                Skill.category,
                JobSkill.requirement,
            )
            .join(Skill, Skill.id == JobSkill.skill_id)
            .where(JobSkill.job_id.in_(SAMPLE_JOB_IDS))
            .order_by(JobSkill.job_id, Skill.name)
        ).all()

        for job_id, name, category, requirement in rows:
            print(
                f"Job {job_id} | {name} | "
                f"{category} | {requirement}"
            )

        print("\n" + "=" * 75)
        print("REZUMAT VERIFICARE")
        print("=" * 75)
        print(f"Joburi verificate: {successful}/5")
        print(f"Asocieri verificate: {len(rows)}")

        if successful == 5:
            print("STATUS: TOATE CELE CINCI ANALIZE SUNT SALVATE.")
        else:
            print("STATUS: EXISTA ANALIZE CARE TREBUIE INVESTIGATE.")

        print("Nu au fost efectuate modificari in baza de date.")
        print("=" * 75)


if __name__ == "__main__":
    main()
