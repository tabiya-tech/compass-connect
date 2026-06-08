"""
Skills Pivot Phase Handler for the Recommender/Advisor Agent.

Handles the SKILLS_UPGRADE_PIVOT phase where we present training
recommendations after user has rejected occupation options.
"""

from typing import Optional

from app.agent.agent_types import LLMStats
from app.agent.llm_caller import LLMCaller
from app.agent.recommender_advisor_agent.state import RecommenderAdvisorAgentState
from app.agent.recommender_advisor_agent.types import (
    ConversationPhase,
    SkillsTrainingRecommendation,
    UserInterestLevel,
)
from app.agent.recommender_advisor_agent.llm_response_models import (
    ConversationResponse,
    UserIntentClassification
)
from app.agent.recommender_advisor_agent.phase_handlers.base_handler import BasePhaseHandler
from app.agent.recommender_advisor_agent.intent_classifier import IntentClassifier
from app.conversation_memory.conversation_memory_manager import ConversationContext
from app.i18n.translation_service import t


class SkillsPivotPhaseHandler(BasePhaseHandler):
    """
    Handles the SKILLS_UPGRADE_PIVOT phase.

    Responsibilities:
    - Present training/skill-building recommendations
    - Frame training as a path to future opportunities
    - Connect each training to specific occupations it unlocks
    - Keep door open for deeper conversation about barriers
    - Detect user intent and transition to appropriate phases

    Trigger: User has rejected >= 3 occupations.
    """

    def __init__(
        self,
        conversation_llm_provider,
        conversation_caller: LLMCaller[ConversationResponse],
        intent_classifier: IntentClassifier = None,
        exploration_handler: 'ExplorationPhaseHandler' = None,
        concerns_handler: 'ConcernsPhaseHandler' = None,
        action_planning_handler: 'ActionPlanningPhaseHandler' = None,
        present_handler: 'PresentPhaseHandler' = None,
        **kwargs
    ):
        """
        Initialize the skills pivot handler.

        Args:
            conversation_llm_provider: Callable returning the conversation LLM for the current request locale
            conversation_caller: LLM caller for conversation responses
            intent_classifier: Optional intent classifier for detecting user intent
            exploration_handler: Optional exploration handler for immediate transitions
            concerns_handler: Optional concerns handler for immediate transitions
            action_planning_handler: Optional action planning handler for immediate transitions
            present_handler: Optional present handler for returning to recommendations
        """
        super().__init__(conversation_llm_provider, conversation_caller, **kwargs)
        self._intent_classifier = intent_classifier
        self._exploration_handler = exploration_handler
        self._concerns_handler = concerns_handler
        self._action_planning_handler = action_planning_handler
        self._present_handler = present_handler
    
    async def handle(
        self,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """
        Handle presenting training recommendations.

        Two scenarios:
        1. User persisted on out-of-list occupation → Show skills gap analysis + relevant trainings
        2. User rejected 3+ occupations → Show general training recommendations
        """
        all_llm_stats: list[LLMStats] = []

        # Mark that we've pivoted
        state.pivoted_to_training = True

        if state.recommendations is None:
            return ConversationResponse(
                reasoning="No recommendations available for pivot",
                message=t("messages", "recommenderAdvisor.pivotNoRecommendations"),
                finished=False
            ), []

        # Get training recommendations
        trainings = state.recommendations.skillstraining_recommendations[:5]

        if not trainings:
            # No training recommendations - explore why they rejected everything
            return await self._handle_no_trainings(user_input, state, context)

        # Check if this is FOLLOW-UP to educational guidance (user responding to binary choice)
        # If pending occupation exists AND guidance was already shown, this is a follow-up
        # Handle this FIRST before intent classification (binary choice is very specific context)
        if state.pending_out_of_list_occupation and state.educational_guidance_shown:
            return await self._handle_educational_guidance_followup(
                user_input=user_input,
                state=state,
                context=context,
                trainings=trainings
            )

        # Check if this is FIRST TIME for out-of-list occupation (user just persisted)
        if state.pending_out_of_list_occupation and not state.educational_guidance_shown:
            return await self._handle_out_of_list_occupation_gap_analysis(
                user_input=user_input,
                state=state,
                context=context,
                trainings=trainings
            )

        # If user has responded (not initial presentation), detect their intent
        # This enables phase transitions and seamless conversation flow
        is_initial_presentation = user_input.strip() == ""

        if not is_initial_presentation and self._intent_classifier:
            # Classify user intent using centralized classifier
            self.logger.info(f"Classifying user intent for: '{user_input}' in SKILLS_UPGRADE_PIVOT phase")
            intent, intent_stats = await self._intent_classifier.classify_intent(
                user_input=user_input,
                state=state,
                context=context,
                phase=ConversationPhase.SKILLS_UPGRADE_PIVOT,
                llm=self._conversation_llm,
                logger=self.logger
            )
            all_llm_stats.extend(intent_stats)

            # Check if intent classification succeeded
            if intent is None:
                self.logger.error("Intent classification failed after all retries, falling back to conversational response")
                # Fall through to regular conversation response generation below
            else:
                self.logger.info(f"Intent classified as: {intent.intent}, reasoning: {intent.reasoning}")

                # Handle the intent and potentially transition phases
                phase_transition = await self._handle_user_intent(intent, user_input, state, context, trainings)

                if phase_transition:
                    # Intent handled, phase transition will occur
                    all_llm_stats.extend(phase_transition[1])
                    return phase_transition[0], all_llm_stats

        # Standard pivot after rejections - use LLM to respond contextually
        # Don't just return static training list - engage in conversation about trainings
        response, llm_stats = await self._handle_training_conversation(
            user_input=user_input,
            state=state,
            context=context,
            trainings=trainings
        )
        all_llm_stats.extend(llm_stats)
        return response, all_llm_stats
    
    async def _handle_out_of_list_occupation_gap_analysis(
        self,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext,
        trainings: list[SkillsTrainingRecommendation]
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """
        Handle skills gap analysis for user's requested out-of-list occupation.

        Uses LLM to:
        1. Compare user's current skills to what requested occupation needs
        2. Identify the gap
        3. Show relevant trainings that could help bridge the gap
        4. Offer controlled binary choice

        Args:
            user_input: User's message
            state: Current agent state
            context: Conversation context
            trainings: Available training recommendations

        Returns:
            Tuple of (ConversationResponse, list of LLMStats)
        """
        all_llm_stats: list[LLMStats] = []
        requested_occupation = state.pending_out_of_list_occupation

        self.logger.info(f"Performing skills gap analysis for requested occupation: {requested_occupation}")

        # Import here to avoid circular dependency
        from app.agent.recommender_advisor_agent.prompts import build_context_block
        from app.conversation_memory.conversation_formatter import ConversationHistoryFormatter
        from app.agent.simple_llm_agent.prompt_response_template import get_json_response_instructions

        # Build context
        skills_list = self._extract_skills_list(state)
        pref_vec_dict = state.preference_vector.model_dump() if state.preference_vector else {}
        conv_history = ConversationHistoryFormatter.format_to_string(context)
        recs_summary = self._build_recommendations_summary(state)

        context_block = build_context_block(
            skills=skills_list,
            preference_vector=pref_vec_dict,
            recommendations_summary=recs_summary,
            conversation_history=conv_history,
            country_of_user=state.country_of_user
        )

        # Build trainings summary
        trainings_summary = "\n".join([
            f"- {trn.training_title}: {trn.skill} ({trn.estimated_hours or '?'} hours, {trn.cost or 'varies'})"
            for trn in trainings
        ])

        # Build prompt for gap analysis
        prompt = context_block + f"""
## CAREER PATH GUIDANCE FOR OUT-OF-LIST OCCUPATION

The user is passionate about **"{requested_occupation}"** and wants to understand what it takes to pursue this path.

**YOUR TASK**:
Provide helpful, educational, unbiased guidance on the career path to {requested_occupation}.

**Available training recommendations:**
{trainings_summary}

Generate a response that:

1. **Acknowledge their passion** (1 sentence)
   - "I understand you're passionate about {requested_occupation}."

2. **Educational career path overview** (3-4 sentences) - FOCUS ON THE PATH FORWARD, NOT JUST GAPS
   - What skills are typically needed for {requested_occupation} (be specific and educational)
   - Realistic career progression: "Most people start as [entry level], then move to [intermediate], then to [{requested_occupation}]"
   - Typical timeline/effort: "This usually takes X years of training/experience"
   - Be informative and educational, NOT discouraging - you're showing them the map, not blocking the road

3. **Current strengths & stepping stones** (2-3 sentences)
   - Are any of their current skills transferable? (e.g., "Your electrical knowledge could help with sound engineering equipment")
   - Could any of the available trainings be stepping stones? (Check the trainings list - even if not directly related, could they build foundational skills?)
   - If truly no connection: Be honest but supportive: "While your current path is different, career changes are possible with dedicated effort"

4. **Next steps** (1-2 sentences) - GIVE THEM OPTIONS, NOT DEAD ENDS
   - If relevant trainings exist: "Some of these trainings could be stepping stones: [mention specific ones]"
   - If no relevant trainings: "To pursue this path, you'd typically need to seek out [specific type of training/apprenticeship]"
   - Then offer choice: "Would you like to explore these options, or look at careers that build on your current strengths?"

**TONE**:
- Educational and informative (like a career counselor, not a gatekeeper)
- Honest about time/effort but NOT discouraging
- Unbiased - present facts, respect their autonomy
- Supportive - show the path forward, not just the obstacles
- Total length: 7-10 sentences

**CRITICAL REQUIREMENTS**:
- FOCUS ON PATH FORWARD, not just what they lack
- Be educational (show the map), not judgmental
- End with OPTIONS (not dead ends)
- Do NOT ask "What interests you about Music Director?" (prevents derailing)
- Response must be JSON matching ConversationResponse schema
- Set `finished` to `false`
- NEVER provide specific contact information, URLs, or addresses you don't have - stick to general career guidance only

**REQUIRED OUTPUT FORMAT** (JSON):
{{
    "reasoning": "User passionate about Music Director. Providing educational career path guidance and realistic stepping stones.",
    "message": "I understand you're passionate about Music Director work. To become a Music Director, you'd typically need skills in music theory, composition, conducting, and sound engineering. Most people start by learning an instrument or music production, then gain experience in smaller musical projects, and eventually work up to directing. This path usually takes 3-5 years of dedicated training and practice. While your current electrical skills are quite different, they could actually be useful when working with sound engineering equipment and stage setups. Our Electrician Grade III Certification could be a foundation for technical sound work, which is often a stepping stone into the music industry. Would you like to explore this technical music path, or look at careers that build more directly on your current strengths?",
    "finished": false
}}

""" + get_json_response_instructions()

        # Call LLM
        try:
            response, llm_stats = await self._conversation_caller.call_llm(
                llm=self._conversation_llm,
                llm_input=ConversationHistoryFormatter.format_for_agent_generative_prompt(
                    model_response_instructions=prompt,
                    context=context,
                    user_input=user_input,
                ),
                logger=self.logger
            )
            all_llm_stats.extend(llm_stats)

            # Mark that we've shown educational guidance
            # DON'T clear pending occupation yet - we need it for the follow-up turn
            # User needs to respond to the binary choice we just offered
            # We'll clear it when they make their choice in the next turn
            state.educational_guidance_shown = True

            self.logger.info(f"Generated skills gap analysis for '{requested_occupation}'")
            return response, all_llm_stats

        except Exception as e:
            self.logger.error(f"LLM call failed for gap analysis of '{requested_occupation}': {e}")
            # Fallback to simple template - clear everything
            state.pending_out_of_list_occupation = None
            state.pending_out_of_list_occupation_entity = None
            state.educational_guidance_shown = False

            return ConversationResponse(
                reasoning=f"Skills gap analysis for '{requested_occupation}' (LLM failed - using fallback)",
                message=t("messages", "recommenderAdvisor.gapAnalysisFallback", occupation=requested_occupation),
                finished=False
            ), all_llm_stats

    async def _handle_educational_guidance_followup(
        self,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext,
        trainings: list[SkillsTrainingRecommendation]
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """
        Handle user's response to the binary choice offered in educational guidance.

        The educational guidance ends with: "Would you like to explore [trainings], or look at [original recommendations]?"
        This method interprets which option the user chose.

        Args:
            user_input: User's response to the binary choice
            state: Current agent state
            context: Conversation context
            trainings: Available training recommendations

        Returns:
            Tuple of (ConversationResponse, list of LLMStats)
        """
        all_llm_stats: list[LLMStats] = []
        requested_occupation = state.pending_out_of_list_occupation

        self.logger.info(f"Handling follow-up response to educational guidance for '{requested_occupation}'")

        # Use LLM to classify user's choice
        from pydantic import BaseModel, Field

        class UserChoice(BaseModel):
            wants_training_path: bool = Field(
                description="True if user wants to explore training/technical path, False if they want to return to original recommendations"
            )
            reasoning: str = Field(description="Brief explanation of the decision")

        prompt = f"""
You previously provided educational career path guidance for "{requested_occupation}" and asked:
"Would you like to explore the training/technical path, or look at careers that build on your current strengths?"

**USER'S RESPONSE**: "{user_input}"

**YOUR TASK**: Determine which option the user chose.

**EXAMPLES OF TRAINING PATH CHOICE (return wants_training_path=true)**:
- "I want to explore this technical route further" → TRUE
- "Show me the trainings" → TRUE
- "I'd like to see the training options" → TRUE
- "Let's explore the technical music path" → TRUE
- "Tell me more about the training" → TRUE

**EXAMPLES OF ORIGINAL RECOMMENDATIONS CHOICE (return wants_training_path=false)**:
- "Let's look at my original options" → FALSE
- "Show me careers that match my skills" → FALSE
- "I want to see the other recommendations" → FALSE
- "Actually, let's focus on what you recommended" → FALSE

**REQUIRED OUTPUT FORMAT** (JSON):
{{
    "wants_training_path": true,
    "reasoning": "User explicitly said they want to explore the technical route further"
}}
"""

        try:
            from app.agent.llm_caller import LLMCaller

            classifier = LLMCaller[UserChoice](
                model_response_type=UserChoice
            )

            result, _ = await classifier.call_llm(
                llm=self._conversation_llm,
                llm_input=prompt,
                logger=self.logger
            )

            self.logger.info(
                f"User choice for '{requested_occupation}': wants_training_path={result.wants_training_path}, "
                f"reasoning={result.reasoning}"
            )

            # Clear pending occupation and guidance flag now that we've handled the follow-up
            state.pending_out_of_list_occupation = None
            state.pending_out_of_list_occupation_entity = None
            state.educational_guidance_shown = False

            if result.wants_training_path:
                # User wants to explore trainings → Use conversational handler to explain relevance
                # This will contextualize the trainings to the requested occupation (e.g., DJ)
                return await self._handle_training_conversation(
                    user_input=user_input,
                    state=state,
                    context=context,
                    trainings=trainings
                )
            else:
                # User wants to return to original recommendations
                from app.agent.recommender_advisor_agent.types import ConversationPhase
                state.conversation_phase = ConversationPhase.PRESENT_RECOMMENDATIONS

                return ConversationResponse(
                    reasoning=f"User chose to return to original recommendations after '{requested_occupation}' guidance",
                    message=t("messages", "recommenderAdvisor.returnToOriginal"),
                    finished=False
                ), all_llm_stats

        except Exception as e:
            self.logger.error(f"LLM-based choice classification failed: {e}, defaulting to training path")

            # Clear pending occupation and guidance flag
            state.pending_out_of_list_occupation = None
            state.pending_out_of_list_occupation_entity = None
            state.educational_guidance_shown = False

            # Fallback: assume they want trainings (safer) - use conversational handler
            return await self._handle_training_conversation(
                user_input=user_input,
                state=state,
                context=context,
                trainings=trainings
            )

    async def _handle_training_conversation(
        self,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext,
        trainings: list[SkillsTrainingRecommendation]
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """
        Handle conversational interaction about trainings using LLM.

        This handles:
        - Initial presentation of trainings after rejection
        - Follow-up questions about trainings
        - Concerns or clarifications about relevance
        - Requests for different options

        Uses LLM to respond contextually instead of static templates.
        """
        all_llm_stats: list[LLMStats] = []

        # Import here to avoid circular dependency
        from app.agent.recommender_advisor_agent.prompts import build_context_block
        from app.conversation_memory.conversation_formatter import ConversationHistoryFormatter
        from app.agent.simple_llm_agent.prompt_response_template import get_json_response_instructions

        # Build context
        skills_list = self._extract_skills_list(state)
        pref_vec_dict = state.preference_vector.model_dump() if state.preference_vector else {}
        conv_history = ConversationHistoryFormatter.format_to_string(context)
        recs_summary = self._build_recommendations_summary(state)

        context_block = build_context_block(
            skills=skills_list,
            preference_vector=pref_vec_dict,
            recommendations_summary=recs_summary,
            conversation_history=conv_history,
            country_of_user=state.country_of_user
        )

        # Build trainings summary
        trainings_summary = "\n".join([
            f"- **{trn.training_title}** ({trn.provider or 'Various providers'}): {trn.skill}\n  {trn.justification}\n  Duration: {trn.estimated_hours or '?'} hours | Cost: {trn.cost or 'Varies'}\n  Opens doors to: {', '.join(trn.target_occupations[:3]) if trn.target_occupations else 'Various careers'}"
            for trn in trainings
        ])

        prompt = context_block + f"""
## TRAINING DISCUSSION & RECOMMENDATIONS

The user is in the SKILLS_UPGRADE_PIVOT phase. They may have rejected some occupations or are exploring alternative paths.

**Available training recommendations:**
{trainings_summary}

**USER'S MESSAGE**: "{user_input}"

**YOUR TASK**:
Respond helpfully and contextually to the user's input. You should:

1. **If this is their first message in this phase** (they haven't seen trainings yet):
   - Present the training recommendations with empathy
   - Use format: "I understand [acknowledge their situation]. Here are skill-building opportunities..."
   - Then list the trainings with key details
   - End with: "Which of these interests you, or would you like to discuss what's holding you back?"

2. **If they're asking questions about trainings** (e.g., "how will these help with X?"):
   - Answer their specific question directly
   - Explain the connection/relevance they're asking about
   - Be honest if a training isn't directly related to their goal
   - Suggest next steps or alternatives

3. **If they're expressing concerns or confusion** (e.g., "these don't seem relevant"):
   - Acknowledge their concern
   - Explain the reasoning (if valid) or admit the mismatch
   - Ask what they're really looking for
   - Offer to explore other options

4. **If they're showing interest in a specific training**:
   - Provide more details about that training
   - Explain the career paths it enables
   - Ask if they want to pursue it

**TONE**:
- Conversational and supportive
- Honest about limitations (don't oversell connections that don't exist)
- Help them find a path forward
- Acknowledge their goals and concerns

**CRITICAL REQUIREMENTS**:
- Respond directly to what they said (don't ignore their question!)
- Don't just dump a static training list
- Be helpful and relevant
- Response must be JSON matching ConversationResponse schema
- Set `finished` to `false`

**FORBIDDEN - DO NOT HALLUCINATE**:
- NEVER provide specific contact information (phone numbers, emails, addresses) you don't have
- If asked for contact info: "I don't have verified contact details, but you can search online for [provider name] or visit their office in person"
- NEVER make up URLs, phone numbers, or addresses
- Be honest about what information you don't have

**REQUIRED OUTPUT FORMAT** (JSON):
{{
    "reasoning": "User is [what they're doing/asking]. Responding with [your approach].",
    "message": "[Your contextual, helpful response to their specific input]",
    "finished": false
}}

""" + get_json_response_instructions()

        # Call LLM
        try:
            response, llm_stats = await self._conversation_caller.call_llm(
                llm=self._conversation_llm,
                llm_input=ConversationHistoryFormatter.format_for_agent_generative_prompt(
                    model_response_instructions=prompt,
                    context=context,
                    user_input=user_input,
                ),
                logger=self.logger
            )
            all_llm_stats.extend(llm_stats)

            # Build metadata for UI
            metadata = self._build_metadata(
                interaction_type="training_conversation",
                trainings=[
                    {
                        "uuid": trn.uuid,
                        "skill": trn.skill,
                        "training_title": trn.training_title,
                        "provider": trn.provider,
                        "estimated_hours": trn.estimated_hours,
                        "cost": trn.cost,
                        "target_occupations": trn.target_occupations,
                        "justification": trn.justification,
                    }
                    for trn in trainings
                ]
            )

            response.metadata = metadata

            self.logger.info("Generated conversational response about trainings")
            return response, all_llm_stats

        except Exception as e:
            self.logger.error(f"LLM call failed for training conversation: {e}")
            # Fallback to simple template
            message = self._build_training_presentation(trainings, state)

            metadata = self._build_metadata(
                interaction_type="training_presentation",
                trainings=[
                    {
                        "uuid": trn.uuid,
                        "skill": trn.skill,
                        "training_title": trn.training_title,
                        "provider": trn.provider,
                        "estimated_hours": trn.estimated_hours,
                        "cost": trn.cost,
                        "target_occupations": trn.target_occupations,
                        "justification": trn.justification,
                    }
                    for trn in trainings
                ]
            )

            return ConversationResponse(
                reasoning="Training conversation (LLM failed - using fallback)",
                message=message,
                finished=False,
                metadata=metadata
            ), all_llm_stats

    def _build_training_presentation(
        self,
        trainings: list[SkillsTrainingRecommendation],
        state: RecommenderAdvisorAgentState,
        is_followup_to_educational_guidance: bool = False
    ) -> str:
        """
        Build the training recommendations message.

        Args:
            trainings: List of training recommendations to present
            state: Current agent state
            is_followup_to_educational_guidance: If True, user chose training path after educational guidance (use positive framing)
        """
        header = "**" + t("messages", "recommenderAdvisor.trainingRecommendationsHeader") + "**\n"
        if is_followup_to_educational_guidance:
            # User chose to explore training path - positive framing
            parts = [
                t("messages", "recommenderAdvisor.trainingIntroPositive") + "\n\n",
                header
            ]
        else:
            # User rejected occupations - empathetic framing
            parts = [
                t("messages", "recommenderAdvisor.trainingIntroEmpathetic1") + "\n\n",
                t("messages", "recommenderAdvisor.trainingIntroEmpathetic2") + "\n\n",
                header
            ]

        for i, trn in enumerate(trainings, 1):
            # Build header
            provider_info = f" ({trn.provider})" if trn.provider else ""
            hours_info = f", {trn.estimated_hours} {t('messages', 'recommenderAdvisor.labelHours')}" if trn.estimated_hours else ""
            parts.append(f"\n**{i}. {trn.training_title}**{provider_info}{hours_info}")

            # Cost info
            if trn.cost:
                parts.append(f"\n   - {t('messages', 'recommenderAdvisor.labelCost')}: {trn.cost}")

            # Justification
            parts.append(f"\n   - {trn.justification}")

            # What occupations it opens
            if trn.target_occupations:
                targets = ", ".join(trn.target_occupations[:3])
                parts.append(f"\n   - {t('messages', 'recommenderAdvisor.labelOpensDoorsTo')}: {targets}")

            # Delivery mode
            if trn.delivery_mode:
                mode_display = t(
                    "messages", f"recommenderAdvisor.deliveryModes.{trn.delivery_mode}",
                    trn.delivery_mode.replace("_", " ").capitalize()
                )
                parts.append(f"\n   - {t('messages', 'recommenderAdvisor.labelFormat')}: {mode_display}")

            # Track as presented
            if trn.uuid not in state.presented_trainings:
                state.presented_trainings.append(trn.uuid)

        parts.append("\n\n" + t("messages", "recommenderAdvisor.trainingConfidencePrompt"))
        parts.append("\n\n" + t("messages", "recommenderAdvisor.trainingHoldingBack"))

        return "".join(parts)
    
    async def _handle_no_trainings(
        self,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """Handle case where no training recommendations are available."""
        
        # This often means deeper issues - explore barriers
        message = t("messages", "recommenderAdvisor.noTrainingsBarriers")

        # Move to concerns phase to explore deeper
        state.conversation_phase = ConversationPhase.ADDRESS_CONCERNS
        
        return ConversationResponse(
            reasoning="No training recommendations available, exploring deeper barriers",
            message=message,
            finished=False
        ), []
    
    async def handle_training_interest(
        self,
        user_input: str,
        training_id: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """Handle when user expresses interest in a specific training."""
        
        # Mark interest
        state.mark_interest(training_id, UserInterestLevel.INTERESTED)
        state.current_focus_id = training_id
        state.current_recommendation_type = "training"
        
        # Get the training details
        training = None
        if state.recommendations:
            for trn in state.recommendations.skillstraining_recommendations:
                if trn.uuid == training_id:
                    training = trn
                    break
        
        if training is None:
            state.conversation_phase = ConversationPhase.ACTION_PLANNING
            return ConversationResponse(
                reasoning="Could not find training details",
                message=t("messages", "recommenderAdvisor.planGetStartedGeneric"),
                finished=False
            ), []

        # Build detailed training info and transition to action
        mode_display = t(
            "messages", f"recommenderAdvisor.deliveryModes.{training.delivery_mode or 'online'}",
            (training.delivery_mode or "online").replace("_", " ").capitalize()
        )
        targets = ', '.join(training.target_occupations[:4]) if training.target_occupations \
            else t("messages", "recommenderAdvisor.valMultipleCareerPaths")
        message = (
            t("messages", "recommenderAdvisor.trainingInterestHeader", training=training.training_title) + "\n\n"
            + f"**{t('messages', 'recommenderAdvisor.labelProvider')}:** {training.provider or t('messages', 'recommenderAdvisor.valVarious')}\n"
            + f"**{t('messages', 'recommenderAdvisor.labelDuration')}:** {training.estimated_hours or t('messages', 'recommenderAdvisor.valVaries')} {t('messages', 'recommenderAdvisor.labelHours')}\n"
            + f"**{t('messages', 'recommenderAdvisor.labelFormat')}:** {mode_display}\n"
            + f"**{t('messages', 'recommenderAdvisor.labelCost')}:** {training.cost or t('messages', 'recommenderAdvisor.valContactProvider')}\n\n"
            + f"**{t('messages', 'recommenderAdvisor.labelWhatYoullLearn')}**\n{training.justification}\n\n"
            + f"**{t('messages', 'recommenderAdvisor.labelCareerDoors')}**\n{targets}\n\n"
            + t("messages", "recommenderAdvisor.trainingStartPrompt")
        )

        state.conversation_phase = ConversationPhase.ACTION_PLANNING

        return ConversationResponse(
            reasoning=f"User interested in training: {training.training_title}",
            message=message,
            finished=False
        ), []

    async def _handle_user_intent(
        self,
        intent: UserIntentClassification,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext,
        trainings: list[SkillsTrainingRecommendation]
    ) -> tuple[ConversationResponse, list[LLMStats]] | None:
        """
        Handle classified user intent and update state accordingly.

        Returns:
            Tuple of (response, llm_stats) if intent triggers phase transition, None otherwise
        """
        self.logger.info(f"Classified intent in SKILLS_UPGRADE_PIVOT: {intent.intent} (reasoning: {intent.reasoning})")

        # Handle ACCEPT intent - user wants to commit to a training
        if intent.intent == "accept":
            return await self._handle_accept_training_intent(intent, user_input, state, context, trainings)

        # Handle RETURN_TO_RECOMMENDATIONS intent - user wants to go back to occupation recommendations
        elif intent.intent == "return_to_recommendations":
            return await self._handle_return_to_recommendations_intent(user_input, state, context)

        # Handle EXPLORE_OCCUPATION intent - user wants to explore one of the original occupations
        elif intent.intent == "explore_occupation":
            return await self._handle_explore_occupation_intent(intent, user_input, state, context)

        # Handle EXPLORE_TRAINING intent - user wants more details about a specific training
        elif intent.intent == "explore_training":
            return await self._handle_explore_training_intent(intent, user_input, state, context, trainings)

        # Handle CONCERN intent - user expressing worries about trainings
        elif intent.intent == "express_concern":
            return await self._handle_concern_intent(user_input, state, context)

        # Handle REQUEST_OUTSIDE_RECOMMENDATIONS - user wants something not in our lists
        elif intent.intent == "request_outside_recommendations":
            # Delegate to base handler's method
            return await self._handle_request_outside_recommendations(
                requested_occupation_name=intent.requested_occupation_name or t("messages", "recommenderAdvisor.thatOccupation"),
                user_input=user_input,
                state=state,
                context=context
            )

        # For other intents (ask_question, other), let LLM handle conversationally
        return None

    async def _handle_accept_training_intent(
        self,
        intent: UserIntentClassification,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext,
        trainings: list[SkillsTrainingRecommendation]
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """Handle user accepting/committing to a training."""
        # Try to identify which training they want
        target_training = None

        if intent.target_recommendation_id:
            # Find training by UUID
            for trn in trainings:
                if trn.uuid == intent.target_recommendation_id:
                    target_training = trn
                    self.logger.info(f"Identified training by UUID {intent.target_recommendation_id}: {trn.training_title}")
                    break

        if target_training:
            # Specific training identified - mark interest and transition to ACTION_PLANNING
            state.current_focus_id = target_training.uuid
            state.current_recommendation_type = "training"
            state.mark_interest(target_training.uuid, UserInterestLevel.INTERESTED)

            # Transition to ACTION_PLANNING phase
            state.conversation_phase = ConversationPhase.ACTION_PLANNING

            self.logger.info(f"User committed to training '{target_training.training_title}', transitioning to ACTION_PLANNING")

            # If we have an action planning handler, immediately invoke it for seamless transition
            if self._action_planning_handler:
                self.logger.info("Immediately invoking action planning handler for seamless experience")
                return await self._action_planning_handler.handle(user_input, state, context)

            # Fallback: return transition message
            return ConversationResponse(
                reasoning=f"User committed to training '{target_training.training_title}', transitioning to ACTION_PLANNING",
                message=t("messages", "recommenderAdvisor.planGetStartedNamed", training=target_training.training_title),
                finished=False
            ), []
        else:
            # Couldn't identify specific training - ask for clarification
            self.logger.warning("User accepted a training but couldn't identify which one")
            return ConversationResponse(
                reasoning="User expressed commitment but training not identified",
                message=t("messages", "recommenderAdvisor.whichTrainingPursue"),
                finished=False
            ), []

    async def _handle_return_to_recommendations_intent(
        self,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """Handle user wanting to return to original occupation recommendations."""
        # Transition back to PRESENT_RECOMMENDATIONS phase
        state.conversation_phase = ConversationPhase.PRESENT_RECOMMENDATIONS

        self.logger.info("User wants to return to original occupation recommendations, transitioning to PRESENT_RECOMMENDATIONS")

        # If we have a present handler, immediately invoke it for seamless transition
        if self._present_handler:
            self.logger.info("Immediately invoking present handler for seamless experience")
            return await self._present_handler.handle(user_input, state, context)

        # Fallback: return transition message
        return ConversationResponse(
            reasoning="User wants to return to original occupation recommendations",
            message=t("messages", "recommenderAdvisor.returnLookAgain"),
            finished=False
        ), []

    async def _handle_explore_occupation_intent(
        self,
        intent: UserIntentClassification,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """Handle user wanting to explore one of the original occupation recommendations."""
        # Determine which occupation they want to explore
        target_occ = None

        if intent.target_occupation_index and state.recommendations:
            idx = intent.target_occupation_index - 1  # Convert to 0-indexed
            occupations = state.recommendations.occupation_recommendations
            if 0 <= idx < len(occupations):
                target_occ = occupations[idx]
                self.logger.info(f"Identified occupation by index {intent.target_occupation_index}: {target_occ.occupation}")

        elif intent.target_recommendation_id:
            target_occ = state.get_recommendation_by_id(intent.target_recommendation_id)
            if target_occ:
                self.logger.info(f"Identified occupation by UUID {intent.target_recommendation_id}: {target_occ.occupation}")

        if target_occ:
            # Set focus and mark as exploring
            state.current_focus_id = target_occ.uuid
            state.current_recommendation_type = "occupation"
            state.mark_interest(target_occ.uuid, UserInterestLevel.EXPLORING)

            # Transition to CAREER_EXPLORATION phase
            state.conversation_phase = ConversationPhase.CAREER_EXPLORATION

            self.logger.info(f"Transitioning to CAREER_EXPLORATION for {target_occ.occupation}")

            # If we have an exploration handler, immediately invoke it for seamless transition
            if self._exploration_handler:
                self.logger.info("Immediately invoking exploration handler for seamless experience")
                return await self._exploration_handler.handle(user_input, state, context)

            # Fallback: just return transition message
            return ConversationResponse(
                reasoning=f"User wants to explore {target_occ.occupation}, transitioning to EXPLORATION phase",
                message=t("messages", "recommenderAdvisor.tellMeMoreAbout", occupation=target_occ.occupation),
                finished=False
            ), []

        # Couldn't identify which occupation - stay in current phase
        self.logger.warning(f"Could not identify target occupation from intent. target_occupation_index={intent.target_occupation_index}, target_recommendation_id={intent.target_recommendation_id}")
        return None

    async def _handle_explore_training_intent(
        self,
        intent: UserIntentClassification,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext,
        trainings: list[SkillsTrainingRecommendation]
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """Handle user wanting more details about a specific training."""
        # Try to identify which training
        target_training = None

        if intent.target_recommendation_id:
            for trn in trainings:
                if trn.uuid == intent.target_recommendation_id:
                    target_training = trn
                    self.logger.info(f"Identified training by UUID: {trn.training_title}")
                    break

        if target_training:
            # Provide detailed training information
            # Stay in SKILLS_UPGRADE_PIVOT phase (just providing more info, not committing)
            mode_display = t(
                "messages", f"recommenderAdvisor.deliveryModes.{target_training.delivery_mode or 'online'}",
                (target_training.delivery_mode or "online").replace("_", " ").capitalize()
            )
            targets = ', '.join(target_training.target_occupations[:4]) if target_training.target_occupations \
                else t("messages", "recommenderAdvisor.valMultipleCareerPaths")
            message = (
                t("messages", "recommenderAdvisor.trainingExploreHeader", training=target_training.training_title) + "\n\n"
                + f"**{t('messages', 'recommenderAdvisor.labelProvider')}:** {target_training.provider or t('messages', 'recommenderAdvisor.valVariousProviders')}\n"
                + f"**{t('messages', 'recommenderAdvisor.labelDuration')}:** {target_training.estimated_hours or t('messages', 'recommenderAdvisor.valVaries')} {t('messages', 'recommenderAdvisor.labelHours')}\n"
                + f"**{t('messages', 'recommenderAdvisor.labelFormat')}:** {mode_display}\n"
                + f"**{t('messages', 'recommenderAdvisor.labelCost')}:** {target_training.cost or t('messages', 'recommenderAdvisor.valContactProviderPricing')}\n\n"
                + f"**{t('messages', 'recommenderAdvisor.labelWhatYoullLearn')}**\n{target_training.justification}\n\n"
                + f"**{t('messages', 'recommenderAdvisor.labelCareerDoors')}**\n{targets}\n\n"
                + t("messages", "recommenderAdvisor.trainingPursueOrMore")
            )

            return ConversationResponse(
                reasoning=f"Providing detailed information about {target_training.training_title}",
                message=message,
                finished=False
            ), []

        # Couldn't identify specific training - let LLM handle conversationally
        self.logger.warning("User wants to explore a training but couldn't identify which one")
        return None

    async def _handle_concern_intent(
        self,
        user_input: str,
        state: RecommenderAdvisorAgentState,
        context: ConversationContext
    ) -> tuple[ConversationResponse, list[LLMStats]]:
        """Handle user expressing concerns about trainings."""
        # Transition to ADDRESS_CONCERNS phase
        state.conversation_phase = ConversationPhase.ADDRESS_CONCERNS

        self.logger.info("User expressed concern about trainings, transitioning to ADDRESS_CONCERNS phase")

        # If we have a concerns handler, immediately invoke it for seamless transition
        if self._concerns_handler:
            self.logger.info("Immediately invoking concerns handler for seamless experience")
            return await self._concerns_handler.handle(user_input, state, context)

        # Fallback: just return transition message
        return ConversationResponse(
            reasoning="User expressed a concern about trainings, transitioning to CONCERNS phase to address it",
            message=t("messages", "recommenderAdvisor.hearYouTalkConcern"),
            finished=False
        ), []
