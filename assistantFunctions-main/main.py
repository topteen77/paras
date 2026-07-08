import base64
from datetime import datetime, timezone
import json
import os
import time
import uuid
import functions_framework
import requests
import google.generativeai as genai
from google.cloud import firestore
from twilio.rest import Client
from prompts import call_summary_agent_to_user_prompt
from google.cloud import bigquery
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Cc, Bcc, Attachment, FileContent, FileName, FileType, Disposition
from google.cloud import pubsub_v1
import random
import string
from common.config import (
    AGENT_EMAIL_ID,
    SENDER_EMAIL_USERNAME,
    SENDER_EMAIL_PASSWORD,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    ELEVENLABS_API_KEY,
    GENAI_API_KEY,
    GENAI_MODEL_NAME,
    TWILIO_WHATSAPP_PHONE_NUMBER,
    WHATSAPP_TEMPLATE_ACTION_REQUIRED_NAME,
    WEB_SERVER_URL,
    PROJECT_ID,
    BIG_QUERY_DATASET_ID
)

def generate_code():
    try:
        # Generate 6-character alphanumeric (alternating letter-digit) + '-' + 3 uppercase letters
        part1 = ''.join(random.choice(string.ascii_uppercase) + random.choice(string.digits) for _ in range(3))
        part2 = ''.join(random.choices(string.ascii_uppercase, k=3))
        code = f"{part1}-{part2}"
        print(f"[generate_code] Generated code: {code}")
        return code
    except Exception as e:
        print(f"[generate_code] Error: {e}")
        return "ERR-XXX"

def log_call_to_firestore_initiated(call_sid: str, to_number: str, internal_id: str):
    try:
        print(f"[log_call_to_firestore_initiated] internal_id: {internal_id}, call_sid: {call_sid}, to_number: {to_number}")
        if not call_sid or not to_number or not internal_id:
            print(f"[log_call_to_firestore_initiated] Missing required parameters.")
            return
        db = firestore.Client()
        doc_ref = db.collection('conversation-history').document(to_number)
        doc = doc_ref.get()
        if not doc.exists:
            data = {
                'to_phone_number': to_number,
                'timestamp': datetime.now(timezone.utc),
            }
            doc_ref.set(data, merge=True)
        doc_ref = db.collection('conversation-history').document(to_number).collection('calls').document(internal_id)
        doc = doc_ref.get()
        retry_count = 0
        if doc.exists:
            doc_dict = doc.to_dict()
            retry_count = doc_dict.get('retry_count', 0) if doc_dict else 0
        doc_ref.set({
            'call_sid': call_sid,
            'from_phone_number': TWILIO_PHONE_NUMBER,
            'status': 'initiated',
            'conversation_id': '',
            "internal_id": internal_id,
            'timestamp': datetime.now(timezone.utc),
            'status_update_timestamp': datetime.now(timezone.utc),
            'retry_count': retry_count
        }, merge=True)
    except Exception as e:
        print(f"[log_call_to_firestore_initiated] internal_id: {internal_id}, Error: {e}")

def write_to_bigquery(internal_id: str, call_sid: str, to_number: str, status: str, conversation_flag: str = '', dangerous_content: str = '', executive_summary: str = ''):
    try:
        print(f"[write_to_bigquery] internal_id: {internal_id}, call_sid: {call_sid}, to_number: {to_number}, status: {status}")
        if not internal_id or not to_number or not status:
            print(f"[write_to_bigquery] Missing required parameters.")
            return
        client = bigquery.Client()
        table_id = f"{PROJECT_ID}.{BIG_QUERY_DATASET_ID}.call_status_updates"
        rows_to_insert = [{
            'internal_id': internal_id,
            'call_sid': call_sid,
            'to_phone_number': to_number,
            'status': status,
            'insert_timestamp': str(datetime.now(timezone.utc)),
            'conversation_flag': conversation_flag,
            'dangerous_content': dangerous_content,
            'executive_summary': executive_summary
        }]
        errors = client.insert_rows_json(table_id, rows_to_insert)
        if errors:
            print(f"[write_to_bigquery] internal_id: {internal_id}, Errors: {errors}")
        else:
            print(f"[write_to_bigquery] internal_id: {internal_id}, Successfully inserted data into BigQuery")
    except Exception as e:
        print(f"[write_to_bigquery] internal_id: {internal_id}, Error: {e}")

