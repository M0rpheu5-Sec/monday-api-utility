"""Lightweight Python client for the monday.com GraphQL API.

This module provides reusable helpers for common monday.com operations while
still exposing ``execute`` for custom GraphQL queries and mutations.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from requests import Response, Session
from requests.exceptions import RequestException

JsonDict = dict[str, Any]

_NEXT_ITEMS_PAGE_QUERY = """
query NextItemsPage($cursor: String!, $limit: Int!) {
    next_items_page(cursor: $cursor, limit: $limit) {
        cursor
        items {
            id
            name
        }
    }
}
"""

_NEXT_ITEMS_PAGE_WITH_VALUES_QUERY = """
query NextItemsPage($cursor: String!, $limit: Int!) {
    next_items_page(cursor: $cursor, limit: $limit) {
        cursor
        items {
            id
            name
            column_values {
                id
                column {
                    title
                }
                text
                value
            }
        }
    }
}
"""


class MondayAPIError(RuntimeError):
    """Raised when a monday.com HTTP request or GraphQL operation fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        errors: Sequence[Mapping[str, Any]] | None = None,
        request_id: str | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.errors = list(errors or [])
        self.request_id = request_id
        self.response_body = response_body


class MondayClient:
    """Small, reusable wrapper around the monday.com GraphQL API."""

    URL = "https://api.monday.com/v2"
    DEFAULT_API_VERSION = "2026-04"
    MAX_ITEM_PAGE_SIZE = 500
    MAX_BOARD_PAGE_SIZE = 100

    def __init__(
        self,
        api_key: str,
        *,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = 30.0,
        session: Session | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            api_key: A monday.com personal or OAuth API token.
            api_version: monday.com API version in ``YYYY-MM`` format.
            timeout: Request timeout in seconds.
            session: Optional preconfigured ``requests.Session``.
        """
        if not api_key or not api_key.strip():
            raise ValueError("api_key must not be empty")
        if not api_version or not api_version.strip():
            raise ValueError("api_version must not be empty")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self.timeout = timeout
        self.headers = {
            "Authorization": api_key.strip(),
            "Content-Type": "application/json",
            "API-Version": api_version.strip(),
        }
        self._session = session or Session()
        self._owns_session = session is None

    def __enter__(self) -> "MondayClient":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP session when it was created by this client."""
        if self._owns_session:
            self._session.close()

    @staticmethod
    def _validate_limit(limit: int, maximum: int) -> int:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError("limit must be an integer")
        if not 1 <= limit <= maximum:
            raise ValueError(f"limit must be between 1 and {maximum}")
        return limit

    @staticmethod
    def _request_id(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None

        extensions = payload.get("extensions")
        if not isinstance(extensions, dict):
            return None

        request_id = extensions.get("request_id")
        return str(request_id) if request_id is not None else None

    def execute(
        self,
        query: str,
        variables: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        """Execute a GraphQL query or mutation and return the full response."""
        if not query or not query.strip():
            raise ValueError("query must not be empty")

        payload: JsonDict = {"query": query}
        if variables is not None:
            payload["variables"] = dict(variables)

        try:
            response = self._session.post(
                self.URL,
                headers=self.headers,
                json=payload,
                timeout=self.timeout,
            )
        except RequestException as exc:
            raise MondayAPIError(f"monday.com request failed: {exc}") from exc

        return self._parse_response(response)

    def _parse_response(self, response: Response) -> JsonDict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise MondayAPIError(
                "monday.com returned a non-JSON response",
                status_code=response.status_code,
                response_body=response.text,
            ) from exc

        if not isinstance(payload, dict):
            raise MondayAPIError(
                "monday.com returned an unexpected response format",
                status_code=response.status_code,
                response_body=payload,
            )

        errors = payload.get("errors")
        request_id = self._request_id(payload)

        if not response.ok:
            message = f"monday.com returned HTTP {response.status_code}"
            if isinstance(errors, list):
                messages = [
                    str(error.get("message", "Unknown GraphQL error"))
                    for error in errors
                    if isinstance(error, dict)
                ]
                if messages:
                    message = "; ".join(messages)

            raise MondayAPIError(
                message,
                status_code=response.status_code,
                errors=errors if isinstance(errors, list) else None,
                request_id=request_id,
                response_body=payload,
            )

        # monday.com can return application-level GraphQL errors with HTTP 200.
        if isinstance(errors, list) and errors:
            messages = [
                str(error.get("message", "Unknown GraphQL error"))
                for error in errors
                if isinstance(error, dict)
            ]
            raise MondayAPIError(
                "; ".join(messages) or "monday.com returned a GraphQL error",
                status_code=response.status_code,
                errors=errors,
                request_id=request_id,
                response_body=payload,
            )

        return payload

    def list_workspaces(self) -> JsonDict:
        """Return workspaces visible to the authenticated user."""
        query = """
        query ListWorkspaces {
            workspaces {
                id
                name
                kind
                description
            }
        }
        """
        return self.execute(query)

    def list_boards(self, workspace_id: str | int, limit: int = 100) -> JsonDict:
        """Return boards in a workspace."""
        limit = self._validate_limit(limit, self.MAX_BOARD_PAGE_SIZE)
        query = """
        query ListBoards($workspaceIds: [ID!], $limit: Int!) {
            boards(workspace_ids: $workspaceIds, limit: $limit) {
                id
                name
                state
                permissions
                columns {
                    id
                    title
                    type
                }
            }
        }
        """
        variables = {
            "workspaceIds": [str(workspace_id)],
            "limit": limit,
        }
        return self.execute(query, variables)

    def list_columns(self, board_id: str | int) -> JsonDict:
        """Return column IDs, titles, and types for a board."""
        query = """
        query ListColumns($boardIds: [ID!]!) {
            boards(ids: $boardIds) {
                columns {
                    id
                    title
                    type
                }
            }
        }
        """
        return self.execute(query, {"boardIds": [str(board_id)]})

    def list_items_from_board(
        self,
        board_id: str | int,
        limit: int = 100,
    ) -> JsonDict:
        """Return the first page of board items and their column values."""
        limit = self._validate_limit(limit, self.MAX_ITEM_PAGE_SIZE)
        query = """
        query ListBoardItems($boardIds: [ID!]!, $limit: Int!) {
            boards(ids: $boardIds) {
                items_page(limit: $limit) {
                    cursor
                    items {
                        id
                        name
                        created_at
                        column_values {
                            id
                            column {
                                title
                            }
                            text
                            value
                        }
                    }
                }
            }
        }
        """
        variables = {
            "boardIds": [str(board_id)],
            "limit": limit,
        }
        return self.execute(query, variables)

    def get_items_by_column_values(
        self,
        board_id: str | int,
        column_id: str,
        value: str | Sequence[str],
        limit: int = 500,
    ) -> JsonDict:
        """Filter items by one column and one or more simple values."""
        return self.get_items_by_multiple_column_values(
            board_id=board_id,
            filters={column_id: value},
            limit=limit,
        )

    def get_items_by_multiple_column_values(
        self,
        board_id: str | int,
        filters: Mapping[str, str | Sequence[str]],
        limit: int = 500,
    ) -> JsonDict:
        """Filter items using multiple ``items_page_by_column_values`` rules.

        ``filters`` maps each column ID to one or more simple string values.
        Example: ``{"status": ["Done"], "priority": ["High", "Critical"]}``.
        """
        limit = self._validate_limit(limit, self.MAX_ITEM_PAGE_SIZE)
        if not filters:
            raise ValueError("filters must contain at least one column")

        columns: list[JsonDict] = []
        for column_id, raw_values in filters.items():
            normalized_column_id = str(column_id).strip()
            if not normalized_column_id:
                raise ValueError("column IDs must not be empty")

            if isinstance(raw_values, str):
                normalized_values = [raw_values]
            else:
                normalized_values = [str(item) for item in raw_values]

            if not normalized_values:
                raise ValueError(
                    f"filter for column {normalized_column_id!r} has no values"
                )

            columns.append(
                {
                    "column_id": normalized_column_id,
                    "column_values": normalized_values,
                }
            )

        query = """
        query ItemsByColumnValues(
            $boardId: ID!
            $limit: Int!
            $columns: [ItemsPageByColumnValuesQuery!]!
        ) {
            items_page_by_column_values(
                board_id: $boardId
                limit: $limit
                columns: $columns
            ) {
                cursor
                items {
                    id
                    name
                    created_at
                    column_values {
                        id
                        column {
                            title
                        }
                        text
                        value
                    }
                }
            }
        }
        """
        variables = {
            "boardId": str(board_id),
            "limit": limit,
            "columns": columns,
        }
        return self.execute(query, variables)

    def get_next_page(
        self,
        cursor: str,
        limit: int = 100,
        *,
        include_column_values: bool = False,
    ) -> JsonDict:
        """Return the next item page using a cursor from an earlier query."""
        if not cursor or not cursor.strip():
            raise ValueError("cursor must not be empty")

        limit = self._validate_limit(limit, self.MAX_ITEM_PAGE_SIZE)
        query = (
            _NEXT_ITEMS_PAGE_WITH_VALUES_QUERY
            if include_column_values
            else _NEXT_ITEMS_PAGE_QUERY
        )
        return self.execute(query, {"cursor": cursor.strip(), "limit": limit})

    def get_item(self, item_id: str | int) -> JsonDict:
        """Return one item with its group and column values."""
        query = """
        query GetItem($itemIds: [ID!]!) {
            items(ids: $itemIds) {
                id
                name
                created_at
                group {
                    id
                    title
                }
                column_values {
                    id
                    text
                    value
                    type
                    ... on MirrorValue {
                        display_value
                    }
                    ... on BoardRelationValue {
                        linked_items {
                            id
                            name
                        }
                    }
                }
            }
        }
        """
        return self.execute(query, {"itemIds": [str(item_id)]})

    def change_simple_column_value(
        self,
        board_id: str | int,
        item_id: str | int,
        column_id: str,
        value: str,
    ) -> JsonDict:
        """Change a column that accepts a simple string value."""
        if not column_id or not column_id.strip():
            raise ValueError("column_id must not be empty")

        query = """
        mutation ChangeSimpleColumnValue(
            $boardId: ID!
            $itemId: ID!
            $columnId: String!
            $value: String!
        ) {
            change_simple_column_value(
                board_id: $boardId
                item_id: $itemId
                column_id: $columnId
                value: $value
            ) {
                id
            }
        }
        """
        variables = {
            "boardId": str(board_id),
            "itemId": str(item_id),
            "columnId": column_id.strip(),
            "value": value,
        }
        return self.execute(query, variables)

    def change_label_status(
        self,
        board_id: str | int,
        item_id: str | int,
        status_value: str,
        *,
        column_id: str = "status",
    ) -> JsonDict:
        """Change a status label using a simple string value."""
        return self.change_simple_column_value(
            board_id=board_id,
            item_id=item_id,
            column_id=column_id,
            value=status_value,
        )

    def create_item(
        self,
        board_id: str | int,
        item_name: str,
        column_values: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        """Create an item, optionally with initial column values."""
        if not item_name or not item_name.strip():
            raise ValueError("item_name must not be empty")

        if column_values is None:
            query = """
            mutation CreateItem($boardId: ID!, $itemName: String!) {
                create_item(board_id: $boardId, item_name: $itemName) {
                    id
                    name
                }
            }
            """
            variables = {
                "boardId": str(board_id),
                "itemName": item_name.strip(),
            }
        else:
            query = """
            mutation CreateItem(
                $boardId: ID!
                $itemName: String!
                $columnValues: JSON!
            ) {
                create_item(
                    board_id: $boardId
                    item_name: $itemName
                    column_values: $columnValues
                ) {
                    id
                    name
                }
            }
            """
            variables = {
                "boardId": str(board_id),
                "itemName": item_name.strip(),
                "columnValues": json.dumps(dict(column_values)),
            }

        return self.execute(query, variables)

    def update_item(
        self,
        board_id: str | int,
        item_id: str | int,
        column_values: Mapping[str, Any],
    ) -> JsonDict:
        """Update multiple column values on an item."""
        if not column_values:
            raise ValueError("column_values must not be empty")

        query = """
        mutation UpdateItem(
            $boardId: ID!
            $itemId: ID!
            $columnValues: JSON!
        ) {
            change_multiple_column_values(
                board_id: $boardId
                item_id: $itemId
                column_values: $columnValues
            ) {
                id
            }
        }
        """
        variables = {
            "boardId": str(board_id),
            "itemId": str(item_id),
            "columnValues": json.dumps(dict(column_values)),
        }
        return self.execute(query, variables)

    def delete_item(self, item_id: str | int) -> JsonDict:
        """Delete an item."""
        query = """
        mutation DeleteItem($itemId: ID!) {
            delete_item(item_id: $itemId) {
                id
            }
        }
        """
        return self.execute(query, {"itemId": str(item_id)})


__all__ = ["MondayAPIError", "MondayClient"]
