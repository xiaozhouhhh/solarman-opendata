# Solarman

Python client for interacting with Solarman devices over local network.

## Installation

```bash
pip install solarman-opendata
```

## Usage

### Basic Example

```python
import asyncio
import aiohttp

from solarman_opendata.solarman import Solarman

async def main():
    host = "190.160.3.43"
    port = 8080

    async with aiohttp.ClientSession() as session:
        client = Solarman(
            session=session,
            host=host,
            port=port
        )

        data = await client.fetch_data()
        print(data)

if __name__ == "__main__":
    asyncio.run(main())
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.