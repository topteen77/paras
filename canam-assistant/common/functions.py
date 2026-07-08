from datetime import datetime, timedelta, timezone
import uuid
from google.cloud import firestore
from google.cloud import pubsub_v1
import json
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
from google.cloud import bigquery
from twilio.rest import Client
from common.config import (
    MAX_CALL_RETRY_COUNT,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    PROJECT_ID,
    QUEUE_NAME,
    REGION_NAME,
    MAX_PARRALLEL_REQUESTS_TO_AGENT,
    DEFAULT_CALL_DURATION_IN_SECONDS,
    BIG_QUERY_DATASET_ID
)
topic_id = "telephonic-call-status-updates"
call_processing_topic_id = "call-processing-topic"

def proces_scheduled_calls(hostname):
    try:
        print(f"[proces_scheduled_calls] Starting scheduled call processing")
        db = firestore.Client()
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, call_processing_topic_id)

        docs = db.collection('conversation-history')\
                .where('process_status', '==', 'scheduled')\
                .limit(MAX_PARRALLEL_REQUESTS_TO_AGENT)\
                .stream()

        processed_count = 0
        for doc in docs:
            data = doc.to_dict()
            doc_id = doc.id
            internal_id = data.get('last_internal_id', '')

            print(f"[proces_scheduled_calls][internal_id: {internal_id}] Processing scheduled call for doc_id: {doc_id}")

            message_data = {
                "doc_id": doc_id,
                "name": data.get('name'),
                "phonenumber": data.get('to_phone_number'),
                "filename": data.get('filename'),
                "internal_id": internal_id
            }

            try:
                json_string = json.dumps(message_data)
                publisher.publish(
                    topic_path, 
                    json_string.encode('utf-8'),
                    origin="call_scheduler",
                    username="gcp"
                ).result()

                doc.reference.update({
                    'process_status': 'initiated',
                    'initiated_at': datetime.now(timezone.utc)
                })
                print(f"[proces_scheduled_calls][internal_id: {internal_id}] Updated process_status to 'initiated' for doc_id: {doc_id}")
                processed_count += 1

            except Exception as e:
                print(f"[proces_scheduled_calls][internal_id: {internal_id}] Error processing record {doc_id}: {str(e)}")
                continue

        if processed_count > 0:
            print(f"[proces_scheduled_calls] Scheduling next batch after {DEFAULT_CALL_DURATION_IN_SECONDS} seconds")
            create_task(hostname, 'process-scheduled-calls', data={}, delay_seconds=DEFAULT_CALL_DURATION_IN_SECONDS)

        print(f"[proces_scheduled_calls] Processed {processed_count} records")
        return {"message": f"Processed {processed_count} records"}
    except Exception as e:
        print(f"[proces_scheduled_calls] Error in processing scheduled calls: {str(e)}")
        return {"message": "Error in processing scheduled calls"}

def create_scheduled_call_record(to_phone_number: str, internal_id: str, filename: str, name: str):
    try:
        db = firestore.Client()
        phone_number = str(to_phone_number)
        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number
        doc_ref = db.collection('conversation-history').document(phone_number)
        if internal_id == "":
            internal_id = str(uuid.uuid4())
        print(f"[create_scheduled_call_record][internal_id: {internal_id}] Creating scheduled call record for phone_number: {phone_number}")
        doc_ref.set(
            {
                'name': name,
                'to_phone_number': phone_number,
                'process_status': 'scheduled',
                'filename': filename,
                'scheduled_at': datetime.now(timezone.utc),
                'last_internal_id': internal_id,
                'retry_count': 0,
            },
            merge=True
        )
        print(f"[create_scheduled_call_record][internal_id: {internal_id}] Scheduled call record created successfully")
        return {"internal_id": internal_id, "to_phone_number": phone_number}
    except Exception as e:
        print(f"[create_scheduled_call_record][internal_id: {internal_id}] Error creating scheduled call record: {str(e)}")
        return {"error": str(e)}

