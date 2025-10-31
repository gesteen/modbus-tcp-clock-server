
#!/usr/bin/env python3
"""
Modbus TCP server that exposes the current system time via Holding Registers.

Registers (0-based addresses):
  0: Day     (1-31)
  1: Month   (1-12)
  2: Year    (e.g., 2025)
  3: Hour    (0-23)
  4: Minute  (0-59)
  5: Second  (0-59)

Notes
-----
* Binds to all interfaces by default (0.0.0.0) on TCP port 502.
  Use --port 502 if you want the default Modbus port (requires admin/root on most OSes).
* Logs all activity to console and to a rotating log file.
* Prints each Modbus request (raw hex) and a parsed summary.
* Supports Function Code 0x03 (Read Holding Registers). Other function codes
  receive an Illegal Function (0x01) exception response.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
from logging.handlers import RotatingFileHandler
import socket
import struct
import threading
from typing import Tuple

# ---------------------------- Logging Setup ---------------------------- #

def setup_logging(log_file: str, verbose: bool = True) -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console
    if verbose:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    # Rotating file (5 MB per file, keep 5 backups)
    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)
    fh.setFormatter(fmt)
    logger.addHandler(fh)


# ---------------------------- Helpers ---------------------------- #

def hexdump(data: bytes, width: int = 16) -> str:
    return " ".join(f"{b:02X}" for b in data)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly n bytes or raise ConnectionError if the stream closes."""
    chunks = []
    bytes_recd = 0
    while bytes_recd < n:
        chunk = sock.recv(n - bytes_recd)
        if not chunk:
            raise ConnectionError("Socket closed while receiving data")
        chunks.append(chunk)
        bytes_recd += len(chunk)
    return b"".join(chunks)


# ---------------------------- Clock Data ---------------------------- #

def read_clock_registers(start: int, count: int) -> Tuple[int, ...]:
    """Return a tuple of register values from the live system clock.

    This server exposes 6 holding registers starting at address 0.
    Requests beyond that range raise an IndexError to signal illegal address.
    """
    now = dt.datetime.now()
    registers = (
        now.day,
        now.month,
        now.year,
        now.hour,
        now.minute,
        now.second,
    )

    end = start + count
    if start < 0 or end > len(registers):
        raise IndexError("Illegal register address range")
    return registers[start:end]


# ---------------------------- Modbus Protocol ---------------------------- #

# Exception codes
ILLEGAL_FUNCTION = 0x01
ILLEGAL_DATA_ADDRESS = 0x02
ILLEGAL_DATA_VALUE = 0x03


def build_exception_response(transaction_id: int, protocol_id: int, unit_id: int, function: int, ex_code: int) -> bytes:
    pdu = struct.pack("BB", function | 0x80, ex_code)
    # Length field = UnitId(1) + PDU length
    length = 1 + len(pdu)
    mbap = struct.pack(">HHHB", transaction_id, protocol_id, length, unit_id)
    return mbap + pdu


def build_fc3_response(transaction_id: int, protocol_id: int, unit_id: int, values: Tuple[int, ...]) -> bytes:
    byte_count = len(values) * 2
    pdu_header = struct.pack("BB", 0x03, byte_count)
    # Each register is 2 bytes, big-endian
    regs = b"".join(struct.pack(">H", v & 0xFFFF) for v in values)
    pdu = pdu_header + regs
    length = 1 + len(pdu)  # UnitId + PDU
    mbap = struct.pack(">HHHB", transaction_id, protocol_id, length, unit_id)
    return mbap + pdu


def parse_mbap_header(hdr: bytes) -> Tuple[int, int, int, int]:
    transaction_id, protocol_id, length, unit_id = struct.unpack(">HHHB", hdr)
    return transaction_id, protocol_id, length, unit_id


# ---------------------------- Client Handler ---------------------------- #

def handle_client(conn: socket.socket, addr: Tuple[str, int], log: logging.Logger) -> None:
    peer = f"{addr[0]}:{addr[1]}"
    log.info(f"Client connected: {peer}")
    try:
        while True:
            # Read MBAP (7 bytes)
            hdr = recv_exact(conn, 7)
            transaction_id, protocol_id, length, unit_id = parse_mbap_header(hdr)
            # Read remaining bytes (length includes UnitId + PDU). We already read UnitId in hdr (1 byte),
            # so remaining PDU bytes = length - 1
            pdu = recv_exact(conn, length - 1)

            # Log raw request
            raw = hdr + pdu
            logging.info(
                "Request from %s | TID=%d UID=%d RAW=%s",
                peer,
                transaction_id,
                unit_id,
                hexdump(raw),
            )

            if not pdu:
                raise ConnectionError("Empty PDU received")

            function = pdu[0]

            # Function 0x03: Read Holding Registers
            if function == 0x03:
                if len(pdu) != 5:
                    # Malformed length
                    resp = build_exception_response(transaction_id, protocol_id, unit_id, function, ILLEGAL_DATA_VALUE)
                    conn.sendall(resp)
                    continue
                start_addr, qty = struct.unpack(">HH", pdu[1:5])
                logging.info(
                    "Parsed FC=0x03 from %s | Start=%d Qty=%d",
                    peer,
                    start_addr,
                    qty,
                )
                if qty < 1 or qty > 125:
                    resp = build_exception_response(transaction_id, protocol_id, unit_id, function, ILLEGAL_DATA_VALUE)
                    conn.sendall(resp)
                    continue
                try:
                    vals = read_clock_registers(start_addr, qty)
                except IndexError:
                    resp = build_exception_response(transaction_id, protocol_id, unit_id, function, ILLEGAL_DATA_ADDRESS)
                    conn.sendall(resp)
                    continue
                resp = build_fc3_response(transaction_id, protocol_id, unit_id, vals)
                conn.sendall(resp)
            else:
                # Unsupported function
                logging.info(
                    "Unsupported FC=0x%02X from %s — replying with Illegal Function",
                    function,
                    peer,
                )
                resp = build_exception_response(transaction_id, protocol_id, unit_id, function, ILLEGAL_FUNCTION)
                conn.sendall(resp)

    except (ConnectionError, OSError) as e:
        log.info(f"Client disconnected: {peer} ({e})")
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------- Server ---------------------------- #

def serve(host: str, port: int, log_file: str) -> None:
    setup_logging(log_file)
    log = logging.getLogger(__name__)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen()
        log.info(f"Modbus TCP Clock Server listening on {host}:{port}")
        log.info("Registers exposed (0-based): 0=Day, 1=Month, 2=Year, 3=Hour, 4=Minute, 5=Second")
        while True:
            conn, addr = s.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr, log), daemon=True)
            t.start()


# ---------------------------- CLI ---------------------------- #

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Modbus TCP server exposing system clock via holding registers")
    p.add_argument("--host", default="0.0.0.0", help="Host/IP to bind (default: 0.0.0.0 — all interfaces)")
    p.add_argument(
        "--port",
        type=int,
        default=502,
        help="TCP port to listen on (default: 502)",
    )
    p.add_argument("--log-file", default="modbus_server.log", help="Path to log file (default: modbus_server.log)")
    return p.parse_args()


def main():
    args = parse_args()
    try:
        serve(args.host, args.port, args.log_file)
    except PermissionError:
        print(
            "\n[ERROR] Permission denied binding to port. On Unix-like systems, ports <1024 require admin/root.\n"
            "       Try a higher port (e.g., --port 5020) or run with elevated privileges.\n"
        )
    except KeyboardInterrupt:
        print("\nShutting down…")


if __name__ == "__main__":
    main()
