# modbus-tcp-clock-server
Modbus TCP Clock Server

Modbus server exposes the current system time via Holding Registers.

| Register | Name   | Range / Example |
|-----------|--------|-----------------|
| 0 | Day | 1–31 |
| 1 | Month | 1–12 |
| 2 | Year | e.g., 2025 |
| 3 | Hour | 0–23 |
| 4 | Minute | 0–59 |
| 5 | Second | 0–59 |


Notes
-----
- Binds to all interfaces by default (0.0.0.0) on TCP port 502. Use --port nnn if you want to use another port (--port 502).
- Logs all activity to console and to a rotating log file.
- Prints each Modbus request (raw hex) and a parsed summary.
- Supports Function Code 0x03 (Read Holding Registers). Other function codes receive an Illegal Function (0x01) exception response.
- Logs all connections and requests to console and a rotating log file
- Displays each Modbus request (raw hex + parsed)
- Runs on all interfaces by default (`0.0.0.0`)

---

### 🚀 Quick Start
#### 1️⃣ Clone the repository
```bash
git clone https://github.com/gesteen/modbus-tcp-clock-server.git
cd modbus-tcp-clock-server
```


#### 2️⃣ Create a virtual environment (recommended)
```bash
python3 -m venv venv
source venv/bin/activate # On Windows: venv\Scripts\activate
```


#### 3️⃣ Run the server
```bash
python modbus_clock_server.py --host 0.0.0.0 --port 502
```
> Default port: **502** (non-privileged). Use other port if needed `--port 5020`.

---


### 🧪 Test With a Modbus Client
Use any Modbus client (e.g., **Modbus Poll**, **QModMaster**, or **pymodbus**).
- **Function Code:** 3 (Read Holding Registers)
- **Start Address:** 0
- **Quantity:** 6
- **Server Address:** `localhost`
- **Port:** 502


You’ll receive the system time as register values.


---


### 🪵 Logging
- Console output includes client connects/disconnects and raw Modbus requests.
- File logging defaults to `modbus_server.log` with rotation (5 MB × 5 backups).


---

---


### 🧰 Build a One-File Executable (Windows/macOS/Linux)
Use **PyInstaller** to distribute a standalone executable:
```bash
pip install pyinstaller
pyinstaller --onefile --name modbus_clock_server modbus_clock_server.py
```
Find the output in the `dist/` directory.


---

