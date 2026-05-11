"""
================================================================================
ID Bridging and Crosswalk Management
Name: bridge.py
Date: 2026-05-11
Script: bridge.py
Version: 1.0.0
Log Summary: Manage player, team, and park ID mappings across sources
Description: Reconcile IDs from MLBAM, Retrosheet, Lahman, FanGraphs, BBRef
Change Summary: Initial implementation with crosswalk utilities
Inputs: IDs from multiple sources, canonical IDs
Outputs: Merged ID relationships, validation reports
================================================================================
"""

from typing import Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from baseball.core.logging import get_logger
from baseball.db.models import (
    Park,
    ParkXwalk,
    Player,
    PlayerXwalk,
    Team,
    TeamXwalk,
)

logger = get_logger(__name__)


class IDBridge:
    """Manage ID crosswalks across all baseball data sources."""

    def __init__(self, session: Session):
        """Initialize ID bridge.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    # ==================== PLAYER ID BRIDGING ====================

    def find_or_create_player(
        self,
        mlbam_id: Optional[int] = None,
        retrosheet_id: Optional[str] = None,
        lahman_id: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Optional[Player]:
        """Find existing player or create new one.

        Args:
            mlbam_id: MLB Advanced Media player ID
            retrosheet_id: Retrosheet player ID
            lahman_id: Lahman database ID
            first_name: Player first name (required for new)
            last_name: Player last name (required for new)

        Returns:
            Player object or None
        """
        # Try to find by ID first
        if mlbam_id:
            player = self.session.query(Player).filter_by(
                player_mlbam_id=mlbam_id
            ).first()
            if player:
                return player

        if retrosheet_id:
            player = self.session.query(Player).filter_by(
                player_retrosheet_id=retrosheet_id
            ).first()
            if player:
                return player

        if lahman_id:
            player = self.session.query(Player).filter_by(
                player_lahman_id=lahman_id
            ).first()
            if player:
                return player

        # Create new player if IDs provided
        if first_name and last_name:
            player = Player(
                first_name=first_name,
                last_name=last_name,
                player_mlbam_id=mlbam_id,
                player_retrosheet_id=retrosheet_id,
                player_lahman_id=lahman_id,
            )
            self.session.add(player)
            self.session.commit()
            logger.info(
                f"Created new player: {first_name} {last_name} "
                f"(mlbam={mlbam_id}, retrosheet={retrosheet_id})"
            )
            return player

        logger.warning(
            "Cannot find or create player - no IDs and no name provided"
        )
        return None

    def create_player_xwalk(
        self,
        player_id: int,
        mlbam_id: Optional[int] = None,
        retrosheet_id: Optional[str] = None,
        lahman_id: Optional[str] = None,
        fangraphs_id: Optional[int] = None,
        bbref_id: Optional[str] = None,
    ) -> Optional[PlayerXwalk]:
        """Create or update player ID crosswalk.

        Args:
            player_id: Canonical player ID
            mlbam_id: MLB Advanced Media ID
            retrosheet_id: Retrosheet ID
            lahman_id: Lahman ID
            fangraphs_id: FanGraphs ID
            bbref_id: Baseball-Reference ID

        Returns:
            PlayerXwalk record or None
        """
        try:
            xwalk = PlayerXwalk(
                player_id=player_id,
                mlbam_id=mlbam_id,
                retrosheet_id=retrosheet_id,
                lahman_id=lahman_id,
                fangraphs_id=fangraphs_id,
                bbref_id=bbref_id,
            )
            self.session.add(xwalk)
            self.session.commit()
            logger.info(f"Created player crosswalk for player_id {player_id}")
            return xwalk
        except Exception as e:
            logger.error(f"Failed to create player crosswalk: {e}")
            self.session.rollback()
            return None

    # ==================== TEAM ID BRIDGING ====================

    def find_or_create_team(
        self,
        team_abbr: str,
        team_name: str,
        league: str,
        mlbam_id: Optional[int] = None,
        retrosheet_id: Optional[str] = None,
        lahman_id: Optional[str] = None,
    ) -> Optional[Team]:
        """Find existing team or create new one.

        Args:
            team_abbr: Team abbreviation (e.g., 'NYY')
            team_name: Full team name
            league: League ('AL' or 'NL')
            mlbam_id: MLB Advanced Media team ID
            retrosheet_id: Retrosheet team ID
            lahman_id: Lahman team ID

        Returns:
            Team object or None
        """
        # Try to find by ID first
        if mlbam_id:
            team = self.session.query(Team).filter_by(
                team_mlbam_id=mlbam_id
            ).first()
            if team:
                return team

        if retrosheet_id:
            team = self.session.query(Team).filter_by(
                team_retrosheet_id=retrosheet_id
            ).first()
            if team:
                return team

        # Try by abbreviation
        team = self.session.query(Team).filter_by(team_abbr=team_abbr).first()
        if team:
            return team

        # Create new team
        team = Team(
            team_name=team_name,
            team_abbr=team_abbr,
            league=league,
            team_mlbam_id=mlbam_id,
            team_retrosheet_id=retrosheet_id,
            team_lahman_id=lahman_id,
        )
        self.session.add(team)
        self.session.commit()
        logger.info(f"Created new team: {team_abbr} {team_name}")
        return team

    def create_team_xwalk(
        self,
        team_id: int,
        mlbam_id: Optional[int] = None,
        retrosheet_id: Optional[str] = None,
        lahman_id: Optional[str] = None,
        bbref_id: Optional[str] = None,
    ) -> Optional[TeamXwalk]:
        """Create or update team ID crosswalk.

        Args:
            team_id: Canonical team ID
            mlbam_id: MLB Advanced Media ID
            retrosheet_id: Retrosheet ID
            lahman_id: Lahman ID
            bbref_id: Baseball-Reference ID

        Returns:
            TeamXwalk record or None
        """
        try:
            xwalk = TeamXwalk(
                team_id=team_id,
                mlbam_id=mlbam_id,
                retrosheet_id=retrosheet_id,
                lahman_id=lahman_id,
                bbref_id=bbref_id,
            )
            self.session.add(xwalk)
            self.session.commit()
            logger.info(f"Created team crosswalk for team_id {team_id}")
            return xwalk
        except Exception as e:
            logger.error(f"Failed to create team crosswalk: {e}")
            self.session.rollback()
            return None

    # ==================== PARK ID BRIDGING ====================

    def find_or_create_park(
        self,
        park_name: str,
        mlbam_id: Optional[int] = None,
        retrosheet_id: Optional[str] = None,
        home_team_id: Optional[int] = None,
    ) -> Optional[Park]:
        """Find existing park or create new one.

        Args:
            park_name: Park name
            mlbam_id: MLB Advanced Media park ID
            retrosheet_id: Retrosheet park ID
            home_team_id: Home team ID

        Returns:
            Park object or None
        """
        # Try to find by ID first
        if mlbam_id:
            park = self.session.query(Park).filter_by(
                park_mlbam_id=mlbam_id
            ).first()
            if park:
                return park

        if retrosheet_id:
            park = self.session.query(Park).filter_by(
                park_retrosheet_id=retrosheet_id
            ).first()
            if park:
                return park

        # Try by name
        park = self.session.query(Park).filter_by(park_name=park_name).first()
        if park:
            return park

        # Create new park
        park = Park(
            park_name=park_name,
            park_mlbam_id=mlbam_id,
            park_retrosheet_id=retrosheet_id,
            home_team_id=home_team_id,
        )
        self.session.add(park)
        self.session.commit()
        logger.info(f"Created new park: {park_name}")
        return park

    def create_park_xwalk(
        self,
        park_id: int,
        mlbam_id: Optional[int] = None,
        retrosheet_id: Optional[str] = None,
        bbref_id: Optional[str] = None,
    ) -> Optional[ParkXwalk]:
        """Create or update park ID crosswalk.

        Args:
            park_id: Canonical park ID
            mlbam_id: MLB Advanced Media ID
            retrosheet_id: Retrosheet ID
            bbref_id: Baseball-Reference ID

        Returns:
            ParkXwalk record or None
        """
        try:
            xwalk = ParkXwalk(
                park_id=park_id,
                mlbam_id=mlbam_id,
                retrosheet_id=retrosheet_id,
                bbref_id=bbref_id,
            )
            self.session.add(xwalk)
            self.session.commit()
            logger.info(f"Created park crosswalk for park_id {park_id}")
            return xwalk
        except Exception as e:
            logger.error(f"Failed to create park crosswalk: {e}")
            self.session.rollback()
            return None
