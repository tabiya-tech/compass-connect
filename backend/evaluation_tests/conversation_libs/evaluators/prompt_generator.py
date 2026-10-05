import textwrap

from evaluation_tests.conversation_libs.evaluators.evaluation_result import EvaluationType


class PromptGenerator:
    """
    Generates the prompt used by the evaluators.
    """

    @staticmethod
    def _get_criteria_string(criteria: EvaluationType):
        match criteria:
            case EvaluationType.CONCISENESS:
                return textwrap.dedent("""
                            Could any of the responses made by EVALUATED_AGENT be expressed more concisely without 
                            losing meaning? Are there any phrases said by EVALUATED_AGENT that are repeated 
                            unnecessarily within this segment of the conversation? Are all the questions by 
                            EVALUATED_AGENT focused and easy to understand?
                        """)
            
            case EvaluationType.FOCUS:
                return textwrap.dedent("""
                            Did the EVALUATED_AGENT lose focus on the topic of the conversation and on its
                            task of investigating the experiences and skill of the user? Did the EVALUATED_AGENT give into
                            a topic of conversation that is different from the experience and skill investigation?
                        """)

            case EvaluationType.SUMMARY_CONSISTENCY:
                return textwrap.dedent("""
                Evaluation Criteria:
                Consistency - the factual alignment between the new summary and the current summary and conversation. 
                A factually consistent new summary contains only statements that are entailed by the current summary and conversation.
                new summaries that contained hallucinated facts are penalized.
                
                Evaluation Steps:

                1. Read the current summary and conversation carefully and identify the main facts and details they present.
                2. Read the new summary and compare it to the current summary and conversation. Check if the new summary contains any factual errors that are not supported by the current summary and conversation.
                3. Assign a score for consistency from of 1 to 5, where 1 is the lowest and 5 is the highest based on the Evaluation Criteria.
                """)

            case EvaluationType.SUMMARY_RELEVANCE:
                return textwrap.dedent("""
                Evaluation Criteria:
                Relevance - selection of important content from the current summary and conversation.
                The new summary should include only important information from the current summary and conversation.
                new summaries which contained redundancies and excess information are penalized.
                
                Evaluation Steps:

                1. Read the summary and the current summary and conversation carefully.
                2. Compare the new summary to the current summary and conversation and identify the main points of the current summary and conversation.
                3. Assess how well the new summary covers the main points of the current summary and conversation, and how much irrelevant or redundant information it contains.
                4. Assign a relevance score from of 1 to 5, where 1 is the lowest and 5 is the highest based on the Evaluation Criteria.
                """)
            case EvaluationType.SINGLE_LANGUAGE:
                return textwrap.dedent("""
                Evaluation Criteria:
                
                Single - Language - Did the EVALUATED_AGENT maintain the same language throughout the conversation? 
                Even if the SIMULATED_USER used a different language.
                
                Evaluation Steps:
                1. Read the conversation carefully and identify the language used by the EVALUATED_AGENT.
                2. Check if the conversation was in the same language throughout (eg: English, Spanish, French, Swahili, etc)..
                3. Assign a score of 100 if the conversation was in the same language throughout, or 0 otherwise.
                """)
            case EvaluationType.NON_PRIORITY_SECTOR_RESPONSE_QUALITY:
                return textwrap.dedent("""
                Evaluation Criteria:

                The EVALUATED_AGENT is a career explorer that answers questions about careers both within and outside
                priority sectors. For non-priority sectors (e.g. software, IT, healthcare, aeronautical engineering),
                the agent should use web search to provide substantive, informative career advice.

                Score highly if the EVALUATED_AGENT:
                - Gives a substantive response with useful career information (roles, pathways, salary context, employers)
                - Stays on topic and addresses the user's career question
                - Does not deflect or redirect the user to pick a different sector

                Score low if the EVALUATED_AGENT:
                - Says it cannot help or redirects to "pick one of our sectors"
                - Gives a generic error or placeholder response
                - Provides no useful career-specific information
                """)
            case EvaluationType.MEMORY_RECALL_ACCURACY:
                return textwrap.dedent("""
                Evaluation Criteria:
                Memory Recall Accuracy - did the EVALUATED_AGENT accurately recall the specific details
                of a past experience when asked by the user, without hallucinating or blending details
                from a different experience?

                The conversation contains TWO distinct experiences:
                  1. A PAID experience: Data Entry Clerk at a telecom company.
                     Duties: entering customer data into systems, filing forms, organizing records.
                  2. A VOLUNTEERING experience: Survey Enumerator at an NGO.
                     Duties: asking questions to respondents, recording answers, occasionally
                     convincing hesitant respondents to participate.

                After summarization has occurred, the user asks the EVALUATED_AGENT to recall
                what they said they volunteered for.

                A CORRECT response:
                  - Describes the Survey Enumerator / NGO volunteering role accurately
                  - Does NOT mention telecom, data entry, filing forms, or customer records
                  - May mention "asking questions", "recording answers", "convincing respondents"

                A HALLUCINATED / BLENDED response:
                  - Mixes in details from the paid Data Entry Clerk role (telecom, filing, data entry)
                  - Invents duties not mentioned in the conversation
                  - Describes the wrong experience entirely

                Evaluation Steps:
                1. Find the turn where the user asks to be reminded about their volunteering experience.
                2. Read the EVALUATED_AGENT's response to that question.
                3. Check if the response accurately describes the Survey Enumerator / NGO role only.
                4. Penalise any blending of paid experience details into the volunteering recall.
                5. Assign a score from 0 to 100:
                   - 0–30: full hallucination or complete blend of the wrong experience
                   - 31–60: partial blend (some correct details, some from the wrong experience)
                   - 61–85: mostly correct with minor inaccuracies
                   - 86–100: fully accurate recall with no hallucinated or blended details
                """)
            case EvaluationType.RECAP_FIELD_ACCURACY:
                return textwrap.dedent("""\
                Evaluation Criteria:
                Recap Field Accuracy - when the EVALUATED_AGENT provides a final recap of collected
                work experiences, it must include ONLY the five structured fields:
                  title, work_type, company, location, start_date / end_date.

                The recap must NOT include any of the following:
                  - duties, responsibilities, or tasks described during the conversation
                  - skills, competencies, or achievements
                  - any information that was mentioned in the conversation but is NOT one of the five fields

                The conversation contains experiences where the user explicitly described duties
                (e.g. "entering data", "filing forms", "asking questions"). A compliant recap
                omits all of these and only lists the five structured fields per experience.

                Evaluation Steps:
                1. Find the turn(s) where the EVALUATED_AGENT provides the final recap.
                2. For each experience in the recap, check whether the agent included anything
                   beyond title, work_type, company, location, and date range.
                3. Penalise every duty, skill, or responsibility that appears in the recap.
                4. Assign a score from 0 to 100:
                   - 0–30: recap contains extensive duties/skills — clear embellishment
                   - 31–60: recap contains some duties/skills mixed with structured fields
                   - 61–85: recap is mostly clean with one or two stray details
                   - 86–100: recap contains ONLY the five structured fields, no duties or skills
                """)
            case _:
                raise NotImplementedError()

    @staticmethod
    def _get_example_response(criteria: EvaluationType):
        match criteria:
            case EvaluationType.CONCISENESS:
                return textwrap.dedent("""
                            The conversation is somewhat concise, but the EVALUATED_AGENT repeats instructions, 
                    and the SIMULATED_USER could ask more focused questions.
                        """)
            
            case EvaluationType.FOCUS:
                return textwrap.dedent("""
                            The conversation is somewhat focused, but the EVALUATED_AGENT allows the user to drift off at times.
                        """)

            case EvaluationType.SUMMARY_CONSISTENCY:
                return textwrap.dedent("""
               The summary is somewhat consistent, but there are some facts that do not exist on the current conversation.
                """)

            case EvaluationType.SUMMARY_RELEVANCE:
                return textwrap.dedent("""
                The summary is somewhat relevant to the current conversation.
                """)
            case EvaluationType.SINGLE_LANGUAGE:
                return textwrap.dedent("""
                The language used in the conversation is somewhat consistent and it is 'Spanish' mixed with 'English'.
                Here are a list of cases where the language deviated.
                
                - EVALUATED_AGENT used 'Hello' instead of 'Hola' at message 2.
                """)
            case EvaluationType.NON_PRIORITY_SECTOR_RESPONSE_QUALITY:
                return textwrap.dedent("""
                The response provides useful career information about the non-priority sector, including roles,
                pathways, and context, without deflecting to priority sectors.
                """)
            case EvaluationType.MEMORY_RECALL_ACCURACY:
                return textwrap.dedent("""
                The agent correctly recalled the volunteering experience as Survey Enumerator at an NGO,
                mentioning asking questions and recording answers, without mixing in any details from
                the paid Data Entry Clerk role at the telecom company.
                """)
            case EvaluationType.RECAP_FIELD_ACCURACY:
                return textwrap.dedent("""\
                The agent's recap listed only title, work type, dates, company, and location for each
                experience. No duties, responsibilities, or skills were included in the recap.
                """)
            case _:
                raise NotImplementedError()

    @staticmethod
    def generate_prompt(conversation: str, criteria: EvaluationType) -> str:
        """
        Generates the prompt to be used in the evaluators.
        """
        criteria_string = PromptGenerator._get_criteria_string(criteria)
        example_response = PromptGenerator._get_example_response(criteria)
        if criteria_string is None or example_response is None:
            raise ValueError("Invalid criteria value")

        template = textwrap.dedent(f"""
            You are assessing a conversation between a human (SIMULATED_USER) and a job 
            counselor AI chatbot (EVALUATED_AGENT). {criteria_string}
            
            Rate it from 0 to 100, 0 being worst 100 being best.
            
            Example: a score of 50, with the reason: "{example_response}"
    
            Conversation Data:
            [BEGIN DATA]
            [Conversation]: {conversation}
            [END DATA] 
        """)

        return template

    @staticmethod
    def generate_summary_prompt(conversation: str, current_summary: str, new_summary: str,
            criteria: EvaluationType) -> str:
        """
        Generates the prompt to be used in the summary evaluators.
        """
        criteria_string = PromptGenerator._get_criteria_string(criteria)
        example_response = PromptGenerator._get_example_response(criteria)
        if criteria_string is None or example_response is None:
            raise ValueError("Invalid criteria value")

        template = textwrap.dedent(f"""
            You are assessing a summary that was created from the original conversation. 
            {criteria_string}
            
            Example: a score of 3, with the reason: "{example_response}"
    
            [BEGIN DATA]
            [Current Summary]: {current_summary}
            [Current Conversation]: {conversation}
            [New Summary]: {new_summary}
            [END DATA] 
        """)

        return template
