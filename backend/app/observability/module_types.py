"""
The "module" and "sub module" dimensions that LLM traces are grouped by.

A `TraceModule` is a *suite area* of Compass Connect (Build Your Profile, Career Readiness,
Career Explorer, ...). A `sub_module` is the named area *within* it that produced the work: the
counseling sub-phase for Build Your Profile, the content module (`CV Development`,
`Interview Preparation`, ...) for Career Readiness. The Career Readiness content module is
deliberately *not* the trace module — a Career Readiness turn carries
`module=Career Readiness` and `sub_module=CV Development`.

Both dimensions are human readable, exactly as they read in the Langfuse UI: title case, spaces
rather than underscores, no slugs.

Modules are tagged at their own service entry points. A deployment that does not mount, say,
`add_career_explorer_routes` never reaches the code that sets `TraceModule.CAREER_EXPLORER`,
so it emits no traces for that module without any conditional logic.
"""

from enum import Enum

# Words that read as acronyms rather than as title-cased words when a slug is humanised.
_ACRONYMS = frozenset({"cv", "id", "ai"})


class TraceModule(Enum):
    """
    The Compass Connect suite area a trace belongs to.
    """

    BUILD_YOUR_PROFILE = "Build your Profile"
    """
    The Compass core conversation: Welcome, Collect Experiences, Skill Explorer, the experience
    linking/ranking pipeline and the conversation summariser.
    """

    JOB_MATCHING = "Job Matching"
    """
    Preference Elicitation and Recommender Advisor.

    These run *inside* the Build Your Profile conversation, so they are only reported as their own
    module when `TracingConfig.split_job_matching` is enabled. Otherwise they are reported as
    `BUILD_YOUR_PROFILE` with a `sub_module` tag.
    """

    CAREER_READINESS = "Career Readiness"
    """
    The "Get Job Ready" modules, driven by `app.career_readiness`.
    """

    CAREER_EXPLORER = "Career Explorer"
    """
    Sector exploration and the sector relevance classifier, driven by `app.career_explorer`.
    """

    CV_UPLOAD = "CV Upload"
    """
    Experience extraction from an uploaded CV.
    """


class TraceSubModule(Enum):
    """
    The named area within a `TraceModule` a trace belongs to.

    Only the sub modules that are fixed in code live here. Career Readiness sub modules come from
    the module registry, which is data rather than code, so they are humanised from their id with
    `sub_module_label`.
    """

    EXPLORE_EXPERIENCES = "Explore Experiences"
    """
    The Build Your Profile experience-elicitation sub-phase: Collect Experiences and Skill Explorer.
    """

    PREFERENCE_ELICITATION = "Preference Elicitation"
    """
    The Build Your Profile job-preference sub-phase.
    """

    RECOMMENDER_ADVISOR = "Recommender Advisor"
    """
    The Build Your Profile job-recommendation sub-phase.
    """


def sub_module_label(identifier: str) -> str:
    """
    Turn an identifier into the human readable sub module label the Langfuse UI shows.

    Both the slugs the Career Readiness registry uses (`cv-development`) and the enum names the
    conversation code uses (`PREFERENCE_ELICITATION`) come out the same way, so the values in
    Langfuse are consistent no matter where they were derived from. Titles are deliberately *not*
    used for Career Readiness: they are localised, and a Portuguese deployment must not report a
    different sub module from an English one.

    :param identifier: A slug or enum name, e.g. "cv-development" or "PREFERENCE_ELICITATION".
    :return: The label, e.g. "CV Development" or "Preference Elicitation".
    """
    words = identifier.replace("-", " ").replace("_", " ").split()
    return " ".join(word.upper() if word.lower() in _ACRONYMS else word.capitalize() for word in words)
