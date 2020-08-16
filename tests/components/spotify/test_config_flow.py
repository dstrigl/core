"""Tests for the Spotify config flow."""
from spotipy import SpotifyException

from homeassistant import data_entry_flow, setup
from homeassistant.components.spotify.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.helpers import config_entry_oauth2_flow

from tests.async_mock import patch
from tests.common import MockConfigEntry


async def test_abort_if_no_configuration(hass):
    """Check flow aborts when no configuration is present."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "missing_configuration"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "missing_configuration"


async def test_zeroconf_abort_if_existing_entry(hass):
    """Check zeroconf flow aborts when an entry already exist."""
    MockConfigEntry(domain=DOMAIN).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "already_configured"


async def test_full_flow(hass, aiohttp_client, aioclient_mock, current_request):
    """Check a full flow."""
    assert await setup.async_setup_component(
        hass,
        DOMAIN,
        {
            DOMAIN: {CONF_CLIENT_ID: "client", CONF_CLIENT_SECRET: "secret"},
            "http": {"base_url": "https://example.com"},
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    # pylint: disable=protected-access
    state = config_entry_oauth2_flow._encode_jwt(hass, {"flow_id": result["flow_id"]})

    assert result["type"] == data_entry_flow.RESULT_TYPE_EXTERNAL_STEP
    assert result["url"] == (
        "https://accounts.spotify.com/authorize"
        "?response_type=code&client_id=client"
        "&redirect_uri=https://example.com/auth/external/callback"
        f"&state={state}"
        "&scope=user-modify-playback-state,user-read-playback-state,user-read-private"
    )

    client = await aiohttp_client(hass.http.app)
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"

    aioclient_mock.post(
        "https://accounts.spotify.com/api/token",
        json={
            "refresh_token": "mock-refresh-token",
            "access_token": "mock-access-token",
            "type": "Bearer",
            "expires_in": 60,
        },
    )

    with patch("homeassistant.components.spotify.config_flow.Spotify") as spotify_mock:
        spotify_mock.return_value.current_user.return_value = {"id": "fake_id"}
        result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["data"]["auth_implementation"] == DOMAIN
    result["data"]["token"].pop("expires_at")
    assert result["data"]["token"] == {
        "refresh_token": "mock-refresh-token",
        "access_token": "mock-access-token",
        "type": "Bearer",
        "expires_in": 60,
    }


async def test_abort_if_spotify_error(
    hass, aiohttp_client, aioclient_mock, current_request
):
    """Check Spotify errors causes flow to abort."""
    await setup.async_setup_component(
        hass,
        DOMAIN,
        {
            DOMAIN: {CONF_CLIENT_ID: "client", CONF_CLIENT_SECRET: "secret"},
            "http": {"base_url": "https://example.com"},
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    # pylint: disable=protected-access
    state = config_entry_oauth2_flow._encode_jwt(hass, {"flow_id": result["flow_id"]})
    client = await aiohttp_client(hass.http.app)
    await client.get(f"/auth/external/callback?code=abcd&state={state}")

    aioclient_mock.post(
        "https://accounts.spotify.com/api/token",
        json={
            "refresh_token": "mock-refresh-token",
            "access_token": "mock-access-token",
            "type": "Bearer",
            "expires_in": 60,
        },
    )

    with patch(
        "homeassistant.components.spotify.config_flow.Spotify.current_user",
        side_effect=SpotifyException(400, -1, "message"),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "connection_error"