def log_call_to_firestore_status_update(internal_id: str, to_number: str, call_status: str):
    try:
        db = firestore.Client()
        doc_ref = db.collection('conversation-history').document(to_number).collection('calls').document(internal_id)
        doc = doc_ref.get()
        can_retry = False
        if doc.exists:
            current_retry_count = doc.get('retry_count') or 0
            print(f"[log_call_to_firestore_status_update][internal_id: {internal_id}] Current retry count: {current_retry_count}")
            new_retry_count = current_retry_count
            if call_status in ['failed', 'busy', 'no-answer']:
                new_retry_count = current_retry_count + 1
                can_retry = new_retry_count <= MAX_CALL_RETRY_COUNT
                print(f"[log_call_to_firestore_status_update][internal_id: {internal_id}] Retry needed. New retry count: {new_retry_count}, Can retry: {can_retry}")
            doc_ref.set({
                'status': call_status,
                'status_update_timestamp': datetime.now(timezone.utc),
                'retry_count': new_retry_count
            }, merge=True)
            print(f"[log_call_to_firestore_status_update][internal_id: {internal_id}] Updated Firestore with status: {call_status}, retry_count: {new_retry_count}")
        else:
            print(f"[log_call_to_firestore_status_update][internal_id: {internal_id}] Document does not exist for to_number: {to_number}")
        return can_retry
    except Exception as e:
        print(f"[log_call_to_firestore_status_update][internal_id: {internal_id}] Error: {str(e)}")
        return False
           
def add_call_staus_to_pubsub(call_sid: str, internal_id: str, to_number: str, status: str):
    try:
        print(f"[add_call_staus_to_pubsub][internal_id: {internal_id}] Publishing call status to Pub/Sub for to_number: {to_number}, call_sid: {call_sid}, status: {status}")
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, topic_id)
        data = {"internal_id": internal_id, "to_number": to_number, "call_sid": call_sid, "status": status}
        json_string = json.dumps(data)
        byte_data = json_string.encode('utf-8')
        publisher.publish(
            topic_path, byte_data, origin="assistance api", username="gcp"
        ).result()
        print(f"[add_call_staus_to_pubsub][internal_id: {internal_id}] Published call status successfully")
    except Exception as e:
        print(f"[add_call_staus_to_pubsub][internal_id: {internal_id}] Error publishing call status: {str(e)}")

def create_task(hostname: str, endpoint: str, data: any, delay_seconds: int = 20):
    try:
        print(f"[create_task] Creating task for endpoint: {endpoint} with delay: {delay_seconds} seconds")
        client = tasks_v2.CloudTasksClient()
        project = PROJECT_ID
        queue = QUEUE_NAME
        location = REGION_NAME
        url = f'https://{hostname}/{endpoint}'

        parent = client.queue_path(project, location, queue)

        task = {
            'http_request': {
                'http_method': tasks_v2.HttpMethod.POST,
                'url': url,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps(data).encode()
            }
        }

        schedule_time = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        timestamp = timestamp_pb2.Timestamp()
        timestamp.FromDatetime(schedule_time)
        task['schedule_time'] = timestamp

        print(f"[create_task] Task scheduled at: {schedule_time.isoformat()} for endpoint: {endpoint}")
        return client.create_task(request={'parent': parent, 'task': task})
    except Exception as e:
        print(f"[create_task] Error creating task for endpoint: {endpoint}: {str(e)}")

def write_to_bigquery(internal_id: str, call_sid: str, to_number: str, status: str, conversation_flag=''):
    try:
        print(f"[write_to_bigquery][internal_id: {internal_id}] Inserting call status update into BigQuery")
        client = bigquery.Client()
        table_id = f"{PROJECT_ID}.{BIG_QUERY_DATASET_ID}.call_status_updates" 
        
        rows_to_insert = [{
            'internal_id': internal_id,
            'call_sid': call_sid,
            'to_phone_number': to_number,
            'status': status,
            'insert_timestamp': str(datetime.now(timezone.utc)),
            'conversation_flag': conversation_flag
        }]

        errors = client.insert_rows_json(table_id, rows_to_insert)
        print(f"[write_to_bigquery][internal_id: {internal_id}] rows_to_insert: {rows_to_insert}")
        if errors:
            print(f"[write_to_bigquery][internal_id: {internal_id}] Encountered errors while inserting into BigQuery: {errors}")
        else:
            print(f"[write_to_bigquery][internal_id: {internal_id}] Successfully inserted data into BigQuery")
    except Exception as e:
        print(f"[write_to_bigquery][internal_id: {internal_id}] Error inserting into BigQuery: {str(e)}")