def send_email(to, cc, subject, body, attachments):
    try:
        print(f"[send_email] Sending email to: {to}, subject: {subject}")
        from_username = SENDER_EMAIL_USERNAME
        password = SENDER_EMAIL_PASSWORD
        if not from_username or not password:
            print("[send_email] Email credentials not configured.")
            return
        message = Mail(
            from_email=from_username,
            to_emails=to,
            subject=subject,
            html_content=body)
        if cc:
            for email in cc:
                if email:
                    message.add_cc(Cc(email))
        if attachments:
            for attachment in attachments:
                if not os.path.isfile(attachment):
                    print(f"[send_email] Attachment file not found: {attachment}")
                    continue
                with open(attachment, 'rb') as f:
                    data = f.read()
                encoded_file = base64.b64encode(data).decode()
                attachedFile = Attachment(
                    FileContent(encoded_file),
                    FileName(os.path.basename(attachment)),
                    FileType('application/pdf'),
                    Disposition('attachment')
                )
                message.attachment = attachedFile
        sg = SendGridAPIClient(password)
        response = sg.send(message)
        print(f"[send_email] Status: {response.status_code}, Headers: {response.headers}")
    except Exception as e:
        print(f"[send_email] Error: {e}")

def process_initiated_call(data: str):
    try:
        print(f"[process_initiated_call] Raw data: {data}")
        data = json.loads(data)
        doc_id = data.get("doc_id")
        name = data.get("name")
        phonenumber = data.get("phonenumber")
        filename = data.get("filename")
        internal_id = data.get("internal_id")
        print(f"[process_initiated_call] internal_id: {internal_id}, phonenumber: {phonenumber}, doc_id: {doc_id}, name: {name}, filename: {filename}")
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
            print("[process_initiated_call] Twilio credentials not configured.")
            return {"error": "Twilio credentials not configured."}
        if not phonenumber or not internal_id:
            print("[process_initiated_call] Missing phone number or internal_id.")
            return {"error": "Missing phone number or internal_id."}
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        call = client.calls.create(
            url=f"{WEB_SERVER_URL}/outgoing-call/{phonenumber}/{internal_id}",
            to=phonenumber,
            from_=TWILIO_PHONE_NUMBER,
            status_callback=f'{WEB_SERVER_URL}/call/status/{phonenumber}/{internal_id}',
            status_callback_event=['initiated', 'ringing', 'answered', 'busy', 'no-answer', 'failed', 'canceled', 'completed']
        )
        log_call_to_firestore_initiated(call.sid, phonenumber, internal_id)
        return {"internal_id": internal_id}
    except Exception as e:
        print(f"[process_initiated_call] internal_id: {data.get('internal_id', 'N/A')}, Error: {e}")
        return {"error": f"Failed to make call: {str(e)}"}

def get_conversation_id(internal_id: str, phone_number: str):
    try:
        print(f"[get_conversation_id] internal_id: {internal_id}, phone_number: {phone_number}")
        if not internal_id or not phone_number:
            print("[get_conversation_id] Missing internal_id or phone_number.")
            return '', ''
        db = firestore.Client()
        doc_ref = db.collection('conversation-history').document(phone_number).collection('calls').document(internal_id)
        doc = doc_ref.get()
        if doc.exists:
            doc_dict = doc.to_dict()
            return doc_dict.get('conversation_id', ''), doc_dict.get('conversation_summary', '')
        return '', ''
    except Exception as e:
        print(f"[get_conversation_id] internal_id: {internal_id}, Error: {e}")
        return '', ''

