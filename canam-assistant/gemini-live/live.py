## pip install --upgrade google-genai==0.3.0##
import asyncio
import json
import os
import websockets   
from google import genai
import base64
from google.genai import types

MODEL = "gemini-2.0-flash-live-001"

# client = genai.Client(
#     vertexai=True, 
#     project='docboard-561bf', 
#     location='us-central1'
# )


GEMINI_API_KEY = os.environ.get('GOOGLE_API_KEY')
client = genai.Client(api_key=GEMINI_API_KEY)

system_prompt = '''
You are a helpful and knowledgeable AI assistant designed to guide students in shortlisting suitable courses based on their individual profiles and preferences. Your goal is to gather relevant information from the student through a series of questions and utilize available tools to filter course options effectively. 
Each prefrence is a filter which can be used to filter the courses.

Given below are the points for each country which should be kept in mind:
Germany: If student has cgpa less that 75 and wants to do graduation than call applyFilter for degree 16 because student must join foundation course.


Please follow the steps below in sequence:

Country of Interest: Begin by asking the student: "Which country are you interested in studying in?" Wait for the student to respond.

Degree Level: Once the country is established, inquire about the degree level: "Are you looking to pursue a Bachelor's (graduation), Master's, or PhD degree?" Wait for the student to respond.
if country is germany and user has cgpa less that 75% then degree should be foundation course

Desired Job Roles (Tool Usage - ShowFilter): Use the ShowFilter tool to present the job options to the student. Say this to the student "To help me narrow down suitable courses, I need to understand your career aspirations. I am going to use tool to show you available job options". Then, use the following JSON to invoke the tool:

Generated json
{
  "filter": "Jobs"
}
After using the tool to present the job options, ask the student: "Which job roles are you targeting after completing your studies? Please select from the options presented." Wait for the student to respond with their desired job roles.
Note: Do not present any job option from your end. Let tool show the job options

Maximum Budget: Ask the student: "What is the maximum budget you have allocated for your tuition fees and living expenses per year?" Wait for the student to respond.

Marks in Last Completed Degree: Ask the student: "What were your marks or GPA in your last completed degree (e.g., high school diploma for Bachelor's, Bachelor's degree for Master's, Master's degree for PhD)?" Wait for the student to respond.
If student wants to do graduation degree and his marks are less than 75% then alert student that he would need to do foundation course and change degree to 16 which is for foundation course.

IELTS Score: Ask the student: "What is your IELTS score?" Wait for the student to respond.

Applying Filters (Tool Usage - ApplyFilter): After collecting all the necessary information, use the ApplyFilter tool to filter the course options based on the student's responses. For each criteria below create ApplyFilter with appropriate values.

Country

Degree Level

Job Roles

Budget (Tuition Fees)

Marks in Last Completed Degree

IELTS Score

For example, if the student indicated they are interested in "Computer Science" and "Data Science" job roles, you would use the ApplyFilter tool as follows:

Generated json
{
    "filter": "Jobs",
    "values": ["Computer Science", "Data Science"]
}

Presenting Shortlisted Courses: Apply filter as soon as filter is identified.

Clarification and Further Assistance: Throughout the interaction, be prepared to answer the student's questions and provide further assistance as needed. Offer to refine the search criteria if the initial shortlist is too broad or narrow.

Important Considerations:

Error Handling: If the student provides invalid input or if a tool fails to execute properly, provide a helpful error message and guide the student on how to correct the issue.

Tool Limitations: Be aware of the limitations of the available tools and inform the student accordingly.

Flexibility: While following the sequence is important, be flexible and adapt to the student's individual needs and preferences.

Example Interaction:

Agent: "Hello! I'm here to help you shortlist suitable courses for your studies. Which country are you interested in studying in?"

Student: "germany"

( Agent uses applyFilter to get courses of canada)

Agent: "Are you looking to pursue a Bachelor's (graduation), Master's, or PhD degree?"

Student: "Master's"

( Agent uses applyFilter to get courses in masters)

Agent: "To help me narrow down suitable courses, I need to understand your career aspirations. I am going to use tool to show you available job options"

(Agent uses ShowFilter to show list of jobs)

Agent: "Which job roles are you targeting after completing your studies? Please select from the options presented."

Student: "Data Scientist, Machine Learning Engineer"

( Agent uses applyFilter to get courses which matches jobs Data Scientist, Machine Learning Engineer)

Agent: "What is the maximum budget you have allocated for your tuition fees and living expenses per year?"

Student: "$40,000"

( Agent uses applyFilter to get courses whose fees is less than 40000)

Agent: "What were your marks or GPA in your Bachelor's degree?"

Student: "8.5 GPA"

( Agent uses applyFilter to get courses which has gpa of 8.5 )

Agent: "What is your IELTS score?"

Student: "7.0"

( Agent uses applyFilter to get courses which has ielts requirements of 7.0)




Note 1: user might provide you all or some parts of information in one answer. In that case 
    a) do not ask about the information again. 
    b) apply multiple filters. One each for provides information
Example:
    I want to go to germany for graduation. In this case country and degree are given so do not ask for them
Exception: Only exception to above is jobs. You must always prompt user for jobs.

Note 2: User might want to change his preferences. Allow user to do that.  User should be able to change the preferences
and see results after applying filter.

Note 3: If the applyFilter yielded no result. Let the user know about it and ask user same question again so that he can change preference.
Do not ask next preference until apply filter has result.
'''


