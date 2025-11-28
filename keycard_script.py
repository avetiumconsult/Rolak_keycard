from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import ctypes
from ctypes import c_int, c_ubyte, create_string_buffer, POINTER
import threading
import logging
import time
import uvicorn
from mongodb import connect_to_database

# -----------------------------------------------------
# 1️⃣ Setup & Logging
# -----------------------------------------------------
app = FastAPI(title="ProRFL SDK Agent")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    handlers=[
        logging.FileHandler("sdk_agent.log"),
        logging.StreamHandler()
    ]
)

# Initialize race safety lock
sdk_lock = threading.Lock()

# -----------------------------------------------------
# 2️⃣ Database connection
# -----------------------------------------------------
db_client = connect_to_database()
db = db_client['keycard_db']
cards_collection = db['cards']

# -----------------------------------------------------
# 3️⃣ Load the SDK DLL
# -----------------------------------------------------
try:
    sdk = ctypes.WinDLL(r"C:\Users\chinedu.orjiogo\Documents\Rolak_keycard\proRFL.dll")
    logging.info(f"✅ SDK DLL loaded successfully from {sdk._name}")
except Exception as e:
    raise Exception(f"❌ Failed to load DLL: {e}")

# -----------------------------------------------------
# 4️⃣ Map SDK functions & define argument/return types
# -----------------------------------------------------
sdk.GetDLLVersion.argtypes = [ctypes.c_char_p]
sdk.GetDLLVersion.restype = c_int

sdk.initializeUSB.argtypes = [c_ubyte]
sdk.initializeUSB.restype = c_int

sdk.CloseUSB.argtypes = [c_ubyte]
sdk.CloseUSB.restype = None

sdk.Buzzer.argtypes = [c_ubyte, c_ubyte]
sdk.Buzzer.restype = c_int

sdk.GuestCard.argtypes = [
    c_ubyte, c_int, c_ubyte, c_ubyte, c_ubyte, c_ubyte,
    ctypes.c_char_p, ctypes.c_char_p, POINTER(c_ubyte), ctypes.c_char_p
]
sdk.GuestCard.restype = c_int

sdk.ReadCard.argtypes = [c_ubyte, ctypes.c_char_p]
sdk.ReadCard.restype = c_int

sdk.CardErase.argtypes = [c_ubyte, c_int, ctypes.c_char_p]
sdk.CardErase.restype = c_int

# -----------------------------------------------------
# 5️⃣ Utility wrappers with race safety
# -----------------------------------------------------
def init_usb():
    """
    Initialize the USB connection to the keycard encoder.

    Returns:
        bool: True if the USB initialization succeeds, False otherwise.
    """
    res = sdk.initializeUSB(1)
    if res == 0:
        logging.info("[USB] Initialized successfully")
        return True
    logging.error(f"[USB] Initialization failed (code={res})")
    return False

def buzzer(fUSB: int = 1, duration_ms: int = 500) -> bool:
    """
    Activate the buzzer on the keycard encoder.

    Parameters:
        fUSB (int): Type of reader.
            - 0: USB
            - 1: proUSB
        duration_ms (int): Duration of the beep in milliseconds.

    Returns:
        bool: True if the buzzer activation succeeds, False otherwise.
    """
    # Convert milliseconds to 10ms units (as required by the SDK)
    t = duration_ms // 10

    # Call the SDK function
    res = sdk.Buzzer(c_ubyte(fUSB), c_ubyte(t))

    if res == 0:
        logging.info(f"[BUZZER] Activated successfully (reader={fUSB}, duration={duration_ms}ms)")
        return True
    else:
        logging.error(f"[BUZZER] Activation failed (reader={fUSB}, duration={duration_ms}ms, code={res})")
        return False


def close_usb():
    """
    Close the USB connection to the keycard encoder.
    """
    sdk.CloseUSB(1)
    logging.info("[USB] Closed successfully")

def lockstr_to_bytes(lockstr: str):
    """
    Convert a string like '01000808' into a ctypes c_ubyte array
    suitable for the SDK GuestCard function.
    """
    if len(lockstr) != 8:
        logging.info(lockstr)
        raise ValueError("lockstr must be exactly 8 characters")

    # Each character becomes its ASCII byte
    lock_bytes = (ctypes.c_ubyte * 8)(
        *[ord(lockstr[i]) for i in range(8)]
    )
    return lock_bytes

