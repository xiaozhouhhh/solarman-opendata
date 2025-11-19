import pytest
import asyncio
import aiohttp
from unittest.mock import patch, AsyncMock
from aiohttp import ClientSession, ClientResponse
from http import HTTPStatus
from solarman_opendata.solarman import (
    Solarman,
    DeviceConnectionError,
    DeviceResponseError,
    validate_response,
)

# Test constants
TEST_HOST = "test-host"
TEST_PORT = 8080
TEST_TIMEOUT = 5
TEST_DEVICE_TYPE = "SP-2W-EU"

# Mock response data
MOCK_CONFIG_RESPONSE = {"type": TEST_DEVICE_TYPE}
MOCK_DATA_RESPONSE = {"power": 100}
MOCK_STATUS_RESPONSE = {"status": "on"}

@pytest.fixture
async def mock_session():
    """Creates an aiohttp session with mocked request method"""
    session = AsyncMock(spec=ClientSession)
    mock_context_manager = AsyncMock()
    session.request.return_value = mock_context_manager
    return session

@pytest.fixture
def api_client(mock_session):
    """Initializes Solarman client for testing"""
    return Solarman(
        session=mock_session,
        host=TEST_HOST,
        port=TEST_PORT,
        timeout=TEST_TIMEOUT
    )

@pytest.mark.asyncio
async def test_initialization(api_client, mock_session):
    """Tests API client initialization parameters"""
    assert api_client.host == TEST_HOST
    assert api_client.port == TEST_PORT
    assert api_client.timeout.total == TEST_TIMEOUT
    assert api_client.base_url == f"http://{TEST_HOST}:{TEST_PORT}/rpc"
    assert api_client.device_type is None

@pytest.mark.asyncio
async def test_request_success(api_client, mock_session):
    """Tests successful API request handling"""
    # Mock successful response
    mock_resp = AsyncMock(spec=ClientResponse)
    mock_resp.status = HTTPStatus.OK
    mock_resp.json.return_value = MOCK_DATA_RESPONSE
    
    mock_context_manager = mock_session.request.return_value
    mock_context_manager.__aenter__.return_value = mock_resp

    status, data = await api_client.request("GET", "test_api")
    
    assert status == HTTPStatus.OK
    assert data == MOCK_DATA_RESPONSE
    mock_session.request.assert_called_once_with(
        method="GET",
        url=f"{api_client.base_url}/test_api",
        params=None,
        headers=api_client.headers,
        raise_for_status=True,
        timeout=api_client.timeout
    )

@pytest.mark.asyncio
async def test_request_timeout_error(api_client, mock_session):
    """Tests timeout error handling in request method"""
    mock_session.request.side_effect = asyncio.TimeoutError("Timeout")
    
    with pytest.raises(DeviceConnectionError) as exc_info:
        await api_client.request("GET", "test_api")
    
    assert f"Timeout connecting to {TEST_HOST}:{TEST_PORT}" in str(exc_info.value)

@pytest.mark.asyncio
async def test_request_client_error(api_client, mock_session):
    """Tests connection error handling in request method"""
    mock_session.request.side_effect = aiohttp.ClientError("Connection failed")
    
    with pytest.raises(DeviceConnectionError) as exc_info:
        await api_client.request("GET", "test_api")
    
    assert f"Connection error to {TEST_HOST}:{TEST_PORT}" in str(exc_info.value)

@pytest.mark.asyncio
async def test_request_unexpected_error(api_client, mock_session):
    """Tests unexpected error handling in request method"""
    mock_session.request.side_effect = Exception("Unexpected error")
    
    with pytest.raises(DeviceResponseError) as exc_info:
        await api_client.request("GET", "test_api")
    
    assert "Unexpected error: Unexpected error" in str(exc_info.value)

