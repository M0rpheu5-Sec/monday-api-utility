# monday-api-utility

A lightweight Python client for common [monday.com GraphQL API](https://developer.monday.com/api-reference/) operations, including workspaces, boards, item filtering, cursor-based pagination, and CRUD automation.

The project is designed as a reusable utility module that can be imported into other Python automation scripts. It provides helper methods for common operations while still exposing `execute()` for custom GraphQL queries and mutations.

> This is an independent project and is not an official monday.com SDK.

## Features

- List accessible workspaces
- List boards in a workspace
- Retrieve board column metadata
- Retrieve items and column values
- Filter items by one or multiple column values
- Continue item queries with cursor-based pagination
- Retrieve a specific item
- Create, update, and delete items
- Change simple column values and status labels
- Execute custom GraphQL operations
- Reuse HTTP sessions
- Configure request timeouts
- Detect HTTP and GraphQL errors
- Use the client as a context manager

## Requirements

- Python 3.10 or newer
- `requests`
- `python-dotenv` *(optional, only if you use a local `.env` file)*

Install the required dependency:

```bash
python -m pip install requests
```

For optional `.env` support:

```bash
python -m pip install python-dotenv
```

## Installation

Clone the repository:

```bash
git clone https://github.com/M0rpheu5-Sec/monday-api-utility.git
cd monday-api-utility
```

You can then import `MondayClient` from `monday_client.py`.

## Authentication

The monday.com API requires an API token in the `Authorization` header.

Never hardcode the token in source code or commit it to GitHub.

For production environments, use a dedicated secret manager such as:

- AWS Secrets Manager
- Azure Key Vault

For local development, store the token in an environment variable or in a `.env` file that is excluded from Git.

### Option 1: Environment Variable

#### Windows PowerShell

```powershell
$env:MONDAY_API_TOKEN = "your-api-token"
```

#### macOS or Linux

```bash
export MONDAY_API_TOKEN="your-api-token"
```

Read the token in Python:

```python
import os

api_token = os.environ["MONDAY_API_TOKEN"]
```

### Option 2: Local `.env` File

Create a file named `.env`:

```dotenv
MONDAY_API_TOKEN=your-api-token
```

Add it to `.gitignore`:

```gitignore
.env
.env.*
```

Install `python-dotenv`:

```bash
python -m pip install python-dotenv
```

Load the token in Python:

```python
import os

from dotenv import load_dotenv

load_dotenv()

api_token = os.environ["MONDAY_API_TOKEN"]
```

Never commit the `.env` file. Commit a safe `.env.example` file instead:

```dotenv
MONDAY_API_TOKEN=
```
## Quick Start

```python
import os

from monday_client import MondayClient

api_token = os.environ["MONDAY_API_TOKEN"]

with MondayClient(api_token) as client:
    response = client.list_workspaces()

    for workspace in response["data"]["workspaces"]:
        print(workspace["id"], workspace["name"])
```

The client returns the complete JSON response from monday.com. Successful query data is normally available under the `data` key.

## Client Configuration

```python
client = MondayClient(
    api_key="your-api-token",
    api_version="2026-04",
    timeout=30.0,
)
```

| Argument | Type | Default | Description |
|---|---|---|---|
| `api_key` | `str` | Required | monday.com personal or OAuth API token |
| `api_version` | `str` | `2026-04` | Value sent in the `API-Version` header |
| `timeout` | `float` | `30.0` | HTTP request timeout in seconds |
| `session` | `requests.Session` | `None` | Optional preconfigured HTTP session |

The API endpoint used by the client is:

```text
https://api.monday.com/v2
```

## Usage Examples

Replace the example IDs and column IDs with values from your own monday.com account.

### List Workspaces

```python
response = client.list_workspaces()

for workspace in response["data"]["workspaces"]:
    print(
        workspace["id"],
        workspace["name"],
        workspace["kind"],
    )
```

### List Boards in a Workspace

```python
workspace_id = 123456

response = client.list_boards(
    workspace_id=workspace_id,
    limit=100,
)

for board in response["data"]["boards"]:
    print(board["id"], board["name"], board["state"])
```

### List Board Columns

Column IDs are required for most filtering and update operations.

```python
board_id = 123456789

response = client.list_columns(board_id)
columns = response["data"]["boards"][0]["columns"]

for column in columns:
    print(
        f'ID: {column["id"]} | '
        f'Title: {column["title"]} | '
        f'Type: {column["type"]}'
    )
```

### Retrieve Items from a Board

```python
response = client.list_items_from_board(
    board_id=board_id,
    limit=100,
)

page = response["data"]["boards"][0]["items_page"]

for item in page["items"]:
    print(item["id"], item["name"])

cursor = page["cursor"]
```

Each item includes its ID, name, creation time, and column values.

### Continue with the Next Page

Use the cursor returned by `list_items_from_board()` or a filtered item query.

```python
if cursor:
    response = client.get_next_page(
        cursor=cursor,
        limit=100,
        include_column_values=True,
    )

    next_page = response["data"]["next_items_page"]

    for item in next_page["items"]:
        print(item["id"], item["name"])

    cursor = next_page["cursor"]
```

To retrieve all pages:

```python
response = client.list_items_from_board(
    board_id=board_id,
    limit=500,
)

page = response["data"]["boards"][0]["items_page"]
all_items = list(page["items"])
cursor = page["cursor"]

while cursor:
    response = client.get_next_page(
        cursor=cursor,
        limit=500,
        include_column_values=True,
    )

    page = response["data"]["next_items_page"]
    all_items.extend(page["items"])
    cursor = page["cursor"]

print(f"Retrieved {len(all_items)} items")
```

### Filter Items by One Column

```python
response = client.get_items_by_column_values(
    board_id=board_id,
    column_id="status",
    value="Done",
    limit=500,
)

page = response["data"]["items_page_by_column_values"]

for item in page["items"]:
    print(item["id"], item["name"])
```

You can also match multiple values in the same column:

```python
response = client.get_items_by_column_values(
    board_id=board_id,
    column_id="priority",
    value=["High", "Critical"],
)
```

### Filter Items by Multiple Columns

```python
response = client.get_items_by_multiple_column_values(
    board_id=board_id,
    filters={
        "status": ["Working on it", "Stuck"],
        "priority": ["High", "Critical"],
    },
    limit=500,
)

page = response["data"]["items_page_by_column_values"]

for item in page["items"]:
    print(item["id"], item["name"])
```

The filter keys must be actual column IDs from your board.

### Retrieve One Item

```python
item_id = 987654321

response = client.get_item(item_id)
items = response["data"]["items"]

if items:
    item = items[0]
    print(item["id"], item["name"])
```

### Create an Item

Create an item without initial column values:

```python
response = client.create_item(
    board_id=board_id,
    item_name="Review security finding",
)

created_item = response["data"]["create_item"]
print(created_item["id"], created_item["name"])
```

Create an item with initial column values:

```python
response = client.create_item(
    board_id=board_id,
    item_name="Review critical security finding",
    column_values={
        "status": {"label": "Working on it"},
        "priority": {"label": "Critical"},
        "text": "Created through the monday.com API",
    },
)
```

Column value formats vary by column type.

### Update Multiple Column Values

```python
response = client.update_item(
    board_id=board_id,
    item_id=item_id,
    column_values={
        "status": {"label": "Done"},
        "text": "Investigation completed",
    },
)

updated_item_id = response["data"]["change_multiple_column_values"]["id"]
print(updated_item_id)
```

### Change a Simple Column Value

```python
response = client.change_simple_column_value(
    board_id=board_id,
    item_id=item_id,
    column_id="text",
    value="Updated by Python automation",
)
```

### Change a Status Label

The default status column ID is `status`.

```python
response = client.change_label_status(
    board_id=board_id,
    item_id=item_id,
    status_value="Done",
)
```

For a status column with a different ID:

```python
response = client.change_label_status(
    board_id=board_id,
    item_id=item_id,
    status_value="Done",
    column_id="project_status",
)
```

### Delete an Item

```python
response = client.delete_item(item_id)

deleted_item_id = response["data"]["delete_item"]["id"]
print(f"Deleted item: {deleted_item_id}")
```

Deletion is destructive. Verify the item ID before running this operation.

### Execute a Custom GraphQL Query

Use `execute()` for API operations that do not have a dedicated helper method.

```python
query = """
query CurrentUser {
    me {
        id
        name
    }
}
"""

response = client.execute(query)
print(response["data"]["me"])
```

You can also pass GraphQL variables:

```python
query = """
query GetBoards($boardIds: [ID!]!) {
    boards(ids: $boardIds) {
        id
        name
    }
}
"""

variables = {
    "boardIds": ["123456789", "987654321"],
}

response = client.execute(query, variables)
```

## Error Handling

The client raises `MondayAPIError` when:

- The HTTP request fails
- monday.com returns a non-JSON response
- monday.com returns an unsuccessful HTTP status
- The GraphQL response contains an `errors` array

```python
import os

from monday_client import MondayAPIError, MondayClient

try:
    with MondayClient(os.environ["MONDAY_API_TOKEN"]) as client:
        response = client.get_item(123456789)

except MondayAPIError as exc:
    print(f"Request failed: {exc}")
    print(f"HTTP status: {exc.status_code}")
    print(f"Request ID: {exc.request_id}")
    print(f"GraphQL errors: {exc.errors}")
```

The exception exposes these attributes:

| Attribute | Description |
|---|---|
| `status_code` | HTTP response status, when available |
| `errors` | GraphQL errors returned by monday.com |
| `request_id` | monday.com request ID, when included |
| `response_body` | Parsed response body or raw response text |

## Method Reference

| Method | Purpose |
|---|---|
| `execute(query, variables=None)` | Execute a custom GraphQL operation |
| `list_workspaces()` | List visible workspaces |
| `list_boards(workspace_id, limit=100)` | List boards in a workspace |
| `list_columns(board_id)` | List board columns |
| `list_items_from_board(board_id, limit=100)` | Retrieve the first page of board items |
| `get_items_by_column_values(...)` | Filter items by one column |
| `get_items_by_multiple_column_values(...)` | Filter items by multiple columns |
| `get_next_page(...)` | Continue an item query using a cursor |
| `get_item(item_id)` | Retrieve one item |
| `change_simple_column_value(...)` | Change a simple column value |
| `change_label_status(...)` | Change a status label |
| `create_item(...)` | Create an item |
| `update_item(...)` | Update multiple item columns |
| `delete_item(item_id)` | Delete an item |
| `close()` | Close the internally created HTTP session |

## Return Values

The utility returns the complete monday.com JSON response rather than converting responses into custom model objects.

A typical response looks like:

```json
{
  "data": {
    "boards": [
      {
        "id": "123456789",
        "name": "Security Operations"
      }
    ]
  }
}
```

This keeps the wrapper flexible and makes it easier to inspect or use any fields returned by the API.

## Security Recommendations

- Never commit API tokens to GitHub.
- Use a dedicated secret manager in production.
- Use environment variables or an ignored `.env` file for local development.
- Do not print tokens in logs.
- Rotate a token immediately if it is exposed.
- Remember that a personal API token inherits the permissions of its owner.
- Review IDs carefully before updating or deleting data.
- Avoid storing sensitive board data in debug output.

Suggested `.gitignore` entries:

```gitignore
.env
.env.*
venv/
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.idea/
.vscode/
```

## Limitations

This project is intentionally lightweight. It does not currently include:

- Complete monday.com API coverage
- Automatic retries or exponential backoff
- Asynchronous requests
- Typed response models
- A command-line interface
- Built-in caching
- Automated tests
- PyPI packaging

For operations not covered by a helper method, use `execute()` with a custom GraphQL query or mutation.

## Repository Structure

```text
monday-api-utility/
├── monday_client.py
└── README.md
```

## Project Background

This utility was created to avoid rewriting the same monday.com GraphQL request logic across multiple Python automation scripts.

The GraphQL operations are based on monday.com's public API documentation. The reusable client structure, validation, session management, error handling, filtering helpers, and automation-focused interface were organized into one module to make future integrations easier to maintain.


## Useful Links

- [monday.com API documentation](https://developer.monday.com/api-reference/)
- [Authentication](https://developer.monday.com/api-reference/docs/authentication)
- [API versioning](https://developer.monday.com/api-reference/docs/api-versioning)
- [GraphQL introduction](https://developer.monday.com/api-reference/docs/introduction-to-graphql)
- [Querying board items](https://developer.monday.com/api-reference/docs/querying-board-items)
- [Changing column values](https://developer.monday.com/api-reference/docs/change-column-values)
- [Error handling](https://developer.monday.com/api-reference/docs/error-handling)
- [Rate limits](https://developer.monday.com/api-reference/docs/rate-limits)
