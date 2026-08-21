import pytest


@pytest.fixture(scope="session", autouse=True)
def _ensure_integration_test_database(_test_database):
    """Ensure integration tests have the isolated test database created and migrated."""
    pass