@pytest.mark.asyncio
async def test_fetch_data(api_client):
    """Tests data fetching with device type detection"""

    with patch.object(api_client, 'get_config', AsyncMock(return_value=MOCK_CONFIG_RESPONSE)):        
        api_client.request = AsyncMock(return_value=(HTTPStatus.OK, MOCK_DATA_RESPONSE))
        api_client.get_status = AsyncMock(return_value=MOCK_STATUS_RESPONSE)
        
        result = await api_client.fetch_data()

    expected = {**MOCK_STATUS_RESPONSE, **MOCK_DATA_RESPONSE}
    assert result == expected

@pytest.mark.asyncio
async def test_fetch_data_unsupported_device(api_client):
    """Tests data fetching for unsupported device type"""
    api_client.device_type = None
    
    with patch.object(api_client, 'get_config', AsyncMock(return_value={"type": "UNSUPPORTED"})):
        result = await api_client.fetch_data()
    
    assert result == {}

@pytest.mark.asyncio
async def test_fetch_data_no_device_type_in_config(api_client):
    """Tests data fetching when config doesn't contain device type"""
    api_client.device_type = None

    with patch.object(api_client, 'get_config', AsyncMock(return_value={"some_other_field": "value"})):
        result = await api_client.fetch_data()
    
    assert result == {}

@pytest.mark.asyncio
async def test_set_status_unsupported_device(api_client):
    """Tests set_status for unsupported device type"""
    api_client.device_type = "UNSUPPORTED_DEVICE"
    
    with patch.object(api_client, 'request') as mock_request:
        await api_client.set_status(True)
        mock_request.assert_not_called()

@pytest.mark.asyncio
async def test_get_status_supported_device(api_client):
    """Tests status retrieval for supported device type"""
    with patch.object(api_client, 'request', AsyncMock(return_value=(HTTPStatus.OK, MOCK_STATUS_RESPONSE))):
        api_client.device_type = TEST_DEVICE_TYPE
        status = await api_client.get_status()
        assert status == MOCK_STATUS_RESPONSE

@pytest.mark.asyncio
async def test_get_status_unsupported_device(api_client):
    """Tests status retrieval for unsupported device type"""
    api_client.device_type = "UNSUPPORTED_DEVICE"
    status = await api_client.get_status()
    assert status == {}

@pytest.mark.asyncio
async def test_set_status_success(api_client):
    """Tests successful plug control (on/off)"""
    api_client.device_type = TEST_DEVICE_TYPE
    
    with patch.object(api_client, 'request', AsyncMock(return_value=(HTTPStatus.OK, {"result": True}))):
        # Test turn on
        await api_client.set_status(True)
        api_client.request.assert_called_with(
            "POST",
            "Plug.SetStatus",
            {"config": '{"switch_status":"on"}'}  # Note: No spaces in JSON
        )
        
        # Test turn off
        await api_client.set_status(False)
        api_client.request.assert_called_with(
            "POST",
            "Plug.SetStatus",
            {"config": '{"switch_status":"off"}'}
        )

@pytest.mark.asyncio
async def test_set_status_failure(api_client, caplog):
    """Tests failed plug control operation"""
    with patch.object(api_client, 'request', AsyncMock(return_value=(HTTPStatus.OK, {"result": False}))):
        api_client.device_type = TEST_DEVICE_TYPE
        await api_client.set_status(True)
        assert "Failed to set switch state" in caplog.text


@pytest.mark.asyncio
async def test_get_config_success(api_client):
    """Tests successful device configuration retrieval"""
    with patch.object(api_client, 'request', AsyncMock(return_value=(HTTPStatus.OK, MOCK_CONFIG_RESPONSE))):
        data = await api_client.get_config()
        assert data == MOCK_CONFIG_RESPONSE
        api_client.request.assert_called_once_with("GET", "Sys.GetConfig")


def test_validate_response_success():
    """Tests successful response validation (200 status)"""
    # Should not raise exception
    assert validate_response(HTTPStatus.OK) is True

def test_validate_response_failure():
    """Tests failure response validation (non-200 status)"""
    with pytest.raises(DeviceResponseError) as exc_info:
        validate_response(HTTPStatus.NOT_FOUND)
    
    assert "Unexpected status: 404." in str(exc_info.value)