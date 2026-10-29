"""Real locked DBAPI codec regression; no network, database or credentials."""

import asyncio
from datetime import datetime

import aiomysql
import pytest
from pymysql.constants import SERVER_STATUS

from app.core.db_connection import TLSRequiredConnection
from app.db.models import subject_digest


@pytest.fixture
def connection():
    loop = asyncio.new_event_loop()
    connection = TLSRequiredConnection(loop=loop, charset="utf8mb4", local_infile=False)
    connection.server_status = 0
    try:
        yield connection
    finally:
        connection.close()
        loop.close()


@pytest.mark.parametrize("no_backslash", [False, True])
@pytest.mark.parametrize(
    "value",
    [
        b"",
        bytes(range(256)),
        b"'\\\x00\n\r\x1a;--?%",
        subject_digest("urn:ditnow:student-login:demo:v1", "DITDEMO_A"),
        bytearray(b"\x00'\\\xff"),
    ],
)
def test_binary_bindings_are_lossless_hex_and_independent_of_sql_mode(
    connection, value, no_backslash
):
    connection.server_status = (
        SERVER_STATUS.SERVER_STATUS_NO_BACKSLASH_ESCAPES if no_backslash else 0
    )
    encoded = connection.escape(value)
    assert encoded == f"X'{value.hex()}'"
    assert bytes.fromhex(encoded[2:-1]) == bytes(value)
    assert set(encoded[2:-1]) <= set("0123456789abcdef")


@pytest.mark.parametrize("value", [None, True, 42, "가상 '문자열'", datetime(2026, 10, 30)])
def test_other_parameter_types_preserve_the_locked_driver_behavior(connection, value):
    assert connection.escape(value) == aiomysql.Connection.escape(connection, value)
