#!/usr/bin/env python3
"""
Test script for FastAPI OTel endpoints
Exercises all endpoints to generate metrics
"""

import requests
import time
import sys
from typing import Dict, Any
import json

BASE_URL = "http://localhost:8000"


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'


def print_test(name: str):
    print(f"\n{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"{Colors.BLUE}Testing: {name}{Colors.END}")
    print(f"{Colors.BLUE}{'=' * 60}{Colors.END}")


def print_success(message: str):
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")


def print_error(message: str):
    print(f"{Colors.RED}✗ {message}{Colors.END}")


def print_response(response: requests.Response):
    print(f"Status: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response: {response.text}")


def test_root():
    print_test("GET / - Root endpoint")
    try:
        response = requests.get(f"{BASE_URL}/")
        print_response(response)
        if response.status_code == 200:
            print_success("Root endpoint working")
        else:
            print_error(f"Unexpected status: {response.status_code}")
    except Exception as e:
        print_error(f"Error: {e}")


def test_health():
    print_test("GET /health - Health check")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print_response(response)
        if response.status_code == 200:
            print_success("Health check passed")
        else:
            print_error(f"Health check failed: {response.status_code}")
    except Exception as e:
        print_error(f"Error: {e}")


def test_create_items():
    print_test("POST /items - Create items")
    items = [
        {"name": "Laptop", "description": "High-performance laptop", "price": 1299.99, "tax": 129.99},
        {"name": "Mouse", "description": "Wireless mouse", "price": 29.99, "tax": 2.99},
        {"name": "Keyboard", "description": "Mechanical keyboard", "price": 89.99},
    ]

    created_ids = []
    for item in items:
        try:
            response = requests.post(f"{BASE_URL}/items", json=item)
            print(f"\nCreating: {item['name']}")
            print_response(response)
            if response.status_code == 201:
                created_ids.append(response.json()["id"])
                print_success(f"Created item: {item['name']}")
            else:
                print_error(f"Failed to create: {response.status_code}")
        except Exception as e:
            print_error(f"Error creating item: {e}")

    return created_ids


def test_list_items():
    print_test("GET /items - List all items")
    try:
        response = requests.get(f"{BASE_URL}/items")
        print_response(response)
        if response.status_code == 200:
            count = response.json().get("count", 0)
            print_success(f"Retrieved {count} items")
        else:
            print_error(f"Failed to list items: {response.status_code}")
    except Exception as e:
        print_error(f"Error: {e}")


def test_get_item(item_id: str):
    print_test(f"GET /items/{item_id} - Get specific item")
    try:
        response = requests.get(f"{BASE_URL}/items/{item_id}")
        print_response(response)
        if response.status_code == 200:
            print_success(f"Retrieved item {item_id}")
        else:
            print_error(f"Failed to get item: {response.status_code}")
    except Exception as e:
        print_error(f"Error: {e}")


def test_update_item(item_id: str):
    print_test(f"PUT /items/{item_id} - Update item")
    updated_data = {
        "name": "Updated Laptop",
        "description": "Ultra high-performance laptop - Updated",
        "price": 1499.99,
        "tax": 149.99
    }
    try:
        response = requests.put(f"{BASE_URL}/items/{item_id}", json=updated_data)
        print_response(response)
        if response.status_code == 200:
            print_success(f"Updated item {item_id}")
        else:
            print_error(f"Failed to update item: {response.status_code}")
    except Exception as e:
        print_error(f"Error: {e}")


def test_delete_item(item_id: str):
    print_test(f"DELETE /items/{item_id} - Delete item")
    try:
        response = requests.delete(f"{BASE_URL}/items/{item_id}")
        print(f"Status: {response.status_code}")
        if response.status_code == 204:
            print_success(f"Deleted item {item_id}")
        else:
            print_error(f"Failed to delete item: {response.status_code}")
    except Exception as e:
        print_error(f"Error: {e}")


def test_slow_endpoint():
    print_test("GET /simulate/slow - Test latency metrics")
    try:
        print("Calling slow endpoint (1-3s delay expected)...")
        start = time.time()
        response = requests.get(f"{BASE_URL}/simulate/slow")
        duration = time.time() - start
        print_response(response)
        print(f"Duration: {duration:.2f}s")
        if response.status_code == 200:
            print_success("Slow endpoint completed")
        else:
            print_error(f"Unexpected status: {response.status_code}")
    except Exception as e:
        print_error(f"Error: {e}")


def test_error_endpoint():
    print_test("GET /simulate/error - Test error rate metrics")
    successes = 0
    errors = 0
    attempts = 10

    print(f"Making {attempts} requests to test error rate...")
    for i in range(attempts):
        try:
            response = requests.get(f"{BASE_URL}/simulate/error")
            if response.status_code == 200:
                successes += 1
                print(f"{Colors.GREEN}#{i + 1}: Success{Colors.END}")
            else:
                errors += 1
                print(f"{Colors.RED}#{i + 1}: Error {response.status_code}{Colors.END}")
        except Exception as e:
            errors += 1
            print(f"{Colors.RED}#{i + 1}: Exception: {e}{Colors.END}")

    print(f"\nResults: {successes} successes, {errors} errors")
    print_success(f"Error endpoint test complete - {errors / attempts * 100:.0f}% error rate")


def test_404():
    print_test("GET /items/999 - Test 404 handling")
    try:
        response = requests.get(f"{BASE_URL}/items/999")
        print_response(response)
        if response.status_code == 404:
            print_success("404 handling works correctly")
        else:
            print_error(f"Expected 404, got: {response.status_code}")
    except Exception as e:
        print_error(f"Error: {e}")


def run_all_tests():
    print(f"\n{Colors.YELLOW}{'=' * 60}")
    print("FastAPI OTel Endpoint Testing Suite")
    print(f"{'=' * 60}{Colors.END}\n")
    print(f"Target: {BASE_URL}")
    print(f"This will generate various metrics for testing\n")

    # Check if server is running
    try:
        requests.get(f"{BASE_URL}/health", timeout=2)
    except requests.exceptions.RequestException:
        print_error(f"Cannot connect to {BASE_URL}")
        print("Make sure the FastAPI server is running:")
        print("  python main.py")
        sys.exit(1)

    # Run tests
    test_root()
    test_health()

    # CRUD operations
    created_ids = test_create_items()
    test_list_items()

    if created_ids:
        test_get_item(created_ids[0])
        test_update_item(created_ids[0])
        test_delete_item(created_ids[-1])

    # Test error scenarios
    test_404()
    test_slow_endpoint()
    test_error_endpoint()

    print(f"\n{Colors.YELLOW}{'=' * 60}")
    print("Testing Complete!")
    print(f"{'=' * 60}{Colors.END}")
    print("\nMetrics should now be visible in your OTel collector/backend")
    print("Check the following metrics:")
    print("  - http.server.duration (automatic)")
    print("  - http.server.request.count (automatic)")
    print("  - custom.requests.total")
    print("  - custom.processing.duration")
    print("  - custom.active.connections")


if __name__ == "__main__":
    run_all_tests()