from fastapi import FastAPI, HTTPException, Request
import ctypes
from ctypes import c_int, c_ubyte, create_string_buffer
import uvicorn
from mongodb import connect_to_database

# initialize the database connection
db_client = connect_to_database()
db = db_client['keycard_db']
cards_collection = db['cards']

app = FastAPI(title="ProRFL SDK Agent")

# Load the SDK DLL
try:
    sdk = ctypes.WinDLL(r"C:\Users\chinedu.orjiogo\Documents\Rolak_keycard\proRFL.dll")
    print(f"[OK] DLL loaded successfully from {sdk._name}")
except Exception as e:
    raise Exception(f"Failed to load DLL: {e}")

# Map SDK functions
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


# Utility wrappers
def init_usb():
    res = sdk.initializeUSB(1)
    if res == 0:
        print("[OK] USB initialized")
        return True
    else:
        print(f"[ERROR] USB init failed (code={res})")
        return False


def close_usb():
    sdk.CloseUSB(1)
    print("[OK] USB closed")


def create_card(hotel_id, card_no, checkin_time, checkout_time, room_no):
    dai, LLock, pdoors = 0, 1, 0
    card_hex = create_string_buffer(200)
    res = sdk.GuestCard(
        1, hotel_id, card_no, dai, LLock, pdoors,
        checkin_time.encode(), checkout_time.encode(),
        room_no.encode(), card_hex
    )
    if res == 0:
        return {"status": "success", "card_data": card_hex.value.decode(errors="ignore")}
    else:
        return {"status": "error", "code": res}


def delete_card(hotel_id, card_hex_str):
    res = sdk.CardErase(1, hotel_id, card_hex_str.encode())
    if res == 0:
        return {"status": "success"}
    else:
        return {"status": "error", "code": res}


# ------------------ API Routes ------------------

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

    if not init_usb():
        raise HTTPException(status_code=500, detail="USB initialization failed")

    result = create_card(int(hotel_id), int(card_no), checkin_time, checkout_time, room_no)
    close_usb()
    if result["status"] == "success":
        # Store card info in the database
        cards_collection.insert_one({
            "hotel_id": hotel_id,
            "card_no": card_no,
            "checkin_time": checkin_time,
            "checkout_time": checkout_time,
            "room_no": room_no,
            "card_hex": result["card_data"]
        })
        return {"status": "success", "message": "Card creation successful", "card_data": result.get("card_data")}
    else:
        raise HTTPException(status_code=500, detail=f"Card creation failed (code={result.get('code')})")

@app.post("/delete_card")
async def api_delete_card(request: Request):
    data = await request.json()
    hotel_id = data.get("hotel_id")
    card_data = data.get("card_data")

    if not all([hotel_id, card_data]):
        raise HTTPException(status_code=400, detail="Missing required parameters")

    if not init_usb():
        raise HTTPException(status_code=500, detail="USB initialization failed")

    result = delete_card(int(hotel_id), card_data)
    close_usb()
    return result


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "SDK Agent is running"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