def save_conversation_summary(internal_id: str, phone_number: str, summary: dict):
    try:
        print(f"[save_conversation_summary] internal_id: {internal_id}, phone_number: {phone_number}")
        if not internal_id or not phone_number or not summary:
            print("[save_conversation_summary] Missing required parameters.")
            return
        db = firestore.Client()
        doc_ref = db.collection('conversation-history').document(phone_number)
        user_doc = doc_ref.get()
        prev_summary = ''
        if user_doc.exists:
            prev_summary = user_doc.to_dict().get('executive_summary', '')
        doc_ref.set({
            'executive_summary': f"{prev_summary} \n------------------------------------------------------------\n {datetime.now(timezone.utc)} -  {summary.get('executive_summary', '')}"
        }, merge=True)
        doc_ref = db.collection('conversation-history').document(phone_number).collection('calls').document(internal_id)
        doc_ref.set({
            'conversation_summary': summary.get("summary", ''),
            'executive_summary': summary.get("executive_summary", ''),
            'conversation_flag': summary.get("conversation_flag", ''),
            'dangerous_content': summary.get("dangerous_content", '')
        }, merge=True)
        print(f"[save_conversation_summary] Saved conversation summary for internal_id: {internal_id}, phone_number: {phone_number}")
    except Exception as e:
        print(f"[save_conversation_summary] internal_id: {internal_id}, Error: {e}")

def prepare_call_summary(conversationId: str):
    try:
        print(f"[prepare_call_summary] conversationId: {conversationId}")
        if not conversationId:
            print("[prepare_call_summary] Missing conversationId.")
            return {}
        url = f"https://api.elevenlabs.io/v1/convai/conversations/{conversationId}/audio"
        headers = {'xi-api-key': ELEVENLABS_API_KEY}
        response = requests.request("GET", url, headers=headers)
        response.raise_for_status()
        audio_path = f"{conversationId}.wav"
        with open(audio_path, "wb") as file:
            file.write(response.content)
        genai.configure(api_key=GENAI_API_KEY)
        model = genai.GenerativeModel(GENAI_MODEL_NAME)
        with open(audio_path, "rb") as audio_file:
            audio_bytes = audio_file.read()
        response = model.generate_content(
            [
                call_summary_agent_to_user_prompt,
                {"mime_type": "audio/wav", "data": audio_bytes}
            ]
        )
        summary = process_genai_json_response(response.text)
        print(f"[prepare_call_summary] Generated summary for conversation {conversationId}: {summary}")
        os.remove(audio_path)
        return summary
    except Exception as e:
        print(f"[prepare_call_summary] conversationId: {conversationId}, Error: {e}")
        return {}

def send_whatsapp_message_for_action_required(to_number: str, message: str):
    try:
        print(f"[send_whatsapp_message_for_action_required] to_number: {to_number}")
        topic_id = "whatsapp-message-topic"
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, topic_id)
        random_code = generate_code()
        if not to_number or not message:
            print("[send_whatsapp_message_for_action_required] Missing to_number or message.")
            return
        data = {
            "to_number": to_number,
            "template_name": WHATSAPP_TEMPLATE_ACTION_REQUIRED_NAME,
            "language": "en",
            "templateComponents": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": random_code},
                        {"type": "text", "text": message},
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [
                        {
                            "type": "text",
                            "text": random_code
                        }
                    ]
                }
            ]
        }
        json_string = json.dumps(data)
        byte_data = json_string.encode('utf-8')
        publisher.publish(
            topic_path, byte_data, origin="assistance functions", username="gcp"
        ).result()
        print(f"[send_whatsapp_message_for_action_required] Message published for {to_number}")
    except Exception as e:
        print(f"[send_whatsapp_message_for_action_required] to_number: {to_number}, Error: {e}")

