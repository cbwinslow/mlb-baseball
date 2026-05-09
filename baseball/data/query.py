
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

from typing import Any, Optional
from dataclasses import dataclass

from baseball.data.endpoints import Endpoint, endpoint_registry
from baseball.data.config import SourceType, DataGranularity


@dataclass
class Query:
    """Represents a validated, ready-to-execute query."""
    endpoint: Endpoint
    params: dict[str, Any]
    
    def to_request_kwargs(self) -> dict[str, Any]:
        """Convert to kwargs for requests/httpx."""
        kwargs = {
            'url': self.endpoint.base_url,
            'method': self.endpoint.method,
            'timeout': self.endpoint.timeout,
        }
        
        if self.endpoint.method == 'GET':
            kwargs['params'] = self.params
        else:
            kwargs['data'] = self.params
        
        return kwargs


class ParamTransformer:
    """Transform parameter names and formats for different APIs."""
    
    # Map internal param names to API-specific names
    TRANSFORMS = {
        SourceType.MLB: {
            'season': 'season',
            'team_id': 'teamId',
            'game_pk': 'gamePk',
            'person_id': 'personId',
            'sport_id': 'sportId',
            'start_date': 'date',  # Sometimes used as date filter
            'end_date': 'dateEnd',
        },
        SourceType.STATCAST: {
            'start_date': 'game_date_gt',
            'end_date': 'game_date_lt',
            'pitcher_id': 'pitcher_lookup',
            'batter_id': 'batters_lookup',
            'pitch_type': 'pitch_type',
            'team': 'team',
        },
        SourceType.FANGRAPHS: {
            'season': 'season',
            'stats_type': 'stats',
            'league': 'lg',
            'qual': 'qual',
            'type': 'type',
            'position': 'pos',
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
    
    def __init__(self, transformer: Optional[ParamTransformer] = None):
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
                f'No endpoint for {source.value}/{endpoint_type}/{granularity.value}'
            )
        
        # Validate params
        is_valid, error = endpoint.validate_params(**params)
        if not is_valid:
            raise ValueError(f'Invalid params: {error}')
        
        # Apply defaults
        all_params = {**endpoint.param_defaults, **params}
        
        # Remove None values
        all_params = {k: v for k, v in all_params.items() if v is not None}
        
        # Transform param names
        transformed = self.transformer.transform(source, all_params)
        
        return Query(endpoint=endpoint, params=transformed)


# Global query builder
query_builder = QueryBuilder()