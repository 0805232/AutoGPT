"""Unit tests for merge_stats cost tracking in individual blocks.

Covers the exa code_context, exa contents, and apollo organization blocks
to verify provider cost is correctly extracted and reported.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from backend.data.model import APIKeyCredentials, NodeExecutionStats

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_EXA_CREDENTIALS = APIKeyCredentials(
    id="01234567-89ab-cdef-0123-456789abcdef",
    provider="exa",
    api_key=SecretStr("mock-exa-api-key"),
    title="Mock Exa API key",
    expires_at=None,
)

TEST_EXA_CREDENTIALS_INPUT = {
    "provider": TEST_EXA_CREDENTIALS.provider,
    "id": TEST_EXA_CREDENTIALS.id,
    "type": TEST_EXA_CREDENTIALS.type,
    "title": TEST_EXA_CREDENTIALS.title,
}


# ---------------------------------------------------------------------------
# ExaCodeContextBlock — cost_dollars is a string like "0.005"
# ---------------------------------------------------------------------------


class TestExaCodeContextBlockCostTracking:
    @pytest.mark.asyncio
    async def test_merge_stats_called_with_float_cost(self):
        """float(cost_dollars) parsed from API string and passed to merge_stats."""
        from backend.blocks.exa.code_context import ExaCodeContextBlock

        block = ExaCodeContextBlock()

        api_response = {
            "requestId": "req-1",
            "query": "how to use hooks",
            "response": "Here are some examples...",
            "resultsCount": 3,
            "costDollars": "0.005",
            "searchTime": 1.2,
            "outputTokens": 100,
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response

        accumulated: list[NodeExecutionStats] = []

        with (
            patch(
                "backend.blocks.exa.code_context.Requests.post",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
            patch.object(
                block, "merge_stats", side_effect=lambda s: accumulated.append(s)
            ),
        ):
            input_data = ExaCodeContextBlock.Input(
                query="how to use hooks",
                credentials=TEST_EXA_CREDENTIALS_INPUT,  # type: ignore[arg-type]
            )
            results = []
            async for output in block.run(
                input_data,
                credentials=TEST_EXA_CREDENTIALS,
            ):
                results.append(output)

        assert len(accumulated) == 1
        assert accumulated[0].provider_cost == pytest.approx(0.005)

    @pytest.mark.asyncio
    async def test_invalid_cost_dollars_does_not_raise(self):
        """When cost_dollars cannot be parsed as float, merge_stats is not called."""
        from backend.blocks.exa.code_context import ExaCodeContextBlock

        block = ExaCodeContextBlock()

        api_response = {
            "requestId": "req-2",
            "query": "query",
            "response": "response",
            "resultsCount": 0,
            "costDollars": "N/A",
            "searchTime": 0.5,
            "outputTokens": 0,
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response

        merge_calls: list[NodeExecutionStats] = []

        with (
            patch(
                "backend.blocks.exa.code_context.Requests.post",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
            patch.object(
                block, "merge_stats", side_effect=lambda s: merge_calls.append(s)
            ),
        ):
            input_data = ExaCodeContextBlock.Input(
                query="query",
                credentials=TEST_EXA_CREDENTIALS_INPUT,  # type: ignore[arg-type]
            )
            async for _ in block.run(
                input_data,
                credentials=TEST_EXA_CREDENTIALS,
            ):
                pass

        assert merge_calls == []

    @pytest.mark.asyncio
    async def test_zero_cost_is_tracked(self):
        """A zero cost_dollars string '0.0' should still be recorded."""
        from backend.blocks.exa.code_context import ExaCodeContextBlock

        block = ExaCodeContextBlock()

        api_response = {
            "requestId": "req-3",
            "query": "query",
            "response": "...",
            "resultsCount": 1,
            "costDollars": "0.0",
            "searchTime": 0.1,
            "outputTokens": 10,
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response

        accumulated: list[NodeExecutionStats] = []

        with (
            patch(
                "backend.blocks.exa.code_context.Requests.post",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
            patch.object(
                block, "merge_stats", side_effect=lambda s: accumulated.append(s)
            ),
        ):
            input_data = ExaCodeContextBlock.Input(
                query="query",
                credentials=TEST_EXA_CREDENTIALS_INPUT,  # type: ignore[arg-type]
            )
            async for _ in block.run(
                input_data,
                credentials=TEST_EXA_CREDENTIALS,
            ):
                pass

        assert len(accumulated) == 1
        assert accumulated[0].provider_cost == 0.0


# ---------------------------------------------------------------------------
# ExaContentsBlock — response.cost_dollars.total (CostDollars model)
# ---------------------------------------------------------------------------


class TestExaContentsBlockCostTracking:
    @pytest.mark.asyncio
    async def test_merge_stats_called_with_cost_dollars_total(self):
        """provider_cost equals response.cost_dollars.total when present."""
        from backend.blocks.exa.contents import ExaContentsBlock
        from backend.blocks.exa.helpers import CostDollars

        block = ExaContentsBlock()

        cost_dollars = CostDollars(total=0.012)

        mock_response = MagicMock()
        mock_response.results = []
        mock_response.context = None
        mock_response.statuses = None
        mock_response.cost_dollars = cost_dollars

        accumulated: list[NodeExecutionStats] = []

        with (
            patch(
                "backend.blocks.exa.contents.AsyncExa",
                return_value=MagicMock(
                    get_contents=AsyncMock(return_value=mock_response)
                ),
            ),
            patch.object(
                block, "merge_stats", side_effect=lambda s: accumulated.append(s)
            ),
        ):
            input_data = ExaContentsBlock.Input(
                urls=["https://example.com"],
                credentials=TEST_EXA_CREDENTIALS_INPUT,  # type: ignore[arg-type]
            )
            async for _ in block.run(
                input_data,
                credentials=TEST_EXA_CREDENTIALS,
            ):
                pass

        assert len(accumulated) == 1
        assert accumulated[0].provider_cost == pytest.approx(0.012)

    @pytest.mark.asyncio
    async def test_no_merge_stats_when_cost_dollars_absent(self):
        """When response.cost_dollars is None, merge_stats is not called."""
        from backend.blocks.exa.contents import ExaContentsBlock

        block = ExaContentsBlock()

        mock_response = MagicMock()
        mock_response.results = []
        mock_response.context = None
        mock_response.statuses = None
        mock_response.cost_dollars = None

        accumulated: list[NodeExecutionStats] = []

        with (
            patch(
                "backend.blocks.exa.contents.AsyncExa",
                return_value=MagicMock(
                    get_contents=AsyncMock(return_value=mock_response)
                ),
            ),
            patch.object(
                block, "merge_stats", side_effect=lambda s: accumulated.append(s)
            ),
        ):
            input_data = ExaContentsBlock.Input(
                urls=["https://example.com"],
                credentials=TEST_EXA_CREDENTIALS_INPUT,  # type: ignore[arg-type]
            )
            async for _ in block.run(
                input_data,
                credentials=TEST_EXA_CREDENTIALS,
            ):
                pass

        assert accumulated == []


# ---------------------------------------------------------------------------
# SearchOrganizationsBlock — provider_cost = float(len(organizations))
# ---------------------------------------------------------------------------


class TestSearchOrganizationsBlockCostTracking:
    @pytest.mark.asyncio
    async def test_merge_stats_called_with_org_count(self):
        """provider_cost == number of returned organizations, type == 'items'."""
        from backend.blocks.apollo._auth import TEST_CREDENTIALS as APOLLO_CREDS
        from backend.blocks.apollo._auth import (
            TEST_CREDENTIALS_INPUT as APOLLO_CREDS_INPUT,
        )
        from backend.blocks.apollo.models import Organization
        from backend.blocks.apollo.organization import SearchOrganizationsBlock

        block = SearchOrganizationsBlock()

        fake_orgs = [Organization(id=str(i), name=f"Org{i}") for i in range(3)]

        accumulated: list[NodeExecutionStats] = []

        with (
            patch.object(
                SearchOrganizationsBlock,
                "search_organizations",
                new_callable=AsyncMock,
                return_value=fake_orgs,
            ),
            patch.object(
                block, "merge_stats", side_effect=lambda s: accumulated.append(s)
            ),
        ):
            input_data = SearchOrganizationsBlock.Input(
                credentials=APOLLO_CREDS_INPUT,  # type: ignore[arg-type]
            )
            results = []
            async for output in block.run(
                input_data,
                credentials=APOLLO_CREDS,
            ):
                results.append(output)

        assert len(accumulated) == 1
        assert accumulated[0].provider_cost == pytest.approx(3.0)
        assert accumulated[0].provider_cost_type == "items"

    @pytest.mark.asyncio
    async def test_empty_org_list_tracks_zero(self):
        """An empty organization list results in provider_cost=0.0."""
        from backend.blocks.apollo._auth import TEST_CREDENTIALS as APOLLO_CREDS
        from backend.blocks.apollo._auth import (
            TEST_CREDENTIALS_INPUT as APOLLO_CREDS_INPUT,
        )
        from backend.blocks.apollo.organization import SearchOrganizationsBlock

        block = SearchOrganizationsBlock()
        accumulated: list[NodeExecutionStats] = []

        with (
            patch.object(
                SearchOrganizationsBlock,
                "search_organizations",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                block, "merge_stats", side_effect=lambda s: accumulated.append(s)
            ),
        ):
            input_data = SearchOrganizationsBlock.Input(
                credentials=APOLLO_CREDS_INPUT,  # type: ignore[arg-type]
            )
            async for _ in block.run(
                input_data,
                credentials=APOLLO_CREDS,
            ):
                pass

        assert len(accumulated) == 1
        assert accumulated[0].provider_cost == 0.0
        assert accumulated[0].provider_cost_type == "items"
