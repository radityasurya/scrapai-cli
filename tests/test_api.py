"""
Test script for ScrapAI API.

Tests basic API functionality including health checks and endpoint availability.
"""

import sys

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test root endpoint returns API info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "ScrapAI API"
    assert data["version"] == "0.1.0"
    assert data["status"] == "operational"
    print("[PASS] Root endpoint test passed")


def test_health_endpoint():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    print("[PASS] Health endpoint test passed")


def test_docs_endpoint():
    """Test OpenAPI docs are available."""
    response = client.get("/docs")
    assert response.status_code == 200
    print("[PASS] API docs endpoint test passed")


if __name__ == "__main__":
    print("Running ScrapAI API tests...")
    print("-" * 50)

    try:
        test_root_endpoint()
        test_health_endpoint()
        test_docs_endpoint()

        print("-" * 50)
        print("[SUCCESS] All tests passed!")
        print("\nScrapAI API is ready to use!")
        print("\nNext steps:")
        print("1. Start the API: python -m uvicorn api.main:app --reload")
        print("2. Visit http://localhost:8000/docs for interactive API docs")
        print("3. Create an API key using the CLI tools")
        print("4. Test endpoints with the API key in the Authorization header")

    except Exception as e:
        print(f"[FAIL] Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
