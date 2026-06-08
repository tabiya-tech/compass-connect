"""
Follow-up Phase Handler for the Recommender/Advisor Agent.

Handles the FOLLOW_UP phase where we clarify ambiguous user responses.
"""

from app.agent.agent_types import LLMStats
from app.agent.llm_caller import LLMCaller
from app.agent.recommender_advisor_agent.state import RecommenderAdvisorAgentState
from app.agent.recommender_advisor_agent.types import ConversationPhase
from app.agent.recommender_advisor_agent.llm_response_models import (
    ConversationResponse,
    UserIntentClassification,
)
from app.agent.recommender_advisor_agent.phase_handlers.base_handler import BasePhaseHandler
from app.agent.recommender_advisor_agent.intent_classifier import IntentClassifier
from app.agent.simple_llm_agent.prompt_response_template import get_json_response_instructions
from app.conversation_memory.conversation_formatter import ConversationHistoryFormatter
from app.conversation_memory.conversation_memory_manager import ConversationContext
from app.i18n.translation_service import t


class FollowupPhaseHandler(BasePhaseHandler):
    """
    Handles the FOLLOW_UP phase.
    
    Responsibilities:
    - Clarify ambiguous user intent
    - Route to appropriate phase based on clarified intent
    - Handle edge cases (silence, off-topic, confusion)
    
    This is a transitional phase that routes to other phases once intent is clear.
    """
    
    def __init__(
        self,
        conversation_llm_provider,
        conversation_caller: LLMCaller[ConversationResponse],
        intent_classifier: IntentClassifier,
        **kwargs
    ):
        """
        Initialize the follow-up handler.

        Args:
            intent_classifier: Intent classifier for detecting user intent
        """
        super().__init__(conversation_llm_provider, conversation_caller, **kwargs)
        self._intent_classifier = intent_classifier
    
    async def handle(
        self,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """
        Handle follow-up clarification.
        """
        all_llm_stats: list[LLMStats] = []

        # Classify user intent using centralized classifier
        intent, llm_stats = await self._intent_classifier.classify_intent(
            user_input=user_input,
            state=state,
            context=context,
            phase=ConversationPhase.FOLLOW_UP,
            llm=self._conversation_llm,
            logger=self.logger
        )
        all_llm_stats.extend(llm_stats)

        # GUARDRAIL: Check for off-recommendation requests first
        if intent.intent == "request_outside_recommendations":
            self.logger.warning(f"GUARDRAIL TRIGGERED: User requested occupation outside recommendations: {intent.requested_occupation_name}")
            # Use strict guardrail to redirect back to recommendations
            return await self._handle_request_outside_recommendations(
                requested_occupation_name=intent.requested_occupation_name or t("messages", "recommenderAdvisor.thatOccupation"),
                user_input=user_input,
                state=state,
                context=context
            )

        # Route based on intent
        next_phase = self._get_next_phase(intent, state)

        if next_phase:
            state.conversation_phase = next_phase
            
            # If they selected an occupation (by number or name), set the focus
            if intent.target_occupation_index and state.recommendations:
                idx = intent.target_occupation_index - 1  # Convert to 0-indexed
                occupations = state.recommendations.occupation_recommendations
                if 0 <= idx < len(occupations):
                    state.current_focus_id = occupations[idx].uuid
                    state.current_recommendation_type = "occupation"
            elif intent.target_recommendation_id:
                state.current_focus_id = intent.target_recommendation_id
            
            return ConversationResponse(
                reasoning=f"Intent classified as '{intent.intent}', routing to {next_phase.value}",
                message=self._get_transition_message(intent, state),
                finished=False
            ), all_llm_stats
        
        # Intent unclear - generate clarifying question
        response, llm_stats = await self._generate_clarification(user_input, state, context)
        all_llm_stats.extend(llm_stats)
        
        return response, all_llm_stats

    def _get_next_phase(
        self,
        intent: UserIntentClassification,
        state: RecommenderAdvisorAgentState
    ) -> ConversationPhase | None:
        """Determine next phase based on classified intent."""
        intent_to_phase = {
            "explore_occupation": ConversationPhase.CAREER_EXPLORATION,
            "show_opportunities": ConversationPhase.PRESENT_RECOMMENDATIONS,
            "express_concern": ConversationPhase.ADDRESS_CONCERNS,
            "reject": ConversationPhase.ADDRESS_CONCERNS,
            "accept": ConversationPhase.ACTION_PLANNING,
        }
        
        return intent_to_phase.get(intent.intent)
    
    def _get_transition_message(
        self,
        intent: UserIntentClassification,
        state: RecommenderAdvisorAgentState
    ) -> str:
        """Get appropriate transition message for the intent."""
        if intent.intent == "explore_occupation" and intent.target_occupation_index:
            return t("messages", "recommenderAdvisor.transitionTellMore")
        elif intent.intent == "express_concern":
            return t("messages", "recommenderAdvisor.transitionHearYou")
        elif intent.intent == "accept":
            return t("messages", "recommenderAdvisor.transitionPlanSteps")
        elif intent.intent == "show_opportunities":
            return t("messages", "recommenderAdvisor.transitionShowAvailable")
        else:
            return t("messages", "recommenderAdvisor.transitionHelp")
    
    async def _generate_clarification(
        self,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """Generate a clarifying question when intent is unclear."""
        
        prompt = f"""
The user's message was unclear. Generate a brief, friendly clarifying question.

User said: "{user_input}"

We're in a career recommendation session. Ask a simple clarifying question to understand:
- Which occupation they're interested in (if any)
- What concern they might have
- What help they need

Keep it conversational and short. Don't repeat all the options - just ask what they meant.

{get_json_response_instructions()}
"""
        
        return await self._conversation_caller.call_llm(
            llm=self._conversation_llm,
            llm_input=ConversationHistoryFormatter.format_for_agent_generative_prompt(
                model_response_instructions=prompt,
                conversation_context=context,
            ),
            logger=self.logger
        )