def card_no_to_lockno_bytes(card_no: int):
    # Build lock string, e.g., "01000105"
    lockstr = f"0100{card_no:02d}08"  # adjust final pattern to your hardware expectation
    if len(lockstr) != 8:
        raise ValueError("LockNo string must be 8 chars")
    
    # Convert each character to ASCII byte
    lock_bytes = (c_ubyte * 8)(*[ord(c) for c in lockstr])
    return lock_bytes

def create_card(hotel_id, card_no, checkin_time, checkout_time, room_no, lock_no):
    """
    Create a new keycard for a hotel guest using the SDK GuestCard function.

    Parameters:
        hotel_id (int): The unique identifier for the hotel.
        card_no (int): The card number to be assigned.
        checkin_time (str): The check-in time in string format.
        checkout_time (str): The check-out time in string format.
        room_no (str): The room number assigned to the guest.

    Returns:
        dict: A JSON-like dictionary containing:
            - status (str): "success" if card creation succeeds, otherwise "error".
            - code (int, optional): The SDK error code if any.
            - card_data (str, optional): Encoded keycard data if successful.
    """
    dai, LLock, pdoors = 0, 1, 1
    card_hex = create_string_buffer(200)
    res = sdk.GuestCard(
        1, hotel_id, card_no, dai, LLock, pdoors,
        checkin_time.encode(), checkout_time.encode(), lock_no,
        card_hex
    )


    if res == 0:
        buzzer(1, 500)
        logging.info(f"[CARD] Created successfully for room {room_no}")
        return {"status": "success", "card_data": card_hex.value.decode(errors="ignore").rstrip('\x00')}
    else:
        buzzer(1, 500)
        logging.error(f"[CARD] Creation failed (code={res})")
        return {"status": "error", "code": res}
    
def read_card(fUSB: int = 1) -> dict:
    """
    Read data from an existing keycard using the SDK ReadCard function.

    Parameters:
        fUSB (int): Type of reader.
            - 0: USB
            - 1: proUSB

    Returns:
        dict: A JSON-like dictionary containing:
            - status (str): "success" if reading succeeds, otherwise "error".
            - code (int, optional): The SDK error code if any.
            - card_data (str, optional): Encoded keycard data if successful.
    """
    card_hex = create_string_buffer(200)
    res = sdk.ReadCard(c_ubyte(fUSB), card_hex)

    if res == 0:
        logging.info(f"[CARD] Read successfully (reader={fUSB})")
        return {"status": "success", "card_data": card_hex.value.decode(errors="ignore").rstrip('\x00')}
    else:
        logging.error(f"[CARD] Read failed (reader={fUSB}, code={res})")
        return {"status": "error", "code": res}


def delete_card(hotel_id, card_hex_str):
    """
    Delete an existing keycard by erasing its data using the SDK CardErase function.

    Parameters:
        hotel_id (int): The unique identifier for the hotel.
        card_hex_str (str): The encoded hexadecimal string of the card to be erased.

    Returns:
        dict: A JSON-like dictionary containing:
            - status (str): "success" if deletion succeeds, otherwise "error".
            - code (int, optional): The SDK error code if any.
    """
    res = sdk.CardErase(1, hotel_id, card_hex_str.encode())
    if res == 0:
        buzzer(1, 500)
        logging.info(f"[CARD] Deleted successfully (hotel_id={hotel_id})")
        return {"status": "success"}
    else:
        buzzer(1, 500)
        logging.error(f"[CARD] Deletion failed (code={res})")
        return {"status": "error", "code": res}


