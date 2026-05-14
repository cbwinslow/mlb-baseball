#!/usr/bin/env python3
"""
================================================================================
Name: baseball/data/query.py
Date: 2026-05-09
Script Name: Query Building and Parameter Management
Version: 2.0.0

Description:
    Build and validate queries for different endpoints.
    Handles parameter transformation, validation, and optimization.

    - QueryBuilder: Construct queries from params
    - ParamValidator: Validate params against endpoint spec
    - ParamTransformer: Transform param names/formats

================================================================================
"""

from dataclasses import dataclass
from typing import Any

from baseball.core.enums import DataGranularity, SourceType


@dataclass
class Endpoint:
    """Minimal endpoint descriptor (url, http method, timeout, param defaults)."""
    base_url: str
    method: str = "GET"
    timeout: int = 30
    param_defaults: dict[str, Any] = None
    required_params: list[str] = None

    def __post_init__(self) -> None:
        if self.param_defaults is None:
            self.param_defaults = {}
        if self.required_params is None:
            self.required_params = []

    def validate_params(self, **params: Any) -> tuple[bool, str | None]:
        missing = [p for p in self.required_params if p not in params]
        if missing:
            return False, f"Missing required params: {missing}"
        return True, None


class _EndpointRegistry:
    """Simple registry mapping (source, type, granularity) -> Endpoint."""

    def __init__(self) -> None:
        self._registry: dict[tuple, Endpoint] = {}

    def register(self, source: SourceType, endpoint_type: str, granularity: DataGranularity, endpoint: Endpoint) -> None:
        self._registry[(source, endpoint_type, granularity)] = endpoint

    def get_endpoint(self, source: SourceType, endpoint_type: str, granularity: DataGranularity) -> Endpoint | None:
        return self._registry.get((source, endpoint_type, granularity))


endpoint_registry = _EndpointRegistry()


@dataclass
class Query:
    """Represents a validated, ready-to-execute query."""

    endpoint: Endpoint
    params: dict[str, Any]

    def to_request_kwargs(self) -> dict[str, Any]:
        """Convert to kwargs for requests/httpx."""
        kwargs = {
            "url": self.endpoint.base_url,
            "method": self.endpoint.method,
            "timeout": self.endpoint.timeout,
        }

        if self.endpoint.method == "GET":
            kwargs["params"] = self.params
        else:
            kwargs["data"] = self.params

        return kwargs


class ParamTransformer:
    """Transform parameter names and formats for different APIs."""

    # Map internal param names to API-specific names
    TRANSFORMS = {
        SourceType.MLB: {
            "season": "season",
            "team_id": "teamId",
            "game_pk": "gamePk",
            "person_id": "personId",
            "sport_id": "sportId",
            "start_date": "date",  # Sometimes used as date filter
            "end_date": "dateEnd",
        },
        SourceType.STATCAST: {
            "start_date": "game_date_gt",
            "end_date": "game_date_lt",
            "pitcher_id": "pitcher_lookup",
            "batter_id": "batters_lookup",
            "pitch_type": "pitch_type",
            "team": "team",
        },
        SourceType.FANGRAPHS: {
            "season": "season",
            "stats_type": "stats",
            "league": "lg",
            "qual": "qual",
            "type": "type",
            "position": "pos",
        },
    }

    @classmethod
    def transform(
        cls,
        source: SourceType,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Transform params for source."""
        transform_map = cls.TRANSFORMS.get(source, {})

        result = {}
        for internal_name, value in params.items():
            external_name = transform_map.get(internal_name, internal_name)
            result[external_name] = value

        return result


class QueryBuilder:
    """Build queries for different endpoints."""

    def __init__(self, transformer: ParamTransformer | None = None):
        self.transformer = transformer or ParamTransformer()

    def build(
        self,
        source: SourceType,
        endpoint_type: str,
        granularity: DataGranularity,
        **params,
    ) -> Query:
        """
        Build a query for given endpoint.

        Raises ValueError if params invalid.
        """
        # Get endpoint definition
        endpoint = endpoint_registry.get_endpoint(
            source,
            endpoint_type,
            granularity,
        )

        if not endpoint:
            raise ValueError(
                f"No endpoint for {source.value}/{endpoint_type}/{granularity.value}"
            )

        # Validate params
        is_valid, error = endpoint.validate_params(**params)
        if not is_valid:
            raise ValueError(f"Invalid params: {error}")

        # Apply defaults
        all_params = {**endpoint.param_defaults, **params}

        # Remove None values
        all_params = {k: v for k, v in all_params.items() if v is not None}

        # Transform param names
        transformed = self.transformer.transform(source, all_params)

        return Query(endpoint=endpoint, params=transformed)


# Global query builder
query_builder = QueryBuilder()
