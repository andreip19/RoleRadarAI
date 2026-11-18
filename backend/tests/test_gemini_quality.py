from typing import get_args

import pytest

from backend.app.schemas.ai import ExtractedSkill, JobAnalysisResult, RoleCategory
from backend.app.services.gemini_service import (
    GEMINI_RESPONSE_SCHEMA,
    ROLE_CATEGORIES,
    build_analysis_prompt,
    classify_requirement,
    classify_role_category,
    is_company_profile_evidence,
    is_generic_skill_name,
    infer_title_seniority,
    infer_description_seniority,
    normalize_text,
    skill_name_supported_by_evidence,
)
from backend.app.models.skill import Skill
from backend.app.services.skill_extraction_service import (
    _find_legacy_skill_match,
    PIPELINE_VERSION,
    canonicalize_skill,
    normalize_skill_name,
)


@pytest.mark.parametrize(
    "name",
    ["CI/CD", "CI-CD", "CI CD", "CI.CD"],
)
def test_skill_normalization_collapses_formatting_variants(name):
    assert normalize_skill_name(name) == "cicd"


def test_skill_normalization_preserves_distinct_technical_names():
    assert normalize_skill_name("Git") != normalize_skill_name("GitLab")
    assert normalize_skill_name("C") != normalize_skill_name("C++")
    assert normalize_skill_name("C") != normalize_skill_name("C#")


def test_skill_normalization_handles_unicode_and_case():
    full_width_git = "\uFF27\uFF29\uFF34"
    mixed_width_git = "\uFF27\uFF49\uFF54"

    assert normalize_skill_name(f"  {full_width_git}  ") == "git"
    assert normalize_text(f"  {mixed_width_git}   LAB  ") == "git lab"

def test_csv_is_expanded_only_with_explicit_context():
    assert canonicalize_skill(
        "CSV",
        "Experience in Computer Software Validation (CSV) processes.",
    ) == "Computer Software Validation"


def test_csv_is_not_expanded_without_explicit_context():
    assert canonicalize_skill(
        "CSV",
        "Export data to a CSV file.",
    ) == "CSV"


def test_duplicate_skills_keep_the_strongest_requirement():
    mentioned = ExtractedSkill(
        name="CI/CD",
        category="devops",
        requirement="mentioned",
        evidence="CI/CD is part of the engineering environment.",
    )

    required = ExtractedSkill(
        name="CI-CD",
        category="devops",
        requirement="required",
        evidence="CI-CD experience is required.",
    )

    analysis = JobAnalysisResult(
        role_category="devops",
        seniority="unknown",
        summary="A role involving deployment and automation.",
        skills=[mentioned, required],
    )

    assert len(analysis.skills) == 1
    assert analysis.skills[0].requirement == "required"
    assert analysis.skills[0].name == "CI-CD"


def test_duplicate_skills_prefer_more_specific_evidence_when_level_matches():
    broad = ExtractedSkill(
        name="Git",
        category="tool",
        requirement="required",
        evidence="Candidates should have experience with Git and other tools.",
    )

    specific = ExtractedSkill(
        name="git",
        category="tool",
        requirement="required",
        evidence="Experience with Git is required.",
    )

    analysis = JobAnalysisResult(
        role_category="software_engineering",
        seniority="unknown",
        summary="A software engineering role requiring version control.",
        skills=[broad, specific],
    )

    assert len(analysis.skills) == 1
    assert analysis.skills[0].evidence == "Experience with Git is required."


def test_gemini_schema_limits_the_number_of_skills():
    assert GEMINI_RESPONSE_SCHEMA["properties"]["skills"]["maxItems"] == 30


def test_prompt_distinguishes_employer_training_from_prior_experience():
    prompt = build_analysis_prompt(
        title="Business Development Representative",
        company="Example Company",
        description="You will be provided with training on the platform.",
    )

    normalized_prompt = " ".join(prompt.split())

    assert "TRAINING VERSUS PRIOR EXPERIENCE" in normalized_prompt
    assert "classify it as mentioned unless" in normalized_prompt
    assert "must already possess" in normalized_prompt

def test_prompt_uses_conservative_seniority_classification():
    prompt = build_analysis_prompt(
        title="Product Manager",
        company="Example Company",
        description="Work with engineering and design teams.",
    )

    assert "Product Manager" in prompt
    assert "Solutions Architect" in prompt
    assert "Never default to mid or senior" in prompt
    assert "unknown" in prompt


def test_prompt_distinguishes_sales_and_customer_success_roles():
    prompt = build_analysis_prompt(
        title="Business Development Representative",
        company="Example Company",
        description="Generate and qualify new leads.",
    )

    assert "sales" in prompt
    assert "customer_success" in prompt
    assert "customer adoption and retention" in prompt


