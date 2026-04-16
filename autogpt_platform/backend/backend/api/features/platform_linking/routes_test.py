"""Route tests: domain exceptions → HTTPException status codes."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.util.exceptions import (
    LinkAlreadyExistsError,
    LinkFlowMismatchError,
    LinkTokenExpiredError,
    NotAuthorizedError,
    NotFoundError,
)


class TestTokenInfoRouteTranslation:
    @pytest.mark.asyncio
    async def test_not_found_maps_to_404(self):
        from backend.api.features.platform_linking.routes import (
            get_link_token_info_route,
        )

        with patch(
            "backend.api.features.platform_linking.routes.get_link_token_info",
            new=AsyncMock(side_effect=NotFoundError("Token not found.")),
        ):
            with pytest.raises(HTTPException) as exc:
                await get_link_token_info_route(token="abc")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_expired_maps_to_410(self):
        from backend.api.features.platform_linking.routes import (
            get_link_token_info_route,
        )

        with patch(
            "backend.api.features.platform_linking.routes.get_link_token_info",
            new=AsyncMock(side_effect=LinkTokenExpiredError("Token expired.")),
        ):
            with pytest.raises(HTTPException) as exc:
                await get_link_token_info_route(token="abc")
        assert exc.value.status_code == 410


class TestConfirmLinkRouteTranslation:
    @pytest.mark.asyncio
    async def test_not_found_maps_to_404(self):
        from backend.api.features.platform_linking.routes import confirm_link_token

        with patch(
            "backend.api.features.platform_linking.routes.confirm_server_link",
            new=AsyncMock(side_effect=NotFoundError("Token not found.")),
        ):
            with pytest.raises(HTTPException) as exc:
                await confirm_link_token(token="abc", user_id="u1")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_wrong_flow_maps_to_400(self):
        from backend.api.features.platform_linking.routes import confirm_link_token

        with patch(
            "backend.api.features.platform_linking.routes.confirm_server_link",
            new=AsyncMock(side_effect=LinkFlowMismatchError("wrong flow")),
        ):
            with pytest.raises(HTTPException) as exc:
                await confirm_link_token(token="abc", user_id="u1")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_expired_maps_to_410(self):
        from backend.api.features.platform_linking.routes import confirm_link_token

        with patch(
            "backend.api.features.platform_linking.routes.confirm_server_link",
            new=AsyncMock(side_effect=LinkTokenExpiredError("expired")),
        ):
            with pytest.raises(HTTPException) as exc:
                await confirm_link_token(token="abc", user_id="u1")
        assert exc.value.status_code == 410

    @pytest.mark.asyncio
    async def test_already_linked_maps_to_409(self):
        from backend.api.features.platform_linking.routes import confirm_link_token

        with patch(
            "backend.api.features.platform_linking.routes.confirm_server_link",
            new=AsyncMock(side_effect=LinkAlreadyExistsError("already linked")),
        ):
            with pytest.raises(HTTPException) as exc:
                await confirm_link_token(token="abc", user_id="u1")
        assert exc.value.status_code == 409


class TestConfirmUserLinkRouteTranslation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exc,expected_status",
        [
            (NotFoundError("missing"), 404),
            (LinkFlowMismatchError("wrong flow"), 400),
            (LinkTokenExpiredError("expired"), 410),
            (LinkAlreadyExistsError("already"), 409),
        ],
    )
    async def test_translation(self, exc: Exception, expected_status: int):
        from backend.api.features.platform_linking.routes import confirm_user_link_token

        with patch(
            "backend.api.features.platform_linking.routes.confirm_user_link",
            new=AsyncMock(side_effect=exc),
        ):
            with pytest.raises(HTTPException) as ctx:
                await confirm_user_link_token(token="abc", user_id="u1")
        assert ctx.value.status_code == expected_status


class TestDeleteLinkRouteTranslation:
    @pytest.mark.asyncio
    async def test_not_found_maps_to_404(self):
        from backend.api.features.platform_linking.routes import delete_link

        with patch(
            "backend.api.features.platform_linking.routes.delete_server_link",
            new=AsyncMock(side_effect=NotFoundError("missing")),
        ):
            with pytest.raises(HTTPException) as exc:
                await delete_link(link_id="x", user_id="u1")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_not_owned_maps_to_403(self):
        from backend.api.features.platform_linking.routes import delete_link

        with patch(
            "backend.api.features.platform_linking.routes.delete_server_link",
            new=AsyncMock(side_effect=NotAuthorizedError("nope")),
        ):
            with pytest.raises(HTTPException) as exc:
                await delete_link(link_id="x", user_id="u1")
        assert exc.value.status_code == 403


class TestDeleteUserLinkRouteTranslation:
    @pytest.mark.asyncio
    async def test_not_found_maps_to_404(self):
        from backend.api.features.platform_linking.routes import delete_user_link_route

        with patch(
            "backend.api.features.platform_linking.routes.delete_user_link",
            new=AsyncMock(side_effect=NotFoundError("missing")),
        ):
            with pytest.raises(HTTPException) as exc:
                await delete_user_link_route(link_id="x", user_id="u1")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_not_owned_maps_to_403(self):
        from backend.api.features.platform_linking.routes import delete_user_link_route

        with patch(
            "backend.api.features.platform_linking.routes.delete_user_link",
            new=AsyncMock(side_effect=NotAuthorizedError("nope")),
        ):
            with pytest.raises(HTTPException) as exc:
                await delete_user_link_route(link_id="x", user_id="u1")
        assert exc.value.status_code == 403


# ── Adversarial: malformed token path params ──────────────────────────


class TestAdversarialTokenPath:
    # TokenPath enforces `^[A-Za-z0-9_-]+$` + max_length=64. Validation
    # happens before the handler, so route through a TestClient.

    @pytest.fixture
    def client(self):
        import fastapi
        from autogpt_libs.auth import get_user_id, requires_user
        from fastapi.testclient import TestClient

        import backend.api.features.platform_linking.routes as routes_mod

        app = fastapi.FastAPI()
        app.dependency_overrides[requires_user] = lambda: None
        app.dependency_overrides[get_user_id] = lambda: "caller-user"
        app.include_router(routes_mod.router, prefix="/api/platform-linking")
        return TestClient(app)

    def test_rejects_token_with_special_chars(self, client):
        response = client.get("/api/platform-linking/tokens/bad%24token/info")
        assert response.status_code == 422

    def test_rejects_token_with_path_traversal(self, client):
        # Slashes, dots, URL-encoded traversal all rejected by the regex.
        for probe in ("..%2F..", "foo..bar", "foo%2Fbar"):
            response = client.get(f"/api/platform-linking/tokens/{probe}/info")
            assert response.status_code in (
                404,
                422,
            ), f"path-traversal probe {probe!r} returned {response.status_code}"

    def test_rejects_token_too_long(self, client):
        long_token = "a" * 65
        response = client.get(f"/api/platform-linking/tokens/{long_token}/info")
        assert response.status_code == 422

    def test_accepts_token_at_max_length(self, client):
        token = "a" * 64
        with patch(
            "backend.api.features.platform_linking.routes.get_link_token_info",
            new=AsyncMock(side_effect=NotFoundError("missing")),
        ):
            response = client.get(f"/api/platform-linking/tokens/{token}/info")
        # Passes path validation; NotFoundError → 404.
        assert response.status_code == 404

    def test_accepts_urlsafe_b64_token_shape(self, client):
        # secrets.token_urlsafe produces [A-Za-z0-9_-]+ — accepted.
        with patch(
            "backend.api.features.platform_linking.routes.get_link_token_info",
            new=AsyncMock(side_effect=NotFoundError("missing")),
        ):
            response = client.get("/api/platform-linking/tokens/abc-_XYZ123-_abc/info")
        assert response.status_code == 404

    def test_confirm_rejects_malformed_token(self, client):
        # Same regex guard applies to the POST confirm path.
        response = client.post("/api/platform-linking/tokens/bad%24token/confirm")
        assert response.status_code == 422


class TestAdversarialDeleteLinkId:
    """DELETE link_id has no regex — ensure weird values are handled via
    NotFoundError (no crash, no cross-user leak)."""

    @pytest.fixture
    def client(self):
        import fastapi
        from autogpt_libs.auth import get_user_id, requires_user
        from fastapi.testclient import TestClient

        import backend.api.features.platform_linking.routes as routes_mod

        app = fastapi.FastAPI()
        app.dependency_overrides[requires_user] = lambda: None
        app.dependency_overrides[get_user_id] = lambda: "caller-user"
        app.include_router(routes_mod.router, prefix="/api/platform-linking")
        return TestClient(app)

    def test_weird_link_id_returns_404(self, client):
        with patch(
            "backend.api.features.platform_linking.routes.delete_server_link",
            new=AsyncMock(side_effect=NotFoundError("missing")),
        ):
            for link_id in ("'; DROP TABLE links;--", "../../etc/passwd", ""):
                response = client.delete(f"/api/platform-linking/links/{link_id}")
                # Empty string path → 405 (no match); weird strings → 404.
                assert response.status_code in (404, 405)
