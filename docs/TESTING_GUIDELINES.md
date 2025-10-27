# Testing Guidelines for FastAPI Applications

> Comprehensive testing strategies and patterns for production-ready FastAPI applications

This document provides battle-tested testing principles and patterns for FastAPI applications, focusing on comprehensive coverage, maintainability, and production readiness.

---

## Table of Contents

- [Core Testing Principles](#core-testing-principles)
- [Testing Philosophy](#testing-philosophy)
- [FastAPI Testing Patterns](#fastapi-testing-patterns)
- [pytest-mock Patterns](#pytest-mock-patterns)
- [Dependency Injection Testing](#dependency-injection-testing)
- [Async Testing](#async-testing)
- [Database Testing](#database-testing)
- [External Service Mocking](#external-service-mocking)
- [Testing Best Practices](#testing-best-practices)

---

## Core Testing Principles

These are project-wide expectations for all tests:

1. **Coverage**: Test all classes and functions except trivial pass-through logic
2. **Success & Failure Cases**: Every feature must include both paths
3. **Varied Failure Cases**: Test invalid parameters, type mismatches, and early exits
4. **Success Cases**: Represent the only valid path after filtering failures
5. **No Forced Changes**: Don't force production code changes just for tests; fix real bugs found during testing

---

## Testing Philosophy

### Success vs Failure Testing

**Success Cases**:
- Test the "happy path" when all preconditions are met
- Verify correct behavior with valid inputs
- Confirm expected side effects (database updates, external calls)

**Failure Cases**:
- Invalid parameters (null, wrong type, out of range)
- Type mismatches (string when integer expected)
- Business logic failures (insufficient balance, not found)
- External service failures (network errors, timeouts)
- Database failures (constraint violations, connection loss)

### Example: Comprehensive Test Coverage

```python
# Success case
async def test_create_user_success():
    """Test successful user creation with valid data."""
    user_data = {"email": "user@example.com", "name": "John Doe"}
    result = await create_user(user_data)

    assert result.id is not None
    assert result.email == "user@example.com"
    assert result.name == "John Doe"

# Failure cases
async def test_create_user_invalid_email():
    """Test user creation with invalid email format."""
    user_data = {"email": "invalid-email", "name": "John Doe"}

    with pytest.raises(ValidationError):
        await create_user(user_data)

async def test_create_user_duplicate_email():
    """Test user creation with already-existing email."""
    user_data = {"email": "existing@example.com", "name": "John Doe"}

    with pytest.raises(DuplicateEmailError):
        await create_user(user_data)

async def test_create_user_database_error():
    """Test user creation when database fails."""
    user_data = {"email": "user@example.com", "name": "John Doe"}

    with pytest.raises(DatabaseError):
        await create_user(user_data)
```

---

## FastAPI Testing Patterns

### Using TestClient (Synchronous)

For simple synchronous endpoints:

```python
from fastapi.testclient import TestClient
from myapp.main import app

client = TestClient(app)

def test_read_root():
    """Test GET / endpoint."""
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}

def test_create_item():
    """Test POST /items endpoint."""
    response = client.post(
        "/items",
        json={"name": "Test Item", "price": 10.5}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Item"
    assert data["price"] == 10.5
```

### Using AsyncClient (Asynchronous)

For async endpoints with proper async/await:

```python
import pytest
from httpx import AsyncClient
from myapp.main import app

@pytest.mark.asyncio
async def test_read_users():
    """Test GET /users endpoint (async)."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/users")

    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_create_user_async():
    """Test POST /users endpoint with async client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post(
            "/users",
            json={"email": "test@example.com", "name": "Test User"}
        )

    assert response.status_code == 201
    assert response.json()["email"] == "test@example.com"
```

---

## pytest-mock Patterns

### Basic Stub Pattern

Use simple stub classes for predictable behavior:

```python
import pytest

@pytest.mark.asyncio
async def test_feature_success(mocker):
    """Test successful feature execution with stubbed dependency."""

    # Create stub class with predictable behavior
    class FakeRunResult:
        def __init__(self, output):
            self.output = output

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            self._output = {"status": "success", "data": [1, 2, 3]}

        async def run(self, prompt):
            return FakeRunResult(self._output)

    # Patch the dependency
    mocker.patch('myapp.services.Agent', return_value=FakeAgent())

    # Execute feature
    result = await feature_under_test("test input")

    assert result["status"] == "success"
    assert result["data"] == [1, 2, 3]
```

### Failure Case Pattern

```python
@pytest.mark.asyncio
async def test_feature_failure(mocker):
    """Test feature handling when dependency fails."""

    class FakeAgent:
        async def run(self, prompt):
            raise RuntimeError("LLM service unavailable")

    mocker.patch('myapp.services.Agent', return_value=FakeAgent())

    with pytest.raises(RuntimeError, match="LLM service unavailable"):
        await feature_under_test("test input")
```

### Spy Pattern (Verify Calls)

```python
@pytest.mark.asyncio
async def test_feature_calls_agent_correctly(mocker):
    """Verify that feature calls agent with correct parameters."""

    fake_agent = mocker.AsyncMock()
    fake_agent.run.return_value = {"status": "success"}

    mocker.patch('myapp.services.Agent', return_value=fake_agent)

    await feature_under_test("test input")

    # Verify the agent was called correctly
    fake_agent.run.assert_called_once_with("test input")
```

---

## Dependency Injection Testing

### Overriding Dependencies

FastAPI's `dependency_overrides` allows you to replace dependencies for testing:

```python
from fastapi import Depends
from fastapi.testclient import TestClient
from myapp.main import app
from myapp.dependencies import get_db, get_current_user

# Mock database
class MockDatabase:
    async def get_user(self, user_id: int):
        return {"id": user_id, "name": "Test User"}

def test_get_user_endpoint():
    """Test /users/{user_id} with mocked database."""

    # Override database dependency
    def override_get_db():
        return MockDatabase()

    app.dependency_overrides[get_db] = override_get_db

    try:
        client = TestClient(app)
        response = client.get("/users/123")

        assert response.status_code == 200
        assert response.json() == {"id": 123, "name": "Test User"}
    finally:
        # Clean up override
        app.dependency_overrides.clear()
```

### Testing Authentication

```python
from myapp.models import User

def test_protected_endpoint_with_auth():
    """Test protected endpoint with mocked authentication."""

    # Mock authenticated user
    def override_get_current_user():
        return User(id=1, email="test@example.com", role="admin")

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        client = TestClient(app)
        response = client.get("/admin/dashboard")

        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()

def test_protected_endpoint_without_auth():
    """Test protected endpoint without authentication."""

    # Mock unauthenticated request
    def override_get_current_user():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        client = TestClient(app)
        response = client.get("/admin/dashboard")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
```

---

## Async Testing

### pytest-asyncio Setup

```bash
pip install pytest-asyncio
```

```python
# conftest.py
import pytest

# Set default asyncio mode
pytest_plugins = ('pytest_asyncio',)

@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
```

### Testing Async Functions

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Test async function directly."""
    result = await my_async_function()
    assert result == expected_value

@pytest.mark.asyncio
async def test_async_with_timeout():
    """Test async function with timeout."""
    import asyncio

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slow_async_function(), timeout=1.0)
```

---

## Database Testing

### Using Test Database

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from myapp.database import Base

@pytest.fixture(scope="function")
async def test_db():
    """Create test database for each test."""

    # Create test database engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async with AsyncSession(engine) as session:
        yield session

    # Cleanup
    await engine.dispose()

@pytest.mark.asyncio
async def test_create_user_in_db(test_db):
    """Test user creation in database."""
    from myapp.models import User

    user = User(email="test@example.com", name="Test User")
    test_db.add(user)
    await test_db.commit()

    # Verify user was created
    result = await test_db.execute(select(User).where(User.email == "test@example.com"))
    saved_user = result.scalar_one()

    assert saved_user.email == "test@example.com"
    assert saved_user.name == "Test User"
```

### Transaction Rollback Pattern

```python
@pytest.fixture(scope="function")
async def db_session():
    """Database session with automatic rollback."""
    async with async_session_maker() as session:
        async with session.begin():
            yield session
            # Rollback automatically after test
            await session.rollback()
```

---

## External Service Mocking

### Mocking HTTP Clients

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_external_api_call(mocker):
    """Test function that calls external API."""

    # Mock httpx.AsyncClient
    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "test"}

    mock_client.get.return_value = mock_response

    mocker.patch('httpx.AsyncClient', return_value=mock_client)

    result = await fetch_external_data("https://api.example.com/data")

    assert result == {"data": "test"}
    mock_client.get.assert_called_once_with("https://api.example.com/data")
```

### Testing with Failure Scenarios

```python
import httpx
import pytest

@pytest.mark.asyncio
async def test_external_api_timeout(mocker):
    """Test handling of external API timeout."""

    mock_client = mocker.AsyncMock()
    mock_client.get.side_effect = httpx.TimeoutException("Request timeout")

    mocker.patch('httpx.AsyncClient', return_value=mock_client)

    with pytest.raises(httpx.TimeoutException):
        await fetch_external_data("https://api.example.com/data")

@pytest.mark.asyncio
async def test_external_api_500_error(mocker):
    """Test handling of external API server error."""

    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error", request=mocker.Mock(), response=mock_response
    )

    mock_client.get.return_value = mock_response

    mocker.patch('httpx.AsyncClient', return_value=mock_client)

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_external_data("https://api.example.com/data")
```

---

## Testing Best Practices

### 1. Test Isolation

**✅ Good: Independent tests**
```python
def test_create_user():
    """Each test creates its own data."""
    user = create_test_user()
    assert user.id is not None

def test_delete_user():
    """Each test creates its own data."""
    user = create_test_user()
    delete_user(user.id)
    assert get_user(user.id) is None
```

**❌ Bad: Shared state**
```python
# Global state shared between tests
_test_user = None

def test_create_user():
    global _test_user
    _test_user = create_test_user()  # Affects other tests!

def test_delete_user():
    delete_user(_test_user.id)  # Depends on previous test!
```

### 2. Descriptive Test Names

**✅ Good: Clear intent**
```python
def test_user_registration_with_valid_email_creates_user():
    ...

def test_user_registration_with_duplicate_email_raises_error():
    ...

def test_user_registration_without_password_raises_validation_error():
    ...
```

**❌ Bad: Vague names**
```python
def test_user1():
    ...

def test_user2():
    ...
```

### 3. Arrange-Act-Assert Pattern

```python
def test_calculate_discount():
    # Arrange: Set up test data
    cart = Cart()
    cart.add_item(Item(price=100, quantity=2))
    coupon = Coupon(discount_percent=10)

    # Act: Execute the operation
    total = cart.calculate_total(coupon)

    # Assert: Verify the result
    assert total == 180  # 200 - 10% discount
```

### 4. Test Data Factories

Use factories for consistent test data:

```python
# test_factories.py
from datetime import datetime

def create_test_user(**kwargs):
    """Create a test user with sensible defaults."""
    defaults = {
        "email": f"test_{datetime.now().timestamp()}@example.com",
        "name": "Test User",
        "is_active": True,
    }
    defaults.update(kwargs)
    return User(**defaults)

# Usage in tests
def test_user_creation():
    user = create_test_user()
    assert user.is_active is True

def test_inactive_user():
    user = create_test_user(is_active=False)
    assert user.is_active is False
```

### 5. Parametrized Tests

Test multiple scenarios efficiently:

```python
import pytest

@pytest.mark.parametrize("email,expected_valid", [
    ("user@example.com", True),
    ("invalid-email", False),
    ("@example.com", False),
    ("user@", False),
    ("", False),
])
def test_email_validation(email, expected_valid):
    """Test email validation with various inputs."""
    result = is_valid_email(email)
    assert result == expected_valid
```

### 6. Testing Error Messages

```python
def test_insufficient_balance_error_message():
    """Verify error messages are user-friendly."""
    account = Account(balance=10)

    with pytest.raises(InsufficientBalanceError) as exc_info:
        account.withdraw(100)

    assert "insufficient balance" in str(exc_info.value).lower()
    assert "10" in str(exc_info.value)  # Current balance
    assert "100" in str(exc_info.value)  # Requested amount
```

### 7. Testing Logging

```python
import logging

def test_critical_error_is_logged(caplog):
    """Verify that critical errors are logged."""
    with caplog.at_level(logging.ERROR):
        trigger_critical_error()

    assert len(caplog.records) > 0
    assert "critical error" in caplog.records[0].message.lower()
```

---

## Quick Reference

### Common pytest Fixtures

```python
# conftest.py
import pytest

@pytest.fixture
def client():
    """FastAPI test client."""
    from fastapi.testclient import TestClient
    from myapp.main import app
    return TestClient(app)

@pytest.fixture
async def async_client():
    """Async HTTP client."""
    from httpx import AsyncClient
    from myapp.main import app
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def mock_db(mocker):
    """Mocked database."""
    return mocker.AsyncMock()
```

### Useful pytest Markers

```python
@pytest.mark.asyncio          # Async test
@pytest.mark.slow             # Slow test (skip in quick runs)
@pytest.mark.integration      # Integration test
@pytest.mark.parametrize      # Parametrized test
@pytest.mark.skip             # Skip test
@pytest.mark.skipif           # Conditional skip
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=myapp --cov-report=html

# Run specific test file
pytest tests/test_users.py

# Run specific test
pytest tests/test_users.py::test_create_user

# Run tests matching pattern
pytest -k "test_create"

# Run with verbose output
pytest -v

# Run and stop at first failure
pytest -x

# Run only failed tests from last run
pytest --lf
```

---

## Related Resources

- **[FASTAPI_GUIDELINES.md](./FASTAPI_GUIDELINES.md)**: FastAPI development best practices
- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-mock](https://pytest-mock.readthedocs.io/)
