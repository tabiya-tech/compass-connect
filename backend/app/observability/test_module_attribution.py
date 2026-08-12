"""
Tests for module, sub module and session attribution of LLM traces (CC-1 acceptance criteria 2, 3 and 4).

Each service entry point is exercised through its real traced wrapper, with only the work it
delegates to stubbed out, so these tests assert on the grouping the Langfuse UI would show.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.agent_director.abstract_agent_director import CounselingSubPhase
from app.career_explorer.service import CareerExplorerService
from app.career_readiness.service import CareerReadinessService
from app.career_readiness.types import ConversationMode
from app.conversations.service import ConversationService
from app.observability.module_types import TraceModule, TraceSubModule, sub_module_label
from app.users.cv.utils.llm_extractor import CVExperienceExtractor
from common_libs.observability.config import TracingConfig
from common_libs.observability.testing import TEST_TRACING_CONFIG, in_memory_tracing


def _a_conversation_service(sub_phase: CounselingSubPhase = CounselingSubPhase.EXPLORE_EXPERIENCES) -> ConversationService:
    """A ConversationService whose only live code is the traced `send` wrapper."""
    service = ConversationService.__new__(ConversationService)

    state = MagicMock()
    state.agent_director_state.counseling_sub_phase = sub_phase
    service._application_state_metrics_recorder = MagicMock()  # pylint: disable=protected-access
    service._application_state_metrics_recorder.get_state = AsyncMock(return_value=state)  # pylint: disable=protected-access

    response = MagicMock()
    response.messages = []
    service._send = AsyncMock(return_value=response)  # pylint: disable=protected-access

    return service


def _a_career_readiness_service() -> CareerReadinessService:
    """A CareerReadinessService whose only live code is the traced `send_message` wrapper."""
    service = CareerReadinessService.__new__(CareerReadinessService)

    conversation = MagicMock()
    conversation.conversation_mode = ConversationMode.INSTRUCTION

    response = MagicMock()
    response.messages = []

    service._get_module_or_raise = MagicMock(return_value=MagicMock())  # pylint: disable=protected-access
    service._get_conversation_or_raise = AsyncMock(return_value=conversation)  # pylint: disable=protected-access
    service._validate_access = MagicMock()  # pylint: disable=protected-access
    service._handle_instruction_message = AsyncMock(return_value=response)  # pylint: disable=protected-access

    return service


def _a_career_explorer_service() -> CareerExplorerService:
    """A CareerExplorerService whose only live code is the traced `send_message` wrapper."""
    service = CareerExplorerService.__new__(CareerExplorerService)

    response = MagicMock()
    response.messages = []
    service._send_message = AsyncMock(return_value=response)  # pylint: disable=protected-access

    return service


def _a_cv_extractor() -> CVExperienceExtractor:
    """A CVExperienceExtractor whose only live code is the traced `extract_experiences` wrapper."""
    extractor = CVExperienceExtractor.__new__(CVExperienceExtractor)
    extractor._extract_experiences = AsyncMock(return_value=["sold vegetables at the market"])  # pylint: disable=protected-access
    return extractor


class TestModuleAttribution:
    """
    Tests for module attribution.
    """

    @pytest.mark.asyncio
    async def test_attributes_a_conversation_turn_to_build_your_profile(self):
        """Attributes a conversation turn to build your profile."""
        # GIVEN a Build Your Profile conversation turn
        given_service = _a_conversation_service()

        # WHEN the turn is handled
        with in_memory_tracing() as recorded_spans:
            await given_service.send("user-1", 42, "hello", clear_memory=False, filter_pii=False)

        # THEN expect exactly one module to be reported
        assert recorded_spans.trace_modules() == {TraceModule.BUILD_YOUR_PROFILE.value}
        # AND expect the root trace to be tagged with it
        actual_span = recorded_spans.by_name("conversation.turn")
        assert f"module:{TraceModule.BUILD_YOUR_PROFILE.value}" in actual_span.attributes["langfuse.trace.tags"]

    @pytest.mark.asyncio
    async def test_attributes_a_career_readiness_turn_to_career_readiness(self):
        """Attributes a career readiness turn to career readiness."""
        # GIVEN a Career Readiness turn on the CV development content module
        given_service = _a_career_readiness_service()
        given_content_module_id = "cv-development"

        # WHEN the turn is handled
        with in_memory_tracing() as recorded_spans:
            await given_service.send_message("user-1", given_content_module_id, "conversation-1", "hello")

        # THEN expect the career readiness module to be reported
        assert recorded_spans.trace_modules() == {TraceModule.CAREER_READINESS.value}
        # AND expect the content module to be reported as the sub module, not to overwrite the module
        assert recorded_spans.trace_sub_modules() == {"CV Development"}
        # AND expect both to be tagged
        actual_tags = recorded_spans.by_name("career_readiness.turn").attributes["langfuse.trace.tags"]
        assert f"module:{TraceModule.CAREER_READINESS.value}" in actual_tags
        assert "sub_module:CV Development" in actual_tags

    @pytest.mark.asyncio
    async def test_attributes_a_career_explorer_turn_to_career_explorer(self):
        """Attributes a career explorer turn to career explorer."""
        # GIVEN a Career Explorer turn
        given_service = _a_career_explorer_service()

        # WHEN the turn is handled
        with in_memory_tracing() as recorded_spans:
            await given_service.send_message("user-1", "tell me about mining")

        # THEN expect the career explorer module to be reported
        assert recorded_spans.trace_modules() == {TraceModule.CAREER_EXPLORER.value}

    @pytest.mark.asyncio
    async def test_attributes_a_cv_upload_to_cv_upload(self):
        """Attributes a cv upload to cv upload."""
        # GIVEN a CV to extract experiences from
        given_extractor = _a_cv_extractor()

        # WHEN the extraction runs
        with in_memory_tracing() as recorded_spans:
            await given_extractor.extract_experiences("# My CV")

        # THEN expect the cv upload module to be reported
        assert recorded_spans.trace_modules() == {TraceModule.CV_UPLOAD.value}


class TestSubModuleAttribution:
    """
    Tests for sub module attribution.
    """

    @pytest.mark.asyncio
    async def test_reports_the_counseling_sub_phase_as_the_build_your_profile_sub_module(self):
        """Reports the counseling sub phase as the build your profile sub module."""
        # GIVEN a Build Your Profile turn in the experience exploration sub-phase
        given_service = _a_conversation_service(CounselingSubPhase.EXPLORE_EXPERIENCES)

        # WHEN the turn is handled
        with in_memory_tracing() as recorded_spans:
            await given_service.send("user-1", 42, "hello", clear_memory=False, filter_pii=False)

        # THEN expect the sub-phase to be reported as the sub module
        assert recorded_spans.trace_sub_modules() == {TraceSubModule.EXPLORE_EXPERIENCES.value}

    @pytest.mark.asyncio
    async def test_reports_sub_modules_without_underscores(self):
        """Reports sub modules without underscores."""
        # GIVEN a Build Your Profile turn and a Career Readiness turn, whose sub modules come from an
        # enum name and from a registry slug respectively
        given_conversation_service = _a_conversation_service(CounselingSubPhase.RECOMMENDER_ADVISOR)
        given_career_readiness_service = _a_career_readiness_service()

        # WHEN both turns are handled
        with in_memory_tracing() as recorded_spans:
            await given_conversation_service.send("user-1", 42, "hello", clear_memory=False, filter_pii=False)
            await given_career_readiness_service.send_message("user-1", "interview-preparation", "conversation-1", "hello")

        # THEN expect both to be reported as human readable labels, whichever they were derived from
        assert recorded_spans.trace_sub_modules() == {"Recommender Advisor", "Interview Preparation"}

    @pytest.mark.asyncio
    async def test_reports_no_sub_module_for_a_module_that_has_none(self):
        """Reports no sub module for a module that has none."""
        # GIVEN a CV upload, which is a single module-level unit of work with no sub module
        given_extractor = _a_cv_extractor()

        # WHEN the extraction runs
        with in_memory_tracing() as recorded_spans:
            await given_extractor.extract_experiences("# My CV")

        # THEN expect no sub module to be reported, rather than an empty one
        assert recorded_spans.trace_sub_modules() == set()


class TestSessionAttribution:
    """
    Tests for session attribution.
    """

    @pytest.mark.asyncio
    async def test_groups_build_your_profile_turns_by_conversation_session(self):
        """Groups build your profile turns by conversation session."""
        # GIVEN two turns of the same Build Your Profile conversation
        given_service = _a_conversation_service()
        given_session_id = 42

        # WHEN both turns are handled
        with in_memory_tracing() as recorded_spans:
            await given_service.send("user-1", given_session_id, "hello", clear_memory=False, filter_pii=False)
            await given_service.send("user-1", given_session_id, "and then?", clear_memory=False, filter_pii=False)

        # THEN expect the conversation session id to be the session, as a string
        assert recorded_spans.session_ids() == {str(given_session_id)}

    @pytest.mark.asyncio
    async def test_groups_career_readiness_turns_by_the_users_career_readiness_session(self):
        """Groups career readiness turns by the users career readiness session."""
        # GIVEN two Career Readiness turns of the same user, on two different content modules
        given_service = _a_career_readiness_service()
        given_user_id = "user-1"

        # WHEN both turns are handled
        with in_memory_tracing() as recorded_spans:
            await given_service.send_message(given_user_id, "cv-development", "conversation-1", "hello")
            await given_service.send_message(given_user_id, "cover-letter", "conversation-2", "hello")

        # THEN expect one session for the user's whole Career Readiness journey, named after the
        # module so that it cannot collide with another module's session for the same user
        assert recorded_spans.session_ids() == {f"{given_user_id}-career-readiness"}
        # AND expect the content modules to still be told apart as sub modules
        assert recorded_spans.trace_sub_modules() == {"CV Development", "Cover Letter"}

    @pytest.mark.asyncio
    async def test_groups_career_explorer_turns_by_the_users_career_explorer_session(self):
        """Groups career explorer turns by the users career explorer session."""
        # GIVEN two turns of one user's Career Explorer conversation, which the repository keys by
        # user id, so the user id is that conversation's id
        given_service = _a_career_explorer_service()
        given_user_id = "user-1"

        # WHEN both turns are handled
        with in_memory_tracing() as recorded_spans:
            await given_service.send_message(given_user_id, "tell me about mining")
            await given_service.send_message(given_user_id, "what about farming?")

        # THEN expect the conversation to be reported as one session, named after the module so that
        # it cannot collide with another module's session for the same user
        assert recorded_spans.session_ids() == {f"{given_user_id}-career-explorer"}

    @pytest.mark.asyncio
    async def test_keeps_the_sessions_of_two_users_apart(self):
        """Keeps the sessions of two users apart."""
        # GIVEN two users working through Career Readiness
        given_service = _a_career_readiness_service()

        # WHEN a turn of each is handled
        with in_memory_tracing() as recorded_spans:
            await given_service.send_message("user-1", "cv-development", "conversation-1", "hello")
            await given_service.send_message("user-2", "cv-development", "conversation-2", "hello")

        # THEN expect one session per user
        assert recorded_spans.session_ids() == {"user-1-career-readiness", "user-2-career-readiness"}

    @pytest.mark.asyncio
    async def test_keeps_the_sessions_of_two_modules_of_one_user_apart(self):
        """Keeps the sessions of two modules of one user apart."""
        # GIVEN one user working in both Career Readiness and Career Explorer, whose sessions are
        # both derived from their user id
        given_user_id = "user-1"

        # WHEN a turn of each is handled
        with in_memory_tracing() as recorded_spans:
            await _a_career_readiness_service().send_message(given_user_id, "cv-development", "conversation-1", "hello")
            await _a_career_explorer_service().send_message(given_user_id, "tell me about mining")

        # THEN expect the module suffix to keep them apart, rather than merging two unrelated
        # conversations into one session
        assert recorded_spans.session_ids() == {
            f"{given_user_id}-career-readiness",
            f"{given_user_id}-career-explorer",
        }


class TestUserAttribution:
    """
    Tests for user attribution. Only the Build your Profile routes set the observability context
    variables, so every other module has to pass the user to `start_trace` itself.
    """

    @pytest.mark.asyncio
    async def test_attributes_a_build_your_profile_turn_to_its_user(self):
        """Attributes a build your profile turn to its user."""
        # GIVEN a Build Your Profile turn
        given_service = _a_conversation_service()
        given_user_id = "user-1"

        # WHEN the turn is handled
        with in_memory_tracing() as recorded_spans:
            await given_service.send(given_user_id, 42, "hello", clear_memory=False, filter_pii=False)

        # THEN expect the trace to be attributed to the user
        assert recorded_spans.user_ids() == {given_user_id}

    @pytest.mark.asyncio
    async def test_attributes_a_career_readiness_turn_to_its_user(self):
        """Attributes a career readiness turn to its user."""
        # GIVEN a Career Readiness turn
        given_service = _a_career_readiness_service()
        given_user_id = "user-1"

        # WHEN the turn is handled
        with in_memory_tracing() as recorded_spans:
            await given_service.send_message(given_user_id, "cv-development", "conversation-1", "hello")

        # THEN expect the trace to be attributed to the user
        assert recorded_spans.user_ids() == {given_user_id}

    @pytest.mark.asyncio
    async def test_attributes_a_career_explorer_turn_to_its_user(self):
        """Attributes a career explorer turn to its user."""
        # GIVEN a Career Explorer turn
        given_service = _a_career_explorer_service()
        given_user_id = "user-1"

        # WHEN the turn is handled
        with in_memory_tracing() as recorded_spans:
            await given_service.send_message(given_user_id, "tell me about mining")

        # THEN expect the trace to be attributed to the user
        assert recorded_spans.user_ids() == {given_user_id}

    @pytest.mark.asyncio
    async def test_attributes_a_cv_extraction_to_its_user(self):
        """Attributes a cv extraction to its user."""
        # GIVEN a CV extraction, which runs in a background task carrying no request context
        given_extractor = _a_cv_extractor()
        given_user_id = "user-1"

        # WHEN the extraction runs
        with in_memory_tracing() as recorded_spans:
            await given_extractor.extract_experiences("# My CV", user_id=given_user_id)

        # THEN expect the trace to be attributed to the user, even though it has no session
        assert recorded_spans.user_ids() == {given_user_id}
        assert recorded_spans.session_ids() == set()


class TestSubModuleLabel:
    """
    Tests for sub module label.
    """

    @pytest.mark.parametrize("given_identifier,expected_label", [
        ("cv-development", "CV Development"),
        ("cv_development", "CV Development"),
        ("interview-preparation", "Interview Preparation"),
        ("entrepreneurship", "Entrepreneurship"),
        ("PREFERENCE_ELICITATION", "Preference Elicitation"),
    ])
    def test_humanises_an_identifier(self, given_identifier: str, expected_label: str):
        """Humanises an identifier."""
        # GIVEN an identifier, as a registry slug or as an enum name
        # WHEN it is turned into a sub module label
        actual_label = sub_module_label(given_identifier)

        # THEN expect a human readable label with no underscores or dashes
        assert actual_label == expected_label
        assert "_" not in actual_label
        assert "-" not in actual_label


class TestOnlyDeployedModulesProduceTraces:
    """
    Tests for only deployed modules produce traces.
    """

    @pytest.mark.asyncio
    async def test_a_compass_core_only_deployment_reports_only_build_your_profile(self):
        """A compass core only deployment reports only build your profile."""
        # GIVEN a deployment where only the Compass core (BYP chat) is exercised
        given_service = _a_conversation_service()

        # WHEN several conversation turns are handled and nothing else is
        with in_memory_tracing() as recorded_spans:
            for turn in range(3):
                await given_service.send("user-1", 42, f"turn {turn}", clear_memory=False, filter_pii=False)

        # THEN expect no module other than Build Your Profile to appear.
        # Modules are tagged at their own service entry points, so a module that is never invoked
        # cannot emit a trace — there is no conditional logic keeping them out.
        assert recorded_spans.trace_modules() == {TraceModule.BUILD_YOUR_PROFILE.value}
        # AND expect none of the other modules' root traces to exist
        assert "career_readiness.turn" not in recorded_spans.names()
        assert "career_explorer.turn" not in recorded_spans.names()
        assert "cv.extract_experiences" not in recorded_spans.names()

    @pytest.mark.asyncio
    async def test_each_exercised_module_appears_exactly_once_per_turn(self):
        """Each exercised module appears exactly once per turn."""
        # GIVEN a deployment where all three suite areas are exercised
        # WHEN one turn of each is handled
        with in_memory_tracing() as recorded_spans:
            await _a_conversation_service().send("user-1", 42, "hello", clear_memory=False, filter_pii=False)
            await _a_career_readiness_service().send_message("user-1", "cv-development", "conversation-1", "hello")
            await _a_career_explorer_service().send_message("user-1", "tell me about mining")

        # THEN expect exactly the three modules named in the acceptance criteria
        assert recorded_spans.trace_modules() == {
            TraceModule.BUILD_YOUR_PROFILE.value,
            TraceModule.CAREER_READINESS.value,
            TraceModule.CAREER_EXPLORER.value,
        }


class TestJobMatchingSplit:
    """
    Tests for job matching split.
    """

    @pytest.mark.asyncio
    async def test_reports_preference_elicitation_as_build_your_profile_by_default(self):
        """Reports preference elicitation as build your profile by default."""
        # GIVEN a turn in the preference elicitation sub-phase
        given_service = _a_conversation_service(CounselingSubPhase.PREFERENCE_ELICITATION)

        # WHEN the turn is handled with the default configuration
        with in_memory_tracing() as recorded_spans:
            await given_service.send("user-1", 42, "hello", clear_memory=False, filter_pii=False)

        # THEN expect it to stay part of Build Your Profile, so a deployment reports exactly the
        # three modules the acceptance criteria name
        assert recorded_spans.trace_modules() == {TraceModule.BUILD_YOUR_PROFILE.value}
        # AND expect it to still be told apart as a sub module by anyone who wants to split it
        assert recorded_spans.trace_sub_modules() == {TraceSubModule.PREFERENCE_ELICITATION.value}
        actual_tags = recorded_spans.by_name("conversation.turn").attributes["langfuse.trace.tags"]
        assert f"sub_module:{TraceSubModule.PREFERENCE_ELICITATION.value}" in actual_tags

    @pytest.mark.asyncio
    async def test_reports_preference_elicitation_as_job_matching_when_the_split_is_enabled(self):
        """Reports preference elicitation as job matching when the split is enabled."""
        # GIVEN a turn in the preference elicitation sub-phase
        given_service = _a_conversation_service(CounselingSubPhase.PREFERENCE_ELICITATION)
        # AND a configuration that splits job matching into its own module
        given_config = TracingConfig(**{**TEST_TRACING_CONFIG.model_dump(), "split_job_matching": True})

        # WHEN the turn is handled
        with in_memory_tracing(given_config) as recorded_spans:
            await given_service.send("user-1", 42, "hello", clear_memory=False, filter_pii=False)

        # THEN expect it to be reported as its own module
        assert recorded_spans.trace_modules() == {TraceModule.JOB_MATCHING.value}
        # AND expect the sub module to name the part of it that ran
        assert recorded_spans.trace_sub_modules() == {TraceSubModule.PREFERENCE_ELICITATION.value}

    @pytest.mark.asyncio
    async def test_leaves_experience_exploration_as_build_your_profile_when_the_split_is_enabled(self):
        """Leaves experience exploration as build your profile when the split is enabled."""
        # GIVEN a turn in the experience exploration sub-phase
        given_service = _a_conversation_service(CounselingSubPhase.EXPLORE_EXPERIENCES)
        # AND a configuration that splits job matching into its own module
        given_config = TracingConfig(**{**TEST_TRACING_CONFIG.model_dump(), "split_job_matching": True})

        # WHEN the turn is handled
        with in_memory_tracing(given_config) as recorded_spans:
            await given_service.send("user-1", 42, "hello", clear_memory=False, filter_pii=False)

        # THEN expect it to stay in Build Your Profile
        assert recorded_spans.trace_modules() == {TraceModule.BUILD_YOUR_PROFILE.value}
