# 🏨 Rolak Keycard Management API

A simple RESTful API built with **Python (Flask)** for managing hotel keycard creation and synchronization between hotel systems and keycard encoders.

---

## 🚀 Overview

The **Rolak Keycard Management API** provides endpoints to generate and manage digital keycards for hotel rooms.  
It integrates seamlessly with physical keycard encoders and hotel property management systems (PMS), offering an easy-to-use interface for automation and centralized control.

---

## 🧠 Features

- 🪪 Create and encode keycards  
- 🕒 Define access time windows (`checkin_time`, `checkout_time`)  
- 🏠 Assign cards to specific rooms  
- 🧩 Simple JSON-based request body  
- ⚙️ Local deployment with `venv` (Python 32-bit)

---

## 📦 Tech Stack

- **Language:** Python 3.11 (32-bit)  
- **Framework:** Flask  
- **Runtime:** venv32 (Virtual Environment)  
- **API Testing:** Postman / cURL

---

## 🧰 Installation

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/avetiumconsult/Rolak_keycard
cd rolak-keycard-api
````

### 2️⃣ Set Up Virtual Environment (32-bit)

Ensure you have **Python 32-bit** installed.
Create and activate the virtual environment:

```bash
python -m venv venv32
venv32\Scripts\activate    # On Windows
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuration

Update your `.env` or environment variables if required (e.g., encoder paths, serial ports, etc.):

```bash
FLASK_APP=app.py
FLASK_ENV=development
```

---

## ▶️ Running the API

```bash
python app.py
uvicorn keycard_script:app --reload
```

Your API will be available at:

```
http://localhost:5000
```

---

## 📮 API Endpoints

### **POST** `/create_card`

**Description:**
Creates a new keycard for a given hotel room.

**Request Body:**

```json
{
  "hotel_id": 1234,
  "card_no": 1,
  "begin_time": "2509181200",
  "end_time": "2509201100",
  "room_no": "00001234"
}
```

**Response (200):**

```json
{
  "status": "success",
  "message": "Card created successfully",
  "card_id": "8dfc9abe-9e0a-4ac4-8e6d-e754499da8bb"
}
```

**Response (500):**

```json
{
  "status": "error",
  "message": "Internal Server Error"
}
```

---

## 🧪 Testing with Postman

1. Open Postman
2. Create a new **POST** request to:

   ```
   http://localhost:5000/create_card
   ```
3. Set **Headers:**

   ```
   Content-Type: application/json
   ```
4. Add the JSON body above and **Send**.

---

## 🧾 requirements.txt

Example:

```
Flask==3.0.3
python_version == "3.11.8-32bit"
```

> 🧩 Include your Python architecture (32-bit) in documentation for compatibility assurance.

---

## 🧠 Troubleshooting

| Issue                       | Possible Cause                      | Solution                             |
| --------------------------- | ----------------------------------- | ------------------------------------ |
| `Internal Server Error`     | Invalid JSON or missing field       | Check request format                 |
| `Port number not a decimal` | Incorrect cURL syntax on PowerShell | Use backticks (`) or Postman instead |
| Dependencies not found      | Virtual environment not active      | Run `venv32\Scripts\activate`        |

---

## 👨‍💻 Author

**Chinedu Orjiogo**
Backend Developer | Systems Integrator
📧 [Email](mailto:plance991@gmail.com)
🌐 [GitHub](https://github.com/tempahh)

---

## 🪪 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

```