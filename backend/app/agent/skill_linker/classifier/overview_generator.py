import logging
from textwrap import dedent
from typing import Optional

from pydantic import BaseModel, Field

from app.agent.agent_types import LLMStats
from app.agent.experience.timeline import Timeline
from app.agent.experience.work_type import WorkType
from app.agent.llm_caller import LLMCaller
from app.agent.penalty import get_penalty
from app.agent.prompt_template import get_language_style
from app.agent.prompt_template.format_prompt import replace_placeholders_with_indent
from app.countries import Country, get_country_glossary
from common_libs.llm.factory import get_llm
from common_libs.llm.models_utils import LLM, LLMConfig, get_config_variation
from common_libs.llm.schema_builder import with_response_schema
from common_libs.observability.tracing import traced_observation, update_observation
from common_libs.retry import Retry


class ExperienceOverviewResponse(BaseModel):
    """
    The response from the ExperienceOverviewGenerator.
    Contains the generated experience overview, formalized responsibilities, and reasoning.
    """
    reasoning: str = Field(
        description="A concise step-by-step explanation of how you synthesized the experience overview and "
                    "formalized responsibilities from the inputs.")

    experience_overview: str = Field(
        description="A factual background overview paragraph (plain raw text without markdown or bullet points) "
                    "capturing all contextual details about the role, workplace setting, industry, work type, "
                    "environment, and Q&A context that are NOT already stated in the Responsibilities list.")

    professional_responsibilities: list[str] = Field(
        default_factory=list,
        description="The user's responsibilities rephrased into clear, professional job-posting-style statements "
                    "using standard workplace and skill terminology, strictly grounded in the provided inputs.")

    class Config:
        extra = "forbid"


