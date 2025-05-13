from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json
import httpx
import os

app = FastAPI()

API_KEY = "QbVPuhyqwlRyqH4ckFU5HJ0i2YTkUuOmGSPpGYHSYbsF"
COS_URL_OP14 = "https://s3.us-south.cloud-object-storage.appdomain.cloud/leavedetails/watsonxassistant_logs.txt"
COS_URL_OP15 = "https://s3.us-south.cloud-object-storage.appdomain.cloud/leavedetails/phone_no_info.txt"
EXTRACTOR_URL = "https://phone-no-extractor-final.onrender.com/extract"
TIME_CONVERTER_URL = "https://time-convertor.onrender.com/convert"

LOG_FILE_PATH = "watsonxassistant_logs.txt"
PHONE_FILE_PATH = "phone_no_info.txt"

@app.get("/")
async def root():
    return {"message": "CDR Logging API is up and running!"}

async def get_bearer_token():
    url = "https://iam.cloud.ibm.com/identity/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = f"grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey={API_KEY}"
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()["access_token"]

@app.post("/cdr-log")
async def log_webhook(request: Request):
    data = await request.json()
    json_content = json.dumps(data, indent=2)

    # Save incoming payload
    with open(LOG_FILE_PATH, "w") as f:
        f.write(json_content)

    # Extract phone numbers
    try:
        from_uri = data["payload"]["session_initiation_protocol"]["headers"]["from_uri"]
        to_uri = data["payload"]["session_initiation_protocol"]["headers"]["to_uri"]
        payload = {"from_uri": from_uri, "to_uri": to_uri}
        async with httpx.AsyncClient() as client:
            response = await client.post(EXTRACTOR_URL, json=payload)
            result = response.json()
            from_number = result.get("from_number", "Not found")
            to_number = result.get("to_number", "Not found")
            phone_part = f"User Number: {from_number}\nChatbot Number: {to_number}"
    except Exception:
        phone_part = "Phone number extraction failed."

    # Convert timestamps
    try:
        start_ts = data["payload"]["call"]["start_timestamp"]
        stop_ts = data["payload"]["call"]["stop_timestamp"]
        time_payload = {"start_timestamp": start_ts, "stop_timestamp": stop_ts}
        async with httpx.AsyncClient() as client:
            response = await client.post(TIME_CONVERTER_URL, json=time_payload)
            times = response.json()
            ist_start = times.get("start_timestamp_ist", "Conversion error")
            ist_stop = times.get("stop_timestamp_ist", "Conversion error")
            time_part = f"Start Time (IST): {ist_start}\nStop Time (IST): {ist_stop}"
    except Exception:
        time_part = "Timestamp conversion failed."

    with open(PHONE_FILE_PATH, "w") as f:
        f.write(f"{phone_part}\n{time_part}")

    # Upload to COS
    try:
        token = await get_bearer_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "text/plain"}
        async with httpx.AsyncClient() as client:
            with open(LOG_FILE_PATH, "rb") as f:
                await client.put(COS_URL_OP14, headers=headers, content=f.read())
            with open(PHONE_FILE_PATH, "rb") as f:
                await client.put(COS_URL_OP15, headers=headers, content=f.read())

        return JSONResponse(status_code=200, content={"message": "Successfully retrieved data and stored in COS."})

    except Exception as e:
        return JSONResponse(status_code=500, content={"message": "Failed to upload to COS."})