showFilter_declaration = {
  "name": "showFilter",
  "description": '''Call this function to show filter to user to make choice''',
  "parameters": {
    "type": "object",
    "properties": {
      "filter": {
        "type": "string",
        "description": "name of the filter which must be shown to user"
      }
    },
    "required": [
      "filter"
    ]
  }
}

applyFilter_declaration = {
  "name": "applyFilter",
  "description": '''Call this function to apply filter
  For country filter is country and country value can be "germanny", "canada"
  For degree filter is degree and country value can be "3" for graduation, "8" for masters and "16" for foundation course
  for jobs filter is "in_demand_tags" and value is array of jobs selected by user
  for budget filter is "fees" and value is "fees" as mentioned by user
  for cgpa filter is "cgpa" and value is "cgpa" as mentioned by user
  for ielts filter is "ielts" and value is "ielts" as mentioned by user
  ''',
  "parameters": {
    "type": "object",
    "properties": {
      "filter": {
        "type": "string",
        "description": "name of the filter which must be shown to user"
      },
      "values": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Filter values to be applied"
      }
    },
    "required": [
      "filter",
      "values"
    ]
  }
}



def showFilter(args:dict) -> None :
    return {}


def applyFilter(args:dict) -> None :
    return {
        "MessageForAI": "Let UI present the options and wait for choices made by user."
    }


tools = [{"function_declarations": [showFilter_declaration, applyFilter_declaration]}]



