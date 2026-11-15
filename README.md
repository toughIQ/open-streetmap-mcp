# OpenStreetMap (OSM) MCP Server

An OpenStreetMap MCP server implementation that enhances LLM capabilities with location-based services and geospatial data.

## Demo

### Meeting Point Optimization
![Meeting Point Use Case](demo/use-case-meeting.gif)

### Neighborhood Analysis
![Neighborhood Analysis Use Case](demo/use-case-neighborhood.gif)

### Parking Search
![Parking Search Use Case](demo/use-case-parking.gif)


## Installation

### In MCP Hosts like Claude Desktop, Cursor, Windsurf, etc.
- `osm-mcp-server`: The main server, available for public use.
  
  ```json
  "mcpServers": {
    "osm-mcp-server": {
      "command": "uvx",
      "args": [
        "osm-mcp-server"
      ]
    }
  }
  ```

## Features

This server provides LLMs with tools to interact with OpenStreetMap data, enabling location-based applications to:

- Geocode addresses and place names to coordinates
- Reverse geocode coordinates to addresses
- Find nearby points of interest
- Get route directions between locations
- Search for places by category within a bounding box
- Suggest optimal meeting points for multiple people
- Explore areas and get comprehensive location information
- Find schools and educational institutions near a location
- Analyze commute options between home and work
- Locate EV charging stations with connector and power filtering
- Perform neighborhood livability analysis for real estate
- Find parking facilities with availability and fee information

## Components

### Resources

The server implements location-based resources:
- `location://place/{query}`: Get information about places by name or address
- `location://map/{style}/{z}/{x}/{y}`: Get styled map tiles at specified coordinates

### Tools

The server implements several geospatial tools:
- `geocode_address`: Convert text to geographic coordinates
- `reverse_geocode`: Convert coordinates to human-readable addresses
- `find_nearby_places`: Discover points of interest near a location
- `get_route_directions`: Get turn-by-turn directions between locations
- `search_category`: Find places of specific categories in an area
- `suggest_meeting_point`: Find optimal meeting spots for multiple people
- `explore_area`: Get comprehensive data about a neighborhood
- `find_schools_nearby`: Locate educational institutions near a specific location
- `find_place`: Find a place by name or address and check its address (street, house number, postcode, town), limited to an optional area with a fuzzy name fallback
- `create_route_printout`: One call for a printable A4 PDF route sheet: colored map with numbered turn points, checked addresses of start and destination, step-by-step directions (en or de), and automatic zoomed detail maps (one per cluster, up to 3) where turn points overlap
- `render_static_map`: Render a map image (PNG/JPEG) from OSM tiles with markers and a route line, saved to a file for PDFs and docs
- `render_route_map`: Compute a route (car, bike, foot) and save a map image of it
- `analyze_commute`: Compare transportation options between home and work
- `find_ev_charging_stations`: Locate EV charging infrastructure with filtering
- `analyze_neighborhood`: Evaluate neighborhood livability for real estate
- `find_parking_facilities`: Locate parking options near a destination


## Fork changes (toughIQ)

- New tools `render_static_map` and `render_route_map` (Pillow, no extra services). Tiles are cached in `~/.cache/osm-mcp-server/tiles` and fetched with at most 2 connections, as the OSM tile usage policy asks.
- Routing now uses `routing.openstreetmap.de` (separate car, bike and foot profiles) and turn-by-turn steps get readable text.
- A real User-Agent is sent. Override with `OSM_MCP_USER_AGENT`. Other env vars: `OSM_MCP_TILE_URL`, `OSM_MCP_CACHE_DIR`.
- Place search for routing is area-aware: `area="Koenigstetten, Austria"` limits results to that place (checked against the address, not just the bounding box, so a scout group in the next village is not picked) and falls back to a fuzzy name search inside the administrative boundary. If nothing is found inside the area it fails instead of guessing elsewhere. Nominatim calls are throttled to 1 per second.
- All Overpass tools (nearby places, category search, schools, EV charging, parking, neighborhood, place fallback) go through one shared client: User-Agent sent (overpass-api.de answers 406 without one), one request at a time, mirrors tried in order (overpass.openstreetmap.fr first, it was by far the fastest in tests), a 75 s total budget, ways and relations now return a center point (`out center tags`), and OSM keys from tool arguments are validated before they go into a query. Fixed: `search_category` with subcategories built invalid syntax, `find_schools_nearby` had broken bbox placeholders.
- Cancelled requests get no reply (spec), because opencode drops the whole server on the late "Request cancelled" error of the python SDK.
- MCP SDK upgraded from 1.3.0 to 1.30.0: with 1.3.0 any `notifications/cancelled` from the client (abort, timeout) killed the whole server process.
- Dependencies are pinned to exact versions. `constraints.txt` (exported from `uv.lock`) freezes the transitive ones too, because `uv tool install` ignores `uv.lock`. Install
  `uv tool install -c constraints.txt .` (run inside a checkout, non-editable), then use `osm-mcp-server` as the MCP command.
- Keep the "(c) OpenStreetMap contributors" attribution on published maps. It is drawn on the images by default.

## Local Testing

### Running the Server

To run the server locally:

1. Install the package in development mode:

```bash
pip install -e .
```

2. Start the server:

```bash
osm-mcp-server
```

3. The server will start and listen for MCP requests on the standard input/output.

### Testing with Example Clients

The repository includes two example clients in the `examples/` directory:

#### Basic Client Example

`client.py` demonstrates basic usage of the OSM MCP server:

```bash
python examples/client.py
```

This will:
- Connect to the locally running server
- Get information about San Francisco
- Search for restaurants in the area
- Retrieve comprehensive map data with progress tracking

#### LLM Integration Example

`llm_client.py` provides a helper class designed for LLM integration:

```bash
python examples/llm_client.py
```

This example shows how an LLM can use the Location Assistant to:
- Get location information from text queries
- Find nearby points of interest
- Get directions between locations
- Find optimal meeting points
- Explore neighborhoods

### Writing Your Own Client

To create your own client:

1. Import the MCP client:
```python
from mcp.client import Client
```

2. Initialize the client with your server URL:
```python
client = Client("http://localhost:8000")
```

3. Invoke tools or access resources:
```python
# Example: Geocode an address
results = await client.invoke_tool("geocode_address", {"address": "New York City"})
```

#### Claude Desktop config for local server

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

<details>
  <summary>Development/Unpublished Servers Configuration</summary>
  
  ```json
  "mcpServers": {
    "osm-mcp-server": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/osm-mcp-server",
        "run",
        "osm-mcp-server"
      ]
    }
  }
  ```
</details>



## Development

### Building and Publishing

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

2. Build package distributions:
```bash
uv build
```

This will create source and wheel distributions in the `dist/` directory.

3. Publish to PyPI:
```bash
uv publish
```

Note: You'll need to set PyPI credentials via environment variables or command flags.

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv --directory /path/to/osm-mcp-server run osm-mcp-server
```

Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.