def test_legacy_skill_match_uses_display_name_normalization():
    legacy_skill = Skill(
        name="CI/CD",
        normalized_name="ci/cd",
        category="devops",
    )

    match = _find_legacy_skill_match(
        [legacy_skill],
        "cicd",
    )

    assert match is legacy_skill


def test_role_categories_match_gemini_and_pydantic_schema():
    assert tuple(ROLE_CATEGORIES) == get_args(RoleCategory)
    assert "technical_writing" in ROLE_CATEGORIES


def test_staff_technical_writer_has_dedicated_category_guidance():
    prompt = build_analysis_prompt(
        title="Staff Technical Writer",
        company="Example Company",
        description="Own and maintain technical documentation.",
    )

    assert "technical_writing" in ROLE_CATEGORIES
    assert "Staff Technical Writer" in prompt


def test_company_product_positioning_is_rejected_as_skill_evidence():
    evidence = (
        "GitLab is the intelligent orchestration platform for DevSecOps."
    )

    assert is_company_profile_evidence(evidence)
    assert not is_company_profile_evidence(
        "Hands-on experience with Git and CI/CD pipelines is required."
    )


@pytest.mark.parametrize(
    "evidence",
    [
        "Ostro is dedicated to advancing brand engagement through AI technology.",
        "By joining the division, you will work at the forefront of leveraging AI innovations.",
    ],
)
def test_division_and_product_promotion_is_company_profile_evidence(evidence):
    assert is_company_profile_evidence(evidence)


def test_real_ai_responsibilities_are_not_company_profile_evidence():
    assert not is_company_profile_evidence(
        "Responsibilities include designing and building AI agents for clinical workflows."
    )


def test_product_claims_about_ai_are_not_candidate_expertise():
    evidence = "Our AI platform provides deep expertise in AI to customers."
    assert is_company_profile_evidence(evidence)
    assert classify_requirement(evidence, "required", "AI") == "mentioned"
    assert classify_requirement(
        "Our product uses AI to improve customer engagement.",
        "mentioned",
        "AI",
    ) == "mentioned"


def test_oidc_and_openid_connect_are_explicit_evidence_aliases():
    assert skill_name_supported_by_evidence(
        "OpenID Connect",
        "Implement authentication using OIDC.",
    )
    assert skill_name_supported_by_evidence(
        "OIDC",
        "Implement authentication using OpenID Connect.",
    )
    assert not skill_name_supported_by_evidence(
        "OpenID Connect",
        "Implement authentication using OAuth.",
    )


def test_pipeline_version_is_v9():
    assert PIPELINE_VERSION == "9"


def test_generic_clinical_trial_software_is_not_a_standalone_skill():
    assert is_generic_skill_name("Clinical trial software")
    assert not is_generic_skill_name("RTSM")
    assert not is_generic_skill_name("Salesforce")


def test_rtsm_full_name_is_canonicalized_only_with_explicit_acronym():
    assert canonicalize_skill(
        "Randomization and Trial Supply Management",
        "Randomization and Trial Supply Management (RTSM) software.",
    ) == "RTSM"

    assert canonicalize_skill(
        "Randomization and Trial Supply Management",
        "Experience in randomization and trial supply management.",
    ) == "Randomization and Trial Supply Management"


def test_explicit_senior_title_overrides_responsibility_language():
    assert infer_title_seniority(
        "Senior Candidate Experience Specialist, APJ"
    ) == "senior"


def test_staff_title_maps_to_senior():
    assert infer_title_seniority("Staff Technical Writer") == "senior"


def test_lead_generation_is_not_a_seniority_level():
    assert infer_title_seniority(
        "Lead Generation Specialist"
    ) is None
    assert infer_title_seniority(
        "Lead Generation Representative"
    ) is None


def test_explicit_lead_title_maps_to_lead():
    assert infer_title_seniority(
        "Lead Software Engineer"
    ) == "lead"

    assert infer_title_seniority(
        "Engineering Team Lead"
    ) == "lead"


@pytest.mark.parametrize(
    "title",
    [
        "Global Data Science Lead",
        "Engineering Lead",
        "Technical Lead",
        "Engineering Team Lead",
    ],
)
def test_functional_lead_titles_at_the_end_map_to_lead(title):
    assert infer_title_seniority(title) == "lead"