async def gemini_session_handler(client_websocket: websockets.WebSocketServerProtocol):
    """Handles the interaction with Gemini API within a websocket session.

    Args:
        client_websocket: The websocket connection to the client.
    """
    try:
        config_message = await client_websocket.recv()
        config_data = json.loads(config_message)
        config = config_data.get("setup", {})
        config["system_instruction"] = types.Content(
            parts=[
                types.Part(
                    text=system_prompt
                )
            ]
        )

        config["tools"] = tools
        
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("Connected to Gemini API")

            async def send_to_gemini():
                """Sends messages from the client websocket to the Gemini API."""
                try:
                  async for message in client_websocket:
                      try:
                          data = json.loads(message)
                          if "realtime_input" in data:
                              for chunk in data["realtime_input"]["media_chunks"]:
                                  if chunk["mime_type"] == "audio/pcm":
                                        await session.send_realtime_input(
                                            media=types.Blob(
                                                data=chunk["data"], 
                                                mime_type="audio/pcm")
                                            )
                                      
                                  elif chunk["mime_type"] == "image/png":
                                        await session.send(input={
                                            "mime_type": "image/png", 
                                            "data": chunk["data"]
                                        })
                          else:
                              await session.send_client_content(
                                  turns={"role": "user", 
                                         "parts": [
                                             {"text": data["text"]}
                                        ]}, turn_complete=True
                              )
                      except Exception as e:
                          print(f"Error sending to Gemini: {e}")
                  print("Client connection closed (send)")
                except Exception as e:
                     print(f"Error sending to Gemini: {e}")
                finally:
                   print("send_to_gemini closed")



            async def receive_from_gemini():
                """Receives responses from the Gemini API and forwards them to the client, looping until turn is complete."""
                prompt_total = 0
                response_total = 0
                try:
                    while True:
                        try:
                            async for response in session.receive():
                                if response.usage_metadata:
                                    try:
                                        prompt_total += response.usage_metadata.prompt_token_count
                                        response_total += response.usage_metadata.response_token_count
                                        print(f"Prompt tokens: {prompt_total}, Response tokens: {response_total}")
                                    except:
                                        pass
                                        
                                if response.tool_call:
                                    print("Function call received")    
                                    function_calls = []
                                    fcRet = None
                                    for fc in response.tool_call.function_calls:
                                        fcRet = applyFilter(fc.args)
                                        response = types.FunctionResponse(
                                            id = fc.id,
                                            name = fc.name,
                                            response = fcRet
                                        )
                                        function_calls.append(response)
                                        await client_websocket.send(json.dumps({
                                                "action": "functionCall",
                                                "name": fc.name,
                                                "args": fc.args,
                                            }))
                                    await session.send_tool_response(function_responses=function_calls) 
                                    continue

                                
                                if response.server_content and response.server_content.interrupted:
                                    print("Interrupted")    
                                    await client_websocket.send(json.dumps({
                                                "interrupted": True,
                                            }))
                                    continue

                                model_turn = None
                                try:
                                    if response.server_content and response.server_content.model_turn:
                                        model_turn = response.server_content.model_turn
                                except:
                                    pass
                                if model_turn:
                                    for part in model_turn.parts:
                                        if hasattr(part, 'text') and part.text is not None:
                                            await client_websocket.send(json.dumps({"text": part.text}))
                                        elif hasattr(part, 'inline_data') and part.inline_data is not None:
                                            base64_audio = base64.b64encode(part.inline_data.data).decode('utf-8')
                                            await client_websocket.send(json.dumps({
                                                "audio": base64_audio,
                                            }))

                                if response.server_content and response.server_content.turn_complete:
                                    print("Model turn completed")
                                    await client_websocket.send(json.dumps({
                                        "endOfTurn": True,
                                    }))
                        except websockets.exceptions.ConnectionClosedOK:
                            print("Client connection closed normally (receive)")
                            break  # Exit the loop if the connection is closed
                        except Exception as e:
                            print(f"Error receiving from Gemini: {e}")
                            break 

                except Exception as e:
                      print(f"Error receiving from Gemini: {e}")
                finally:
                      print("Gemini connection closed (receive)")


            # Start send loop
            send_task = asyncio.create_task(send_to_gemini())
            # Launch receive loop as a background task
            receive_task = asyncio.create_task(receive_from_gemini())
            await asyncio.gather(send_task, receive_task)


    except Exception as e:
        print(f"Error in Gemini session: {e}")
    finally:
        print("Gemini session closed.")


async def main() -> None:
    async with websockets.serve(gemini_session_handler, "localhost", 9083):
        print("Running websocket server localhost:9083...")
        await asyncio.Future()  # Keep the server running indefinitely


if __name__ == "__main__":
    asyncio.run(main())