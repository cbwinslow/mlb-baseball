
"""
================================================================================
MLB Parameter Handling
Date: 2026-05-09

Parameter transformation and validation for MLB API.
================================================================================
"""

from datetime import date
from typing import Any, Dict, Optional


class MLBParamTransformer:
    """Transform and validate parameters for MLB API."""

    # MLB API base parameters
    SPORT_ID_MLB = 1

    @classmethod
    def schedule_params(
        cls,
        season: Optional[int] = None,
        team_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Build schedule endpoint parameters.

        Args:
            season: Season year
            team_id: Team ID
            start_date: Start date
            end_date: End date

        Returns:
            Parameters dict for schedule endpoint
        """
        params = {'sportId': cls.SPORT_ID_MLB}

        if season:
            params['season'] = season
        if team_id:
            params['teamId'] = team_id
        if start_date:
            params['dateStart'] = start_date.isoformat()
        if end_date:
            params['dateEnd'] = end_date.isoformat()

        return params

    @classmethod
    def game_params(cls, game_pk: int) -> Dict[str, Any]:
        """Build game endpoint parameters.

        Args:
            game_pk: Game ID

        Returns:
            Parameters dict
        """
        return {'gamePk': game_pk}

    @classmethod
    def person_params(
        cls,
        person_id: int,
        season: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Build person/player stats parameters.

        Args:
            person_id: Person ID
            season: Season year

        Returns:
            Parameters dict
        """
        params = {'personId': person_id}

        if season:
            params['season'] = season

        return params