def process_genai_json_response(response_text: str) -> dict:
    try:
        print(f"[process_genai_json_response] Processing response")
        if response_text.startswith('```json'):
            response_text = response_text.replace('```json', '', 1).strip()
        if response_text.endswith('```'):
            response_text = response_text[:-3].strip()
        return json.loads(response_text)
    except json.JSONDecodeError:
        print("[process_genai_json_response] JSON decode error")
        return {
            'summary': '',
            'conversation_flag': 'Unknown',
            'dangerous_content': 'unknown'
        }
    except Exception as e:
        print(f"[process_genai_json_response] Error: {e}")
        return {
            'summary': '',
            'conversation_flag': 'unknown',
            'dangerous_content': 'unknown'
        }

def take_status_completed_action(internal_id: str, to_number: str):
    try:
        print(f"[take_status_completed_action] internal_id: {internal_id}, to_number: {to_number}")
        conversation_id, summary = get_conversation_id(internal_id, to_number)
        if not conversation_id or summary:
            print(f"[take_status_completed_action] No conversation found for internal_id: {internal_id} or summary found: {summary} and to_number: {to_number}")
            return
        print(f"[take_status_completed_action] Found conversation ID: {conversation_id} for internal_id: {internal_id} and to_number: {to_number}")
        print(f"[take_status_completed_action] Preparing call summary for conversation ID: {conversation_id}")
        response = prepare_call_summary(conversation_id)
        if not response:
            print(f"[take_status_completed_action] No summary generated for conversation ID: {conversation_id}")
            return
        summary = response.get('summary', '')
        executive_summary = response.get('executive_summary', '')
        print(f"[take_status_completed_action] Call summary for conversation ID: {conversation_id}, internal_id: {internal_id}: {summary}")
        write_to_bigquery(internal_id, '', to_number, 'processed', response.get('conversation_flag', ''), response.get('dangerous_content', ''), response.get('executive_summary', ''))
        save_conversation_summary(internal_id, to_number, response)
        if response.get('conversation_flag') in ["Potential Customer", "May be Potential Customer"]:
            send_email(AGENT_EMAIL_ID, [], 'New Student Lead', f"New Student Lead for {to_number} \n\nSummary: {executive_summary}", None)
            if response.get('dangerous_content') != "dangerous":
                send_whatsapp_message_for_action_required(to_number, summary)
    except Exception as e:
        print(f"[take_status_completed_action] internal_id: {internal_id}, Error: {e}")

def process_call_status_update(data: str):
    try:
        print(f"[process_call_status_update] Raw data: {data}")
        data = json.loads(data)
        internal_id = data.get("internal_id")
        to_number = data.get("to_number")
        call_sid = data.get("call_sid")
        status = data.get("status")
        print(f"[process_call_status_update] internal_id: {internal_id}, call_sid: {call_sid}, to_number: {to_number}, status: {status}")
        if not internal_id or not to_number or not status:
            print("[process_call_status_update] Missing required parameters.")
            return
        if status == "completed":
            take_status_completed_action(internal_id, to_number)
        else:
            print(f"[process_call_status_update] No summary needed for status: {status}")
    except Exception as e:
        print(f"[process_call_status_update] Error: {e}")

@functions_framework.cloud_event
def telephonic_call_initiator(cloud_event):
    try:
        print("[telephonic_call_initiator] Invoked")
        data = base64.b64decode(cloud_event.data["message"]["data"]).decode('utf-8')
        process_initiated_call(data)
        return ('', 200)
    except Exception as e:
        print(f"[telephonic_call_initiator] Error: {e}")
        return ('', 500)

@functions_framework.cloud_event
def telephonic_call_status_updates(cloud_event):
    try:
        print("[telephonic_call_status_updates] Invoked")
        data = base64.b64decode(cloud_event.data["message"]["data"]).decode('utf-8')
        process_call_status_update(data)
        return ('', 200)
    except Exception as e:
        print(f"[telephonic_call_status_updates] Error: {e}")
        return ('', 500)

if __name__ == "__main__":
    print("[main] Script is being run directly")
    process_call_status_update('{"internal_id": "4fe6d621-1b49-41f9-98ce-acea7439b260", "to_number": "+919646763121", "status": "completed" ,"call_sid" : "CA8e744d384fea6208eec7c21f7dd4740e"}')
else:
    print("[main] Script is being imported as a module")