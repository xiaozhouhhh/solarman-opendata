"""Solarman OpenData base class."""

import json
import logging
from typing import Optional
from http import HTTPStatus

from aiohttp import ClientSession, ClientTimeout, ClientError

from .const import DEFAULT_TIMEOUT
from .errors import DeviceConnectionError, DeviceResponseError

_LOGGER = logging.getLogger(__name__)

class Solarman:
    """Class for Solarman OpenData API."""
    
    def __init__(
        self,
        session: ClientSession,
        host: str,
        port: int,
        headers: Optional[dict] = None,
        timeout: int = DEFAULT_TIMEOUT
    ) -> None:
        """
        Initialize Solarman API client.
        
        :param session: aiohttp client session.
        :param host: Device hostname or IP address.
        :param port: Device port (default: 8080).
        :param headers: Default request headers.
        :param timeout: Request timeout in seconds.
        """
        self.session = session
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}/rpc"
        self.headers = headers
        self.timeout = ClientTimeout(total=timeout)
        self.device_type = None

        self.headers = {"name": "opend", "pass": "opend"}
    
    async def request(
        self,
        method: str,
        api: str,
        params: Optional[dict] = None,
        timeout: Optional[ClientTimeout] = None
    ) -> tuple[HTTPStatus, dict]:
        """Execute HTTP request to Solarman device API.
        
        :param method: HTTP method (GET, POST, etc.).
        :param api: API endpoint path.
        :param params: Query parameters or form data.
        :param timeout: Custom timeout for this request.
        :return: Tuple of HTTP status code and response data.
        """
        url = f"{self.base_url}/{api}"
        _LOGGER.debug("Sending %s request to %s",method, url)

        try:
            async with self.session.request(
                method=method,
                url=url,
                params=params,
                headers=self.headers,
                raise_for_status=True,
                timeout=timeout or self.timeout,
            ) as resp:
                data = await resp.json()
                _LOGGER.debug(
                    "Received response: Status %d. Response data: %s",
                    resp.status,
                    json.dumps(data, indent=2)
                )
                return (HTTPStatus(resp.status), data)
                
        except TimeoutError as err:
            raise DeviceConnectionError(
                f"Timeout connecting to {self.host}:{self.port}"
            ) from err
        except ClientError as err:
            raise DeviceConnectionError(
                f"Connection error to {self.host}:{self.port} {err}"
            ) from err
        except Exception as err:
            raise DeviceResponseError(f"Unexpected error: {err}") from err

    async def fetch_data(self) -> dict:
        """Get real-time device data."""

        api_map = {
            "SP-2W-EU": "Plug.GetData",
            "P1-2W": "P1.JsonData",
            "gl meter": "Meter.JsonData",
        }

        if self.device_type is None:
            # Obtain device model.
            config_data = await self.get_config()
            self.device_type = config_data.get("device", config_data).get("type")

            if self.device_type is None:
                return {}
                    
        # Fetch data.
        api = api_map.get(self.device_type)
        if api is  None:
            return {}
        
        status, data = await self.request("GET", api)
        validate_response(status)
        
        # Obtain device status.
        status_data = await self.get_status()
        data.update(status_data)

        return data
    
    async def get_config(self) -> dict:
        """Get device configuration."""
        status, data = await self.request("GET", "Sys.GetConfig")
        validate_response(status)
        return data
        

    async def get_status(self) -> dict:
        """Get plug status."""
        if self.device_type != "SP-2W-EU":
            return {}
        
        status, data = await self.request("GET", "Plug.GetStatus")
        validate_response(status)
        return data
    
    async def set_status(self, active: bool):
        """
        Set the switch state of a smart plug.
        
        :param active: True to turn on, False to turn off
        :return: True if successful
        """
        if self.device_type != "SP-2W-EU":
            return
        
        switch_status = "on" if active else "off"
        config_param = json.dumps({"switch_status":switch_status}).replace(" ", "")
        payload = {"config": config_param}

        status, response = await self.request("POST", "Plug.SetStatus", payload)
        validate_response(status)
        
        if not response["result"]:
            _LOGGER.error("Failed to set switch state: Status %d, Response: %s", status, response)

    
def validate_response(status: HTTPStatus) -> bool:
    """Validate API response status and content."""
    if status != HTTPStatus.OK:
        raise DeviceResponseError(f"Unexpected status: {status}.")
    
    return True