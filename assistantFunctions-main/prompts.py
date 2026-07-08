call_summary_agent_to_user_prompt = (""" 
Given the transcript of an Agent-Student conversation audio file:

Your task is to analyze the conversation and generate a JSON object.

**1. Summary for Student:**
*   Create a summary of the conversation that the Agent can send to the Student as a follow-up.
*   The summary should be phrased as a polite reminder from the agent to the student, reflecting what was discussed. For example: "Just to recap our conversation, we discussed your interest in..." or "Following up on our call, we talked about..."
*   If the `dangerous_content` flag (see below) is "dangerous", the summary should be an empty string `""`.
* Do not mention if call was ended abruptly or without conclusion.

**2. Executive summary for manager to review after the call:**
*   Create a summary of the conversation that the Agent and  Student for manager to review.
*   The summary should be phrased as  reflecting what was discussed. 
*   Mention is summary if call was concluded or was ended abruptly.
*   Mention the city or near by city where the student is located or can visit the office.

**3. Conversation Flag:**
Flag the conversation based on the student's engagement with these key topics:
    a.  Interest in specific study courses/fields.
    b.  Interest in studying in a particular country.
    c.  Inquiries about study visa processes.
    d.  Inquiries about budget/finances for studying abroad.

*   **Potential Customer:** The student actively asks questions or expresses clear interest in **at least one** of the key topics (a, b, c, or d).
*   **Not a Potential Customer:** The student shows no interest, does not ask questions about any of the key topics, explicitly states they are not interested in studying abroad, or ends the conversation abruptly before any key topics can be meaningfully discussed.
*   **May be Potential Customer:** The student shows slight, vague, or indirect interest in one or more key topics, but it's not a strong or active inquiry.
*   **Random Conversation:** The student primarily asks irrelevant or random, unrelated questions, with no substantial discussion on any key topics.

*   **Clarification:** If the student shows interest in courses/country (topics a or b) but visa/budget (topics c or d) are not discussed, they can still be a "Potential Customer" or "May be Potential Customer" based on the strength of their interest in a/b.

**4. Dangerous Content Flag:**
*   **dangerous:** If the conversation contains dangerous, abusive, or sexually explicit content.
*   **normal:** If the conversation does not contain such content.

** Instructions **
*   **For point 1 and 2 Focus exclusively on:**
    *   The student's expressed interest in specific courses or fields of study, and the intended country.
    *   Any discussion regarding study visa processes for the intended country.
    *   Any discussion regarding budget planning for studying in the intended country.
    *   If student express interests in visiting the office or meeting in person, add reminder to bring all documents along.
    *   If student express interests in scheduling zoom, google meet or online call/meeting via any medium, add reminder keep all documents handy during the call.
*   **Omit:** All introductions, AI confirmations (e.g., "Okay, I understand"), and non-academic small talk.
*   **Prioritize:** Accuracy and completeness based *only* on the conversation. Do not alter or invent information.
*   **Length:** Be concise. Only exceed 50 words if absolutely necessary to capture essential details on the focused topics. Do not provide a verbatim transcript.

**Additional Spelling Guidance:**
*   Please note: The correct spelling is "Canam Consultants". If, in any summary you generate, you come across words like "kaman Consultants," "canum Consultants," or similar variations, it is most likely "Canam Consultants." Please ensure you use the correct spelling "Canam Consultants" in such instances.

**Output Format:**
*   **Strictly output ONLY a JSON object.** No other introductory or explanatory text.
*   The JSON object must conform to this structure:
    ```json
    {
      "summary": "[summary of conversation phrased as a reminder, or empty string if dangerous]",
     "executive_summary": "[summary of conversation for manager to review ]",
      "conversation_flag": "[Potential Customer | Not a Potential Customer | May be Potential Customer | Random Conversation]",
      "dangerous_content": "[dangerous | normal]"
    }
    ```
""")
