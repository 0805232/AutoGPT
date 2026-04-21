"""Edge-case tests for Google Sheets block credential handling.

These pin the contract for the systemic auto-credential None-guard in
``Block._execute()``: any block with an auto-credential field (via
``GoogleDriveFileField`` etc.) that's called without resolved
credentials must surface a clean, user-facing ``BlockExecutionError``
— never a wrapped ``TypeError`` (missing required kwarg) or
``AttributeError`` deep in the provider SDK.
"""

import pytest

from backend.blocks.google.sheets import GoogleSheetsReadBlock
from backend.util.exceptions import BlockExecutionError


@pytest.mark.asyncio
async def test_sheets_read_missing_credentials_yields_clean_error():
    """Valid spreadsheet but no resolved credentials -> the systemic
    None-guard in ``Block._execute()`` yields a ``Missing credentials``
    error before ``run()`` is entered."""
    block = GoogleSheetsReadBlock()
    input_data = {
        "spreadsheet": {
            "id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            "name": "Test Spreadsheet",
            "mimeType": "application/vnd.google-apps.spreadsheet",
        },
        "range": "Sheet1!A1:B2",
    }

    with pytest.raises(BlockExecutionError, match="Missing credentials"):
        async for _ in block.execute(input_data):
            pass


@pytest.mark.asyncio
async def test_sheets_read_no_spreadsheet_still_hits_credentials_guard():
    """When neither spreadsheet nor credentials are present, the
    credentials guard fires first (it runs before we hand off to
    ``run()``). The user-facing message should still be the clean
    ``Missing credentials`` one, not an opaque ``TypeError``."""
    block = GoogleSheetsReadBlock()
    input_data = {"range": "Sheet1!A1:B2"}  # no spreadsheet, no credentials

    with pytest.raises(BlockExecutionError, match="Missing credentials"):
        async for _ in block.execute(input_data):
            pass
