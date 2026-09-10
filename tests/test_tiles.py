"""The local imagery cache: MBTiles files on the station, served by TRACK.

Nothing here reaches a network. The fixture builds a two-tile MBTiles file
with the standard library, exactly the shape a sourced layer has.
"""

from __future__ import annotations

import sqlite3
import struct
import zlib
from pathlib import Path

import httpx
import pytest

from track.app import create_app
from track.config import Settings

from tests.conftest import OPERATOR_TOKEN


def a_png(red: int, green: int, blue: int) -> bytes:
    """A 1x1 opaque PNG, written by hand so the test owns every byte."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00" + bytes((red, green, blue))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


NORTH_TILE = a_png(10, 20, 30)  # xyz y=0 at z=1, stored at tms row 1
SOUTH_TILE = a_png(200, 210, 220)  # xyz y=1 at z=1, stored at tms row 0


def write_mbtiles(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE metadata (name TEXT, value TEXT);
        CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);
        """
    )
    conn.executemany(
        "INSERT INTO metadata VALUES (?, ?)",
        [
            ("name", "Test site imagery"),
            ("format", "png"),
            ("bounds", "-0.13,51.50,-0.11,51.51"),
            ("minzoom", "1"),
            ("maxzoom", "1"),
            ("attribution", "Test imagery"),
        ],
    )
    conn.executemany(
        "INSERT INTO tiles VALUES (?, ?, ?, ?)",
        [(1, 0, 1, NORTH_TILE), (1, 0, 0, SOUTH_TILE)],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def tiles_dir(tmp_path) -> Path:
    directory = tmp_path / "tiles"
    directory.mkdir()
    write_mbtiles(directory / "site.mbtiles")
    return directory


@pytest.fixture
def settings(tmp_path, tiles_dir) -> Settings:
    return Settings(
        db_path=str(tmp_path / "track.db"),
        tokens_path=str(tmp_path / "tokens.yaml"),
        tiles_dir=str(tiles_dir),
        topic_prefix="testsite",
    )


async def test_the_cache_lists_its_layers(client):
    response = await client.get("/v1/tiles")
    assert response.status_code == 200
    assert response.json() == {
        "layers": [
            {
                "id": "site",
                "name": "Test site imagery",
                "format": "png",
                "attribution": "Test imagery",
                "bounds": [-0.13, 51.50, -0.11, 51.51],
                "min_zoom": 1,
                "max_zoom": 1,
            }
        ]
    }


async def test_a_tile_round_trips_with_the_tms_flip(client):
    """The map asks in XYZ, the file stores TMS. y=0 at z=1 is the north
    row on the map and row 1 in the file."""
    response = await client.get("/v1/tiles/site/1/0/0")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, max-age=86400"
    assert response.content == NORTH_TILE

    south = await client.get("/v1/tiles/site/1/0/1")
    assert south.content == SOUTH_TILE


async def test_a_missing_tile_is_refused_in_plain_words(client):
    response = await client.get("/v1/tiles/site/1/1/0")
    assert response.status_code == 404
    assert response.json()["detail"] == "There is no imagery for that part of the map."


async def test_a_missing_layer_is_refused_in_plain_words(client):
    response = await client.get("/v1/tiles/nowhere/1/0/0")
    assert response.status_code == 404
    assert response.json()["detail"] == "There is no map imagery called that on this station."


async def test_tiles_need_a_caller_and_accept_the_token_as_a_query(app):
    """An <img> cannot carry a header, so the tile route takes ?token= the
    way the live stream does. The listing does not."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://server"
    ) as anonymous:
        assert (await anonymous.get("/v1/tiles")).status_code == 401
        assert (await anonymous.get("/v1/tiles/site/1/0/0")).status_code == 401
        assert (await anonymous.get("/v1/tiles/site/1/0/0?token=wrong")).status_code == 401
        by_query = await anonymous.get(f"/v1/tiles/site/1/0/0?token={OPERATOR_TOKEN}")
        assert by_query.status_code == 200
        assert by_query.content == NORTH_TILE


async def test_an_empty_cache_lists_no_layers(tmp_path, store, transport, bus, tokens):
    """A fresh station has no imagery and says so, whether the directory is
    empty or was never created."""
    for directory in (tmp_path / "empty", tmp_path / "never-made"):
        if directory.name == "empty":
            directory.mkdir()
        settings = Settings(
            db_path=str(tmp_path / "track.db"),
            tokens_path=str(tmp_path / "tokens.yaml"),
            tiles_dir=str(directory),
            topic_prefix="testsite",
        )
        application = create_app(
            settings=settings, transport=transport, store=store, bus=bus, tokens=tokens
        )
        async with application.router.lifespan_context(application):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application),
                base_url="http://server",
                headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"},
            ) as client:
                assert (await client.get("/v1/tiles")).json() == {"layers": []}