def get_executive_summary(to_phone_number: str):
    try:
        print(f"[get_executive_summary][to_phone_number: {to_phone_number}] Retrieving executive summary")
        db = firestore.Client()
        doc_ref = db.collection('conversation-history').document(to_phone_number)
        doc = doc_ref.get()
        
        if doc.exists:
            executive_summary = doc.get('executive_summary')
            if executive_summary:
                print(f"[get_executive_summary][to_phone_number: {to_phone_number}] Executive summary found")
                return executive_summary
            else:
                print(f"[get_executive_summary][to_phone_number: {to_phone_number}] No executive summary available")
                return 'No executive summary available'
        else:
            print(f"[get_executive_summary][to_phone_number: {to_phone_number}] Document does not exist")
            return 'No executive summary available'
    except Exception as e:
        print(f"[get_executive_summary][to_phone_number: {to_phone_number}] Error: {str(e)}")
        return 'No executive summary available'

def end_call_by_internal_id(internal_id: str, to_phone_number: str):
    try:
        print(f"[end_call_by_internal_id][internal_id: {internal_id}] Attempting to end call for to_phone_number: {to_phone_number}")
        db = firestore.Client()
        doc_ref = db.collection('conversation-history').document(to_phone_number).collection('calls').document(internal_id)
        doc = doc_ref.get()
        if doc.exists:
            print(f"[end_call_by_internal_id][internal_id: {internal_id}] Call document found, ending call")
            return end_call(doc.get('call_sid'))
        print(f"[end_call_by_internal_id][internal_id: {internal_id}] Call SID not found for given internal ID")
        return {"status": "error", "message": "Call SID not found for given internal ID"}
    except Exception as e:
        print(f"[end_call_by_internal_id][internal_id: {internal_id}] Error: {str(e)}")
        return {"status": "error", "message": str(e)}

def end_call(call_sid: str):
    """End a call using the configured telephony provider."""
    from common.telephony import end_call as telephony_end_call
    print(f"[end_call] Attempting to end call with call_sid: {call_sid}")
    return telephony_end_call(call_sid)

def handle_failed_calls(call_status, to_phone_number, internal_id, hostname):
    try:
        print(f"[handle_failed_calls][internal_id: {internal_id}] Handling failed call for to_phone_number: {to_phone_number}, call_status: {call_status}")
        if call_status in ['busy', 'no-answer', 'failed']:
            ist_tz = timezone(timedelta(hours=5, minutes=30))  # IST is UTC+5:30
            current_time_ist = datetime.now(ist_tz)
            
            if current_time_ist.hour >= 19:
                next_day = current_time_ist + timedelta(days=1)
                schedule_time = next_day.replace(hour=10, minute=0, second=0, microsecond=0)
                delay_seconds = int((schedule_time - current_time_ist).total_seconds())
            else:
                delay_seconds = 7200  # 2 hours in seconds

            print(f"[handle_failed_calls][internal_id: {internal_id}] Setting retry delay for to_phone_number: {to_phone_number}, delay_seconds: {delay_seconds}")
            print(f"[handle_failed_calls][internal_id: {internal_id}] Current IST time: {current_time_ist}")
            retry_time = current_time_ist + timedelta(seconds=delay_seconds)
            print(f"[handle_failed_calls][internal_id: {internal_id}] Will retry call at: {retry_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            task_data = {
                "to": to_phone_number,
                "internal_id": internal_id,
                "retry_time": retry_time.isoformat()
            }
            create_task(hostname, 'make-call', task_data, delay_seconds)
    except Exception as e:
        print(f"[handle_failed_calls][internal_id: {internal_id}] Error handling failed call: {str(e)}")
