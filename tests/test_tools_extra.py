"""Tests for get_cell, move_row, and validate_tables via FastMCP in-memory Client."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from tablestakes.server import mcp
from tests.conftest import read_version, text_of, version_of

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def pipe_md(tmp_path: Path) -> Path:
    f = tmp_path / "test.md"
    f.write_text(
        "# Test\n\n"
        "| Name | Age | City |\n"
        "| --- | --- | --- |\n"
        "| Alice | 30 | NYC |\n"
        "| Bob | 25 | LA |\n"
        "| Carol | 35 | SF |\n"
        "\nEnd.\n"
    )
    return f


class TestGetCell:
    async def test_get_cell_by_name(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "get_cell",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "row_index": 1,
                        "column": "Name",
                    },
                )
            )
            assert "v:" in text
            assert "Bob" in text

    async def test_get_cell_by_letter(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "get_cell",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "row_index": 0,
                        "column": "B",
                    },
                )
            )
            assert "30" in text

    async def test_get_cell_row_out_of_range(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "get_cell",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "row_index": 99,
                        "column": "A",
                    },
                )
            )
            data = json.loads(text)
            assert data["error"] == "ROW_NOT_FOUND"

    async def test_get_cell_column_not_found(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "get_cell",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "row_index": 0,
                        "column": "Z:Nope",
                    },
                )
            )
            data = json.loads(text)
            assert data["error"] == "COLUMN_NOT_FOUND"


class TestMoveRow:
    async def test_move_down(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "move_row",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "from_index": 0,
                        "to_index": 2,
                    },
                )
            )
            assert version_of(text)
            content = pipe_md.read_text()
            names = [line.split("|")[1].strip() for line in content.splitlines() if line.startswith("| ")]
            data_names = [n for n in names if n in {"Alice", "Bob", "Carol"}]
            assert data_names == ["Bob", "Carol", "Alice"]

    async def test_move_to_end(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "move_row",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "from_index": 0,
                    "to_index": -1,
                },
            )
            content = pipe_md.read_text()
            names = [line.split("|")[1].strip() for line in content.splitlines() if line.startswith("| ")]
            data_names = [n for n in names if n in {"Alice", "Bob", "Carol"}]
            assert data_names == ["Bob", "Carol", "Alice"]

    async def test_move_out_of_range(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "move_row",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "from_index": 99,
                        "to_index": 0,
                    },
                )
            )
            data = json.loads(text)
            assert data["error"] == "EDIT_ERROR"

    async def test_move_stale_version(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 0, "column": "Age", "value": "31"}],
                },
            )
            text = text_of(
                await client.call_tool(
                    "move_row",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "from_index": 0,
                        "to_index": 1,
                    },
                )
            )
            data = json.loads(text)
            assert data["error"] == "STALE_READ"


class TestValidateTables:
    async def test_ok(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool("validate_tables", {"file_path": str(pipe_md)})
            )
            assert text.startswith("OK")

    async def test_missing_cells(self, tmp_path: Path) -> None:
        f = tmp_path / "ragged.md"
        f.write_text(
            "| Name | Age | City |\n"
            "| --- | --- | --- |\n"
            "| Alice | 30 | NYC |\n"
            "| Bob | 25 |\n"
        )
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool("validate_tables", {"file_path": str(f)})
            )
            assert "issue" in text
            assert "row1: 2 cells (expected 3)" in text

    async def test_duplicate_keys(self, tmp_path: Path) -> None:
        f = tmp_path / "dupes.md"
        f.write_text(
            "| Name | Age |\n"
            "| --- | --- |\n"
            "| Alice | 30 |\n"
            "| Bob | 25 |\n"
            "| Alice | 41 |\n"
        )
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "validate_tables", {"file_path": str(f), "key_column": "A"}
                )
            )
            assert "duplicate" in text
            assert "row2" in text

    async def test_single_table_index(self, tmp_path: Path) -> None:
        f = tmp_path / "two.md"
        f.write_text(
            "| A |\n| --- |\n| 1 |\n\n| B |\n| --- |\n| 2 |\n"
        )
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "validate_tables", {"file_path": str(f), "table_index": 0}
                )
            )
            assert text.startswith("OK")
