"""Tests for baseball.db.models (SQLAlchemy ORM models)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from baseball.db.models import Base, Player, Team


@pytest.fixture(scope="module")
def engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    """Create a database session for each test."""
    with Session(engine) as session:
        yield session
        session.rollback()


class TestBase:
    def test_base_is_declarative(self):
        """Test that Base is a valid declarative base."""
        assert hasattr(Base, "metadata")
        assert hasattr(Base, "registry")

    def test_tables_created(self, engine):
        """Test that all tables are created."""
        table_names = engine.dialect.get_table_names(engine.connect())
        assert "player" in table_names
        assert "team" in table_names


class TestPlayerModel:
    def test_player_table_name(self):
        assert Player.__tablename__ == "player"

    def test_player_has_required_columns(self):
        columns = {col.name for col in Player.__table__.columns}
        assert "player_id" in columns
        assert "first_name" in columns
        assert "last_name" in columns

    def test_create_player(self, db_session):
        player = Player(
            first_name="Babe",
            last_name="Ruth",
            bats="L",
            throws="R",
        )
        db_session.add(player)
        db_session.flush()
        assert player.player_id is not None

    def test_player_primary_key(self):
        pk_columns = [col for col in Player.__table__.columns if col.primary_key]
        assert len(pk_columns) >= 1
        assert pk_columns[0].name == "player_id"


class TestTeamModel:
    def test_team_table_name(self):
        assert Team.__tablename__ == "team"

    def test_team_has_required_columns(self):
        columns = {col.name for col in Team.__table__.columns}
        assert "team_id" in columns
        assert "team_name" in columns
        assert "team_abbr" in columns

    def test_create_team(self, db_session):
        team = Team(
            team_name="New York Yankees",
            team_abbr="NYY",
            league="AL",
            division="ALE",
        )
        db_session.add(team)
        db_session.flush()
        assert team.team_id is not None

    def test_team_primary_key(self):
        pk_columns = [col for col in Team.__table__.columns if col.primary_key]
        assert len(pk_columns) >= 1
        assert pk_columns[0].name == "team_id"
