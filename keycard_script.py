from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import ctypes
from ctypes import (
    c_int, c_ubyte, c_char_p,
    POINTER, create_string_buffer
)
import threading
import logging
import time
import uvicorn
from mongodb import connect_to_database

# -----------------------------------------------------
# 1️⃣ App & Logging
# -----------------------------------------------------
app = FastAPI(title="ProRFL SDK Agent")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

sdk_lock = threading.Lock()

# -----------------------------------------------------
# 2️⃣ Database
# -----------------------------------------------------
db = connect_to_database()["keycard_db"]
cards = db["cards"]

# -----------------------------------------------------
# 3️⃣ Load DLL
# -----------------------------------------------------
sdk = ctypes.WinDLL(r"C:\Users\chinedu.orjiogo\Documents\Rolak_keycard\proRFL.dll")

# -----------------------------------------------------
# 4️⃣ SDK Function Mapping
# -----------------------------------------------------
sdk.initializeUSB.argtypes = [c_ubyte]
sdk.initializeUSB.restype = c_int

sdk.CloseUSB.argtypes = [c_ubyte]

sdk.Buzzer.argtypes = [c_ubyte, c_ubyte]
sdk.Buzzer.restype = c_int

sdk.GuestCard.argtypes = [
    c_ubyte, c_int, c_ubyte, c_ubyte,
    c_ubyte, c_ubyte,
    c_char_p, c_char_p,
    POINTER(c_ubyte),
    c_char_p
]
sdk.GuestCard.restype = c_int

sdk.ReadCard.argtypes = [c_ubyte, c_char_p]
sdk.ReadCard.restype = c_int

sdk.CardErase.argtypes = [c_ubyte, c_int, c_char_p]
sdk.CardErase.restype = c_int

sdk.ReadRecord.argtypes = [c_ubyte, POINTER(c_ubyte)]
sdk.ReadRecord.restype = c_int

sdk.GetOpenRecordByDataStr.argtypes = [POINTER(c_ubyte), POINTER(c_ubyte)]
sdk.GetOpenRecordByDataStr.restype = c_int

# -----------------------------------------------------
# 5️⃣ Helpers
# -----------------------------------------------------
TOTAL_ROOMS = 16

def init_usb():
    return sdk.initializeUSB(1) == 0

def close_usb():
    sdk.CloseUSB(1)

def buzzer(ms=300):
    sdk.Buzzer(1, ms // 10)

def lockstr_to_bytes(lockstr: str):
    if len(lockstr) != 8:
        raise ValueError("LockNo must be exactly 8 chars")
    return (c_ubyte * 8)(*[ord(c) for c in lockstr])

def convert_date(d):
    day, mon, year = d.split("-")
    months = {
        "Jan":"01","Feb":"02","Mar":"03","Apr":"04",
        "May":"05","Jun":"06","Jul":"07","Aug":"08",
        "Sep":"09","Oct":"10","Nov":"11","Dec":"12"
    }
    return f"{year[-2:]}{months[mon]}{day.zfill(2)}0000"

# -----------------------------------------------------
# 6️⃣ Core SDK Operations
# -----------------------------------------------------
def create_card(hotel_id, card_no, bdate, edate, lock_bytes):
    dai = 0  # 🔧 SAFETY GUARD: NEVER CHANGE
    buf = create_string_buffer(200)

    res = sdk.GuestCard(
        1, hotel_id, card_no,
        dai, 1, 1,
        bdate.encode(),
        edate.encode(),
        lock_bytes,
        buf
    )
    return res, buf.value.decode(errors="ignore").rstrip("\x00")

def read_card():
    buf = create_string_buffer(200)
    res = sdk.ReadCard(1, buf)
    return res, buf.value

def erase_card(hotel_id, card_hex):
    return sdk.CardErase(1, hotel_id, card_hex.encode())

def get_opened_doors():
    doors = (c_ubyte * 64)()
    res = sdk.ReadRecord(1, doors)
    return res, list(doors)

def decode_open_record(card_data):
    data = (c_ubyte * len(card_data))(*card_data)
    out = (c_ubyte * 32)()
    res = sdk.GetOpenRecordByDataStr(data, out)
    return res, list(out)

# -----------------------------------------------------
# 7️⃣ API Endpoints
# -----------------------------------------------------
@app.post("/create_card")
async def api_create(req: Request):
    d = await req.json()
    print(d)

    lock_bytes = lockstr_to_bytes(d["lock_no"])
    bdate = convert_date(d["checkin_time"])
    edate = convert_date(d["checkout_time"])

    print(f"Creating card for HotelID {d['hotel_id']}, CardNo {d['card_no']}, LockNo {d['lock_no']}, From {bdate} To {edate}")

    with sdk_lock:
        if not init_usb():
            raise HTTPException(500, "USB init failed")

        try:
            if TOTAL_ROOMS <= 0:
                raise HTTPException(500, "No rooms available")
            
            res, hexdata = create_card(
                int(d["hotel_id"]),
                int(d["card_no"]),
                bdate, edate,
                lock_bytes
            )
            buzzer()

            if res != 0:
                raise HTTPException(500, f"SDK error {res}")
            
            TOTAL_ROOMS -= 1  # 🔧 SAFETY GUARD: NEVER REMOVE

            cards.insert_one({
                "hotel_id": d["hotel_id"],
                "card_no": d["card_no"],
                "lock_no": d["lock_no"],
                "card_hex": hexdata,
                "dai": 0,
                "created_at": time.time()
            })

            return {"status": "success", "card_hex": hexdata}
        finally:
            close_usb()

@app.post("/inspect_card")
async def api_inspect():
    """
    Reads card, opened doors, and decoded open records
    """
    with sdk_lock:
        if not init_usb():
            raise HTTPException(500, "USB init failed")

        try:
            res, raw = read_card()
            if res != 0:
                raise HTTPException(500, "Read failed")

            doors_res, doors = get_opened_doors()
            rec_res, record = decode_open_record(raw)

            return {
                "card_data": raw.decode(errors="ignore"),
                "opened_doors": doors if doors_res == 0 else None,
                "open_record": record if rec_res == 0 else None
            }
        finally:
            close_usb()

@app.post("/delete_card")
async def api_delete():
    with sdk_lock:
        if not init_usb():
            raise HTTPException(500, "USB init failed")

        try:
            card_hex = read_card()
            if not card_hex:
                raise HTTPException(400, "Failed to read card")

            rec = cards.find_one({"card_hex": card_hex})
            if not rec:
                raise HTTPException(404, "Card not found in database")

            res = erase_card(rec["hotel_id"], card_hex)
            buzzer()

            if res != 0:
                raise HTTPException(500, "Erase failed")

            TOTAL_ROOMS += 1  # advisory counter

            return {
                "status": "success",
                "card_no": rec["card_no"],
                "lock_no": rec["lock_no"]
            }

        finally:
            close_usb()


@app.get("/stats")
async def api_stats():
    total_cards = cards.count_documents({})
    return {
        "total_cards_issued": total_cards,
        "available_rooms": TOTAL_ROOMS
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

# -----------------------------------------------------
# 8️⃣ Run
# -----------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