# -----------------------------------------------------
# 6️⃣ API Endpoints with Observability & Locking
# -----------------------------------------------------
@app.post("/create_card")
async def api_create_card(request: Request):
    """
    Create a new keycard for a hotel guest.

    Parameters:
        request (Request): The HTTP request containing JSON with the following fields:
            - hotel_id (int): The unique identifier for the hotel.
            - card_no (int): The card number to be assigned.
            - checkin_time (str): The check-in time in string format.
            - checkout_time (str): The check-out time in string format.
            - room_no (str): The room number assigned to the guest.

    Returns:
        JSON response with:
            - status (str): "success" if card creation is successful, otherwise "error".
            - message (str): Description of the operation result.
            - card_data (str, optional): The encoded card data if successful.
    """
    data = await request.json()
    hotel_id = data.get("hotel_id")
    card_no = data.get("card_no")
    checkin_time = data.get("checkin_time")
    checkout_time = data.get("checkout_time")
    room_no = data.get("room_no")
    lock_No = data.get("lock_no")

    lock_no = lockstr_to_bytes(lock_No)

    if any(x is None for x in [hotel_id, card_no, checkin_time, checkout_time,room_no, lock_no]):
        raise HTTPException(status_code=400, detail="Missing required parameters")

    req_id = f"REQ-{threading.get_ident()}"
    queue_start = time.perf_counter()
    logging.info(f"{req_id}: Waiting to acquire SDK lock...")

    with sdk_lock:
        queue_wait = time.perf_counter() - queue_start
        buzzer(1, 1000)
        logging.info(f"{req_id}: Lock acquired after {queue_wait:.3f}s — entering SDK operation")
        start_time = time.perf_counter()

        if not init_usb():
            raise HTTPException(status_code=500, detail="USB initialization failed")

        try:
            result = create_card(int(hotel_id), int(card_no), checkin_time, checkout_time, room_no, lock_no)
            if result["status"] == "success":
                cards_collection.insert_one({
                    "hotel_id": hotel_id,
                    "card_no": card_no,
                    "checkin_time": checkin_time,
                    "checkout_time": checkout_time,
                    "room_no": room_no,
                    "card_hex": result["card_data"]
                })
                elapsed = time.perf_counter() - start_time
                logging.info(f"{req_id}: Card created successfully in {elapsed:.3f}s")
                return {
                    "status": "success",
                    "message": "Card creation successful",
                    "card_data": result.get("card_data"),
                    "metrics": {
                        "queue_wait": f"{queue_wait:.3f}s",
                        "processing_time": f"{elapsed:.3f}s"
                    }
                }
            else:
                raise HTTPException(status_code=500, detail=f"Card creation failed (code={result.get('code')})")
        finally:
            close_usb()
            logging.info(f"{req_id}: Lock released and USB closed")

@app.post("/readcard")
async def api_read_card(request: Request):
    """
    Read data from an existing keycard.

    Parameters:
        request (Request): The HTTP request containing JSON with the following optional field:
            - fUSB (int, optional): The reader type. Defaults to 0 if not provided.
                0 → USB reader
                1 → proUSB reader
    Returns:
        JSON response with:
            - status (str): "success" if reading is successful, otherwise "error".
            - message (str): Description of the operation result.
            - card_data (str, optional): The encoded card data if successful.
    """
    data = await request.json()
    fUSB = data.get("fUSB", 1)  # Default to proUSB if not provided

    req_id = f"REQ-{threading.get_ident()}"
    queue_start = time.perf_counter()
    
    #logging.info(f"{req_id}: Waiting to acquire SDK lock for reading...")

    with sdk_lock:
        queue_wait = time.perf_counter() - queue_start
        buzzer(1, 1000)
        #logging.info(f"{req_id}: Lock acquired after {queue_wait:.3f}s — proceeding to read card")
        start_time = time.perf_counter()

        if not init_usb():
            raise HTTPException(status_code=500, detail="USB initialization failed")

        try:
            result = read_card(int(fUSB))
            logging.info(f"{req_id}: Read card result: {result}")
            if result["status"] == "success":
                elapsed = time.perf_counter() - start_time
                logging.info(f"{req_id}: Card read successfully in {elapsed:.3f}s")
                return {
                    "status": "success",
                    "message": "Card read successful",
                    "card_data": result.get("card_data"),
                    "metrics": {
                        "queue_wait": f"{queue_wait:.3f}s",
                        "processing_time": f"{elapsed:.3f}s"
                    }
                }
            else:
                raise HTTPException(status_code=500, detail=f"Card read failed (code={result.get('code')})")
        finally:
            close_usb()
            logging.info(f"{req_id}: Lock released and USB closed after reading")

