# assistantFunctions Plivo patch (Stack 2)

When using `Plivo-Sarvam`, update `assistantFunctions-main/main.py` `process_initiated_call`
to initiate calls via Plivo instead of Twilio.

Replace the Twilio `client.calls.create(...)` block with:

```python
from urllib.parse import quote
import plivo

PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")
PLIVO_PHONE_NUMBER = os.getenv("PLIVO_PHONE_NUMBER")

phone_enc = quote(phonenumber, safe="")
client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)
response = client.calls.create(
    from_=PLIVO_PHONE_NUMBER,
    to_=phonenumber,
    answer_url=f"{WEB_SERVER_URL}/outgoing-call/{phone_enc}/{internal_id}",
    answer_method="POST",
    hangup_url=f"{WEB_SERVER_URL}/call/status/{phone_enc}/{internal_id}",
    hangup_method="POST",
)
call_uuid = response[1].request_uuid
log_call_to_firestore_initiated(call_uuid, phonenumber, internal_id)
```

Add to `assistantFunctions-main/requirements.txt`:
```
plivo
```

Add Plivo env vars to `assistantFunctions-main/.env`.
