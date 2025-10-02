import ctypes
from ctypes import c_int, c_ubyte, create_string_buffer

# Load the DLL
sdk = ctypes.WinDLL("C:\\Users\\chinedu.orjiogo\\Documents\\Rolak_keycard\\proRFL.dll")
if not sdk:
    raise Exception("Failed to load DLL")
print(f"DLL loaded successfully from {sdk._name}")

# -------------------------------
# Map SDK functions
# -------------------------------

# int __stdcall GetDLLVersion(uchar* bufVer)
sdk.GetDLLVersion.argtypes = [ctypes.c_char_p]
sdk.GetDLLVersion.restype = c_int

# int __stdcall initializeUSB(uchar d12)
sdk.initializeUSB.argtypes = [c_ubyte]
sdk.initializeUSB.restype = c_int

# void __stdcall CloseUSB(uchar d12)
sdk.CloseUSB.argtypes = [c_ubyte]
sdk.CloseUSB.restype = None

# int __stdcall Buzzer(uchar d12, unsigned char t)
sdk.Buzzer.argtypes = [c_ubyte, c_ubyte]
sdk.Buzzer.restype = c_int

# int __stdcall GuestCard(...)
sdk.GuestCard.argtypes = [
    c_ubyte,      # d12 (1 = proUSB)
    c_int,        # dlsCoID
    c_ubyte,      # CardNo
    c_ubyte,      # dai
    c_ubyte,      # LLock
    c_ubyte,      # pdoors
    ctypes.c_char_p,  # BDate[10]
    ctypes.c_char_p,  # EDate[10]
    ctypes.c_char_p,  # LockNo[8]
    ctypes.c_char_p   # cardHexStr (output buffer)
]
sdk.GuestCard.restype = c_int

# int __stdcall CardErase(uchar d12, int dlsCoID, unsigned char* cardHexStr)
sdk.CardErase.argtypes = [c_ubyte, c_int, ctypes.c_char_p]
sdk.CardErase.restype = c_int


# --------------------------------------------------------
# Utility functions
# --------------------------------------------------------

def init_usb():
    """Initialize USB connection to encoder"""
    result = sdk.initializeUSB(1)
    if result == 0:
        print("[OK] USB initialized")
    else:
        print(f"[ERROR]: USB init failed (code={result})")
    return result

def close_usb():
    """Close USB connection"""
    sdk.CloseUSB(1)
    print("[OK] USB closed")

def create_card(hotel_id, card_no, begin_time, end_time, room_no):
    """
    Issue a customer keycard.
    begin_time / end_time format: YYMMDDHHmm
    room_no: 8-digit string, e.g. "00001234"
    """
    dai = 0
    LLock = 1   # allow door lock
    pdoors = 0
    card_hex = create_string_buffer(200)

    res = sdk.GuestCard(
        1, hotel_id, card_no, dai, LLock, pdoors,
        begin_time.encode(), end_time.encode(),
        room_no.encode(), card_hex
    )

    if res == 0:
        print("[OK] Card created successfully")
        print("Card Data:", card_hex.value.decode(errors="ignore"))
        return card_hex.value.decode(errors="ignore")
    else:
        print(f"[ERROR] Card creation failed (code={res})")
        return None

def delete_card(hotel_id, card_hex_str):
    """Erase or invalidate a customer keycard"""
    res = sdk.CardErase(1, hotel_id, card_hex_str.encode())
    if res == 0:
        print("[OK] Card deleted successfully")
    else:
        print(f"[ERROR] Card deletion failed (code={res})")
    return res


# --------------------------------------------------------
# Example usage
# --------------------------------------------------------
if __name__ == "__main__":
    if init_usb() == 0:
        # Example: Create a card
        card_data = create_card(
            hotel_id=1234,
            card_no=1,
            begin_time="2509181200",  # YYMMDDHHmm
            end_time="2509201100",
            room_no="00001234"
        )

        if card_data:
            # Example: Delete the same card
            delete_card(1234, card_data)

        close_usb()