@app.post("/delete_card")
async def api_delete_card(request: Request):
    """
    Delete an existing keycard for a hotel guest by erasing its data via the SDK.

    Parameters:
        request (Request): The HTTP request containing JSON with the following fields:
            - hotel_id (int): The unique identifier for the hotel whose card should be deleted.

    Returns:
        JSON response with:
            - status (str): "success" if the deletion is successful, otherwise "error".
            - message (str): Description of the operation result.
    """
    data = await request.json()
    hotel_id = data.get("hotel_id")
    logging.info(f"Received delete_card request for hotel_id: {hotel_id}")

    card_data = cards_collection.find_one(
    {"hotel_id": int(hotel_id)},
    sort=[("_id", -1)]  # get the most recently inserted card
    )

    logging.info(f"Card data retrieved from DB: {card_data}")
    if not card_data:
        raise HTTPException(status_code=404, detail=f"Card not found for hotel_id {hotel_id}")

    card_hex = card_data.get("card_hex")
    if not card_hex:
        raise HTTPException(status_code=400, detail="Missing card data")

    req_id = f"REQ-{threading.get_ident()}"
    queue_start = time.perf_counter()
    logging.info(f"{req_id}: Waiting to acquire SDK lock for deletion...")

    with sdk_lock:
        queue_wait = time.perf_counter() - queue_start
        buzzer(1, 1000)
        logging.info(f"{req_id}: Lock acquired after {queue_wait:.3f}s — proceeding to delete card")
        start_time = time.perf_counter()

        if not init_usb():
            raise HTTPException(status_code=500, detail="USB initialization failed")

        try:
            result = delete_card(int(hotel_id), card_hex)
            if result["status"] == "success":
                cards_collection.delete_one({"hotel_id": hotel_id})
                elapsed = time.perf_counter() - start_time
                logging.info(f"{req_id}: Card deleted successfully in {elapsed:.3f}s")
                return {
                    "status": "success",
                    "message": "Card deletion successful",
                    "metrics": {
                        "queue_wait": f"{queue_wait:.3f}s",
                        "processing_time": f"{elapsed:.3f}s"
                    }
                }
            else:
                raise HTTPException(status_code=500, detail=f"Card deletion failed (code={result.get('code')})")
        finally:
            close_usb()
            logging.info(f"{req_id}: Lock released and USB closed after deletion")

@app.post("/buzzer")
async def trigger_buzzer(request: Request):
    """
    Activate the card reader buzzer.

    Parameters:
        request (Request): The HTTP request containing JSON with the following optional fields:
            - fUSB (int, optional): The reader type. Defaults to 0 if not provided.
                0 → USB reader
                1 → proUSB reader
            - duration_ms (int, optional): The duration of the buzzer sound in milliseconds. Defaults to 500 if not provided.

    Returns:
        JSON response with:
            - status (str): "success" if the buzzer activation is successful, otherwise "error".
            - message (str): Description of the operation result.
    """
    try:
        data = await request.json()
        fUSB = data.get("fUSB", 1)  # Default to proUSB if not provided
        duration_ms = data.get("duration_ms", 500)

        # Validate and convert fUSB
        try:
            fUSB = int(fUSB)
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Invalid fUSB value. Must be 0 or 1.",
                },
            )
        if fUSB not in (0, 1):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "fUSB must be 0 (USB) or 1 (proUSB).",
                },
            )

        # Validate and convert duration_ms
        try:
            duration_ms = int(duration_ms)
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Invalid duration_ms value. Must be an integer.",
                },
            )
        if not (10 <= duration_ms <= 10000):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "duration_ms must be between 10 and 10000 milliseconds.",
                },
            )

        result = buzzer(fUSB, duration_ms)

        if result:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": f"Buzzer activated for {duration_ms}ms on reader type {fUSB}",
                },
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Failed to activate buzzer on the device {result}, fUSB={fUSB}, duration_ms={duration_ms}",
                },
            )

    except Exception as e:
        logging.exception(f"[BUZZER ENDPOINT] Unexpected error occurred. Exception type: {type(e).__name__}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"{type(e).__name__}: {e}"},
        )



@app.get("/health")
async def health_check():
    """
    Perform a simple health check to verify that the SDK Agent service is operational.

    Returns:
        JSON response with:
            - status (str): "ok" if the service is healthy.
            - message (str): Additional information about service status.
    """
    return {"status": "ok", "message": "SDK Agent is healthy and running"}


# -----------------------------------------------------
# 7️⃣ App Entry Point
# -----------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