def test_lead_at_title_start_maps_to_lead():
    assert infer_title_seniority("Lead Software Engineer") == "lead"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Vice President of Marketing", "executive"),
        ("Director of Data Science", "director"),
        ("Principal Engineer", "principal"),
        ("Engineering Manager", "manager"),
        ("Senior Software Engineer", "senior"),
        ("Junior Software Engineer", "junior"),
        ("Mid Level Analyst", "mid"),
        ("Software Engineering Intern", "intern"),
        ("Product Manager", None),
    ],
)
def test_existing_seniority_levels_remain_unchanged(title, expected):
    assert infer_title_seniority(title) == expected


def test_title_without_explicit_seniority_remains_unclassified():
    assert infer_title_seniority(
        "Solutions Architect - Federal"
    ) is None

    assert infer_title_seniority(
        "Product Manager"
    ) is None


def test_prompt_uses_qualification_section_context():
    prompt = build_analysis_prompt(
        title="Solutions Architect",
        company="Example Company",
        description="Familiarity with security frameworks.",
    )

    assert "QUALIFICATION SECTION CONTEXT" in prompt
    assert "What you'll bring" in prompt
    assert "familiarity, working knowledge and proficiency" in prompt
    assert "plus, but not a requirement" in prompt


def test_prompt_covers_technical_writing_hard_skills():
    prompt = build_analysis_prompt(
        title="Staff Technical Writer",
        company="Example Company",
        description="Create software documentation.",
    )

    assert "ROLE-SPECIFIC HARD SKILL GUIDANCE" in prompt
    assert "Docs-as-code workflows" in prompt
    assert "information architecture" in prompt
    assert "AI-output evaluation" in prompt


@pytest.mark.parametrize(
    "phrase",
    ["Helpful, not required", "Beneficial but not required"],
)
def test_explicit_not_required_phrases_are_preferred(phrase):
    assert classify_requirement(
        f"Familiarity with DevSecOps is {phrase.lower()}.", "required"
    ) == "preferred"


def test_employer_training_does_not_establish_prior_requirement():
    assert classify_requirement(
        "You will be provided with training on GitLab.", "required"
    ) == "mentioned"


def test_explicit_qualification_level_is_not_downgraded():
    assert classify_requirement(
        "What you'll bring: working knowledge of Linux shell.", "required"
    ) == "required"


def test_rtsm_opportunity_language_does_not_require_prior_experience():
    assert classify_requirement(
        "Opportunity to work on an RTSM solution.", "mentioned"
    ) == "mentioned"


def test_csv_full_name_alias_canonicalizes_only_when_linked():
    assert canonicalize_skill(
        "Computer Software Validation",
        "Computer Software Validation (CSV) processes.",
    ) == "Computer Software Validation"


def test_rtsm_acronym_is_canonical_when_full_name_is_in_evidence():
    assert canonicalize_skill(
        "RTSM",
        "Randomization and Trial Supply Management (RTSM) software.",
    ) == "RTSM"


def test_prompt_covers_exact_hard_skill_gaps():
    prompt = build_analysis_prompt(
        "Staff Technical Writer",
        "UX and content design skills; hands-on work with Git and CI/CD pipelines and containers.",
    )
    assert "UX and content design skills" in prompt
    assert "do not infer UX" in prompt
    assert "containers in phrases" in prompt
    assert "Do not infer products such as GitLab or DevSecOps" in prompt


@pytest.mark.parametrize(
    "title",
    [
        "Validation Analyst - RTSM",
        "Software Validation Analyst",
        "Software Validation Specialist",
    ],
)
def test_validation_titles_map_to_quality_assurance(title):
    assert classify_role_category(title, "technical_writing") == "quality_assurance"


def test_technical_writer_primary_function_keeps_technical_writing_category():
    assert classify_role_category("Staff Technical Writer", "technical_writing") == "technical_writing"


def test_business_development_representative_has_no_inferred_seniority():
    assert infer_title_seniority(
        "Business Development Representative, Financial Services - UKI"
    ) is None
    assert infer_description_seniority("Lead projects and manage stakeholders.") is None


@pytest.mark.parametrize("title", ["Senior Candidate Experience Specialist", "Staff Technical Writer"])
def test_explicit_senior_and_staff_titles_remain_senior(title):
    assert infer_title_seniority(title) == "senior"


def test_rtsm_exposure_is_mentioned_but_explicit_prior_experience_is_required():
    assert classify_requirement(
        "Opportunity to work on a leading solution in Randomization and Trial Supply Management (RTSM) software.",
        "required",
    ) == "mentioned"
    assert classify_requirement(
        "Previous RTSM experience is required.", "mentioned"
    ) == "required"