class ExperienceOverviewResult(BaseModel):
    """
    The result of generating an experience overview and formalized responsibilities before skill linking.
    """
    overview: str = ""
    professional_responsibilities: list[str] = Field(default_factory=list)
    llm_stats: list[LLMStats] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class ExperienceOverviewGenerator:
    """
    Generates a concise factual overview of an experience using all pre-linking information Compass has collected
    (metadata, responsibilities, and Q&A from skill exploration).

    Used exclusively by ClassifierSkillLinker so that both the Tabiya classifier and the LLM reranker have
    rich background context on what the job is about.
    """

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._llm_caller: LLMCaller[ExperienceOverviewResponse] = LLMCaller[ExperienceOverviewResponse](
            model_response_type=ExperienceOverviewResponse
        )

    @staticmethod
    def get_system_instructions(*, country_of_interest: Country) -> str:
        _country_instructions = ""
        if country_of_interest is not None and country_of_interest != Country.UNSPECIFIED:
            _glossary = get_country_glossary(country_of_interest)
            _country_instructions = dedent("""\
            # Country Context
                The country of the user is {country_name}.
                Use this glossary to understand local terminology and context in the user's experience:
                    {glossary}
            """)
            _country_instructions = replace_placeholders_with_indent(
                _country_instructions,
                country_name=country_of_interest.name,
                glossary=_glossary
            )

        _system_instructions = dedent("""\
        <System Instructions>
            You are an expert labor-market analyst writing a concise factual background overview of a user's work or livelihood experience.
            This overview will be fed alongside the user's responsibilities to an automated skill classifier and reranker so they understand what the job is about.

            {language_style}

            # Task
                Produce two outputs from the provided information:
                1. 'experience_overview': A factual background overview paragraph (plain text without markdown or bullet points) that captures all useful context about what the job is about that is NOT already covered in the Responsibilities list:
                   - The overall role/purpose and its workplace setting, industry, or organization (e.g. family market stall, restaurant, construction site, clinic, household).
                   - The nature of the work (e.g. paid employment, trainee, unpaid/volunteer/caregiving), location, timeline, and scale/environment.
                   - Relevant contextual details from the Questions & Answers (such as products/services, customers/beneficiaries, working environment, team or supervision structure, or local context clarified by the glossary) that are not already stated in the Responsibilities list.
                2. 'professional_responsibilities': Rephrase the user's informal/first-person responsibilities (and any concrete tasks clearly stated by the user in the Questions & Answers) into clear, professional job-posting-style statements using standard workplace and skill terminology (e.g., "I check every morning what fish is left" -> "Monitor daily perishable stock levels and track remaining inventory").

            # Rules
                - In 'experience_overview', do NOT list, enumerate, summarize, or repeat the individual responsibilities/tasks already present in 'Responsibilities'—the full list of responsibilities is already provided separately right after the overview.
                - In 'professional_responsibilities', cover every responsibility the user mentioned (splitting compound tasks into distinct statements where helpful) using clear, concrete action verbs and standard occupational terminology so an automated skill extractor can recognize the underlying skills.
                - Stay strictly grounded in the provided inputs. Do NOT invent roles, industries, tasks, skills, or qualifications that were not mentioned.
                - Do NOT mention tasks or responsibilities that the user explicitly said they did NOT do or that only other people did.
                - Avoid personal or sensitive details unrelated to the work.
            {country_instructions}
            # Input Structure
                'Experience Title': The title of the experience as given by the user.
                'Company/Receiver of work': The company, organization, or receiver of the work.
                'Work Type': The type of work (e.g. Wage Employment, Trainee, Volunteer/Unpaid).
                'Location': Where the work took place.
                'Timeline': Start and end dates of the experience.
                'Responsibilities': The extracted list of responsibilities/tasks performed by the user.
                'Questions & Answers': The follow-up questions asked about this experience and the user's answers.
        </System Instructions>
        """)
        return replace_placeholders_with_indent(
            _system_instructions,
            language_style=get_language_style(),
            country_instructions=_country_instructions
        )

    @staticmethod
    def get_prompt(*,
                   experience_title: str,
                   company_name: Optional[str] = None,
                   work_type: Optional[WorkType] = None,
                   location: Optional[str] = None,
                   timeline: Optional[Timeline] = None,
                   responsibilities: list[str],
                   questions_and_answers: Optional[list[tuple[str, str]]] = None) -> str:
        timeline_str = _format_timeline(timeline)
        qa_str = _format_questions_and_answers(questions_and_answers)

        _prompt = dedent("""\
            <Input>
                Experience Title: '{experience_title}'
                Company/Receiver of work: '{company}'
                Work Type: '{work_type}'
                Location: '{location}'
                Timeline: '{timeline}'
                Responsibilities: '{responsibilities}'
                Questions & Answers: {questions_and_answers}
            </Input>
        """)

        return replace_placeholders_with_indent(
            _prompt,
            experience_title=experience_title,
            company=company_name if company_name else "N/A",
            work_type=WorkType.work_type_short(work_type) if work_type else "N/A",
            location=location if location else "N/A",
            timeline=timeline_str,
            responsibilities=", ".join(responsibilities) if responsibilities else "N/A",
            questions_and_answers=qa_str
        )

    @staticmethod
    def get_llm(*, country_of_interest: Country, temperature_config: dict) -> LLM:
        return get_llm(
            system_instructions=ExperienceOverviewGenerator.get_system_instructions(
                country_of_interest=country_of_interest
            ),
            config=LLMConfig(generation_config=temperature_config | with_response_schema(ExperienceOverviewResponse))
        )

    async def execute(self, *,
                      experience_title: str,
                      company_name: Optional[str] = None,
                      work_type: Optional[WorkType] = None,
                      location: Optional[str] = None,
                      timeline: Optional[Timeline] = None,
                      country_of_interest: Country = Country.UNSPECIFIED,
                      responsibilities: list[str],
                      questions_and_answers: Optional[list[tuple[str, str]]] = None) -> ExperienceOverviewResult:
        """
        Generate a concise factual overview and formalized responsibilities for the experience before skill linking.

        :return: ExperienceOverviewResult. Overview and professional_responsibilities are empty if generation fails.
        """
        prompt = ExperienceOverviewGenerator.get_prompt(
            experience_title=experience_title,
            company_name=company_name,
            work_type=work_type,
            location=location,
            timeline=timeline,
            responsibilities=responsibilities,
            questions_and_answers=questions_and_answers
        )
        all_llm_stats: list[LLMStats] = []

        with traced_observation(
                name="experience_overview_generator",
                as_type="chain",
                input={"experience_title": experience_title, "company_name": company_name,
                       "location": location, "responsibilities": responsibilities},
        ) as observation:
            async def _callback(attempt: int, max_retries: int) -> tuple[ExperienceOverviewResult, float, BaseException | None]:
                temperature_config = get_config_variation(
                    start_temperature=0.3, end_temperature=0.8,
                    start_top_p=0.8, end_top_p=1.0,
                    attempt=attempt, max_retries=max_retries
                )
                llm = ExperienceOverviewGenerator.get_llm(
                    country_of_interest=country_of_interest,
                    temperature_config=temperature_config
                )
                return await self._internal_execute(llm=llm, prompt=prompt, all_llm_stats=all_llm_stats)

            result, _result_penalty, _error = await Retry[ExperienceOverviewResult].call_with_penalty(
                callback=_callback, logger=self._logger
            )
            final_result = ExperienceOverviewResult(
                overview=(result.overview if result else "").strip(),
                professional_responsibilities=[
                    r.strip() for r in (result.professional_responsibilities if result else []) if r.strip()
                ],
                llm_stats=all_llm_stats,
            )
            update_observation(observation, output={
                "overview": final_result.overview,
                "professional_responsibilities": final_result.professional_responsibilities,
            })
            return final_result

    async def _internal_execute(self, *,
                                llm: LLM,
                                prompt: str,
                                all_llm_stats: list[LLMStats]) -> tuple[ExperienceOverviewResult, float, BaseException | None]:
        llm_response, llm_stats = await self._llm_caller.call_llm(
            llm=llm,
            llm_input=prompt,
            logger=self._logger
        )
        all_llm_stats.extend(llm_stats)
        if not llm_response or not llm_response.experience_overview.strip():
            self._logger.warning("The LLM did not return an experience overview; overview is empty.")
            return ExperienceOverviewResult(), get_penalty(0), ValueError("The LLM did not return an experience overview.")
        self._logger.debug("ExperienceOverviewGenerator LLM response: %s", llm_response)
        return ExperienceOverviewResult(
            overview=llm_response.experience_overview.strip(),
            professional_responsibilities=[
                r.strip() for r in llm_response.professional_responsibilities if r.strip()
            ],
        ), 0, None


def _format_timeline(timeline: Optional[Timeline]) -> str:
    if timeline is None:
        return "N/A"
    start = (timeline.start or "").strip()
    end = (timeline.end or "").strip()
    if start and end:
        return f"{start} - {end}"
    if start:
        return f"from {start}"
    if end:
        return f"until {end}"
    return "N/A"


def _format_questions_and_answers(questions_and_answers: Optional[list[tuple[str, str]]]) -> str:
    if not questions_and_answers:
        return "N/A"
    fragments = []
    for question, answer in questions_and_answers:
        qa_fragment = replace_placeholders_with_indent(
            "Question: '{question}'\nAnswer: '{answer}'\n",
            question=question,
            answer=answer
        )
        fragments.append(qa_fragment)
    return "\n" + "\n".join(fragments)
