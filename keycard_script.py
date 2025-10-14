from fastapi import FastAPI, HTTPException, Request
import ctypes
from ctypes import c_int, c_ubyte, create_string_buffer
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
    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p
]
sdk.GuestCard.restype = c_int

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


def close_usb():
    """
    Close the USB connection to the keycard encoder.
    """
    sdk.CloseUSB(1)
    logging.info("[USB] Closed successfully")


def create_card(hotel_id, card_no, checkin_time, checkout_time, room_no):
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
    dai, LLock, pdoors = 0, 1, 0
    card_hex = create_string_buffer(200)
    res = sdk.GuestCard(
        1, hotel_id, card_no, dai, LLock, pdoors,
        checkin_time.encode(), checkout_time.encode(),
        str(room_no).encode(), card_hex
    )

    if res == 0:
        logging.info(f"[CARD] Created successfully for room {room_no}")
        return {"status": "success", "card_data": card_hex.value.decode(errors="ignore").rstrip('\x00')}
    else:
        logging.error(f"[CARD] Creation failed (code={res})")
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
        logging.info(f"[CARD] Deleted successfully (hotel_id={hotel_id})")
        return {"status": "success"}
    else:
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

    if any(x is None for x in [hotel_id, card_no, checkin_time, checkout_time, room_no]):
        raise HTTPException(status_code=400, detail="Missing required parameters")

    req_id = f"REQ-{threading.get_ident()}"
    queue_start = time.perf_counter()
    logging.info(f"{req_id}: Waiting to acquire SDK lock...")

    with sdk_lock:
        queue_wait = time.perf_counter() - queue_start
        logging.info(f"{req_id}: Lock acquired after {queue_wait:.3f}s — entering SDK operation")
        start_time = time.perf_counter()

        if not init_usb():
            raise HTTPException(status_code=500, detail="USB initialization failed")

        try:
            result = create_card(int(hotel_id), int(card_no), checkin_time, checkout_time, room_no)
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

    card_data = cards_collection.find_one({"hotel_id": hotel_id})
    if not card_data:
        raise HTTPException(status_code=404, detail="Card not found")

    card_hex = card_data.get("card_hex")
    if not card_hex:
        raise HTTPException(status_code=400, detail="Missing card data")

    req_id = f"REQ-{threading.get_ident()}"
    queue_start = time.perf_counter()
    logging.info(f"{req_id}: Waiting to acquire SDK lock for deletion...")

    with sdk_lock:
        queue_wait = time.perf_counter() - queue_start
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