@pytest.mark.parametrize("phrase", ["preferred", "nice to have", "a plus"])
def test_explicit_preferred_qualification_stays_preferred(phrase):
    assert classify_requirement(
        f"Previous RTSM experience is {phrase}.", "required"
    ) == "preferred"


@pytest.mark.parametrize(
    "phrase",
    [
        "expert in the use of AI",
        "expertise in AI",
        "deep expertise in AI",
        "extensive experience with AI",
        "strong expertise in AI",
    ],
)
def test_explicit_expertise_language_is_required(phrase):
    assert classify_requirement(
        f"We are looking for someone with {phrase} to build AI agents.",
        "mentioned",
        "AI",
    ) == "required"


def test_explicit_preference_overrides_expertise_language():
    assert classify_requirement(
        "Expertise in AI is preferred.",
        "required",
        "AI",
    ) == "preferred"


@pytest.mark.parametrize(
    ("evidence", "skill"),
    [
        ("Ability to use scripting languages (preferably Ruby or Bash)", "Ruby"),
        ("Ability to use scripting languages (preferably Ruby or Bash)", "Bash"),
        ("Work within model-view-controller frameworks (preferably Ruby on Rails)", "Ruby on Rails"),
    ],
)
def test_preferably_applies_to_named_skill(evidence, skill):
    assert classify_requirement(evidence, "required", skill) == "preferred"


@pytest.mark.parametrize(
    ("evidence", "skill"),
    [
        ("Familiarity with AI/LLM-powered developer tooling (for example GitLab Duo)", "GitLab Duo"),
        ("Understanding of common information security and compliance concepts and controls (for example DISA STIG and SELinux)", "DISA STIG"),
        ("Understanding of common information security and compliance concepts and controls (for example DISA STIG and SELinux)", "SELinux"),
    ],
)
def test_examples_do_not_become_hard_requirements(evidence, skill):
    assert classify_requirement(evidence, "required", skill) == "mentioned"


@pytest.mark.parametrize("skill", ["OpenShift", "Kubernetes"])
def test_devops_technology_examples_are_not_automatically_required(skill):
    evidence = "Familiarity with DevOps practices and container-orchestration technologies such as OpenShift and Kubernetes"
    assert classify_requirement(evidence, "required", skill) == "mentioned"


def test_expertise_in_alternatives_is_skill_scoped():
    assert classify_requirement("Deep expertise in OAuth 2.0 and OIDC", "mentioned", "OAuth 2.0") == "required"
    assert classify_requirement("Deep expertise in OAuth 2.0 and OIDC", "mentioned", "OIDC") == "required"
    assert classify_requirement("Expert in the use of AI", "mentioned", "AI") == "required"
    assert classify_requirement("Expertise in AI is preferred", "required", "AI") == "preferred"


def test_preference_for_one_skill_does_not_change_another_skill():
    evidence = "Ruby on Rails is preferred; Go experience is required."
    assert classify_requirement(evidence, "required", "Ruby on Rails") == "preferred"
    assert classify_requirement(evidence, "required", "Go") == "required"


def test_alternative_skill_list_is_not_expanded_by_classifier():
    evidence = "Experience with Ruby on Rails or Go is required."
    # The schema has no alternative group, so this stage preserves the
    # supplied cautious level instead of promoting both alternatives.
    assert classify_requirement(evidence, "mentioned", "Ruby on Rails") == "mentioned"
    assert classify_requirement(evidence, "mentioned", "Go") == "mentioned"
    assert classify_requirement(
        "Strong expertise in AI is a plus, but not a requirement.",
        "required",
        "AI",
    ) == "preferred"


def test_expertise_for_another_skill_does_not_require_python():
    evidence = "Expertise in AI is required; Python is used by the team."
    assert classify_requirement(
        evidence,
        "mentioned",
        "Python",
    ) == "mentioned"


@pytest.mark.parametrize(
    "evidence",
    [
        "Ostro is dedicated to advancing brand engagement through AI technology.",
        "The division works at the forefront of leveraging AI innovations.",
    ],
)
def test_company_profile_expertise_is_not_promoted_to_required(evidence):
    assert classify_requirement(
        evidence,
        "required",
        "AI",
    ) == "mentioned"


def test_real_ai_expertise_in_responsibility_context_is_required():
    evidence = "Responsibilities require an expert in AI to design and build agents."
    assert not is_company_profile_evidence(evidence)
    assert classify_requirement(evidence, "mentioned", "AI") == "required"


def test_responsibility_does_not_imply_prior_experience_by_itself():
    evidence = "You will design and build AI agents for clinical workflows."
    assert classify_requirement(evidence, "mentioned", "AI") == "mentioned"
