#!/usr/bin/env python3
"""
Test script for the new pre-approval and document tracking features.
This demonstrates how to use the admin endpoints to manage user pre-approval status.
"""

import requests
import json
from datetime import datetime, timedelta

# Base URL for the API
BASE_URL = "http://localhost:8000/v1"

# You'll need to get a valid auth token first
# For testing, you can use the login endpoint with admin credentials

def get_auth_token(email, password):
    """Get an auth token by logging in"""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": email, "password": password}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        print(f"Login failed: {response.text}")
        return None


def test_preapproval_workflow(token, user_id):
    """Test the pre-approval workflow"""
    headers = {"Authorization": f"Bearer {token}"}

    print("\n1. Checking current pre-approval status...")
    response = requests.get(
        f"{BASE_URL}/admin/preapproval/users/{user_id}/preapproval",
        headers=headers
    )
    print(f"Current status: {json.dumps(response.json(), indent=2)}")

    print("\n2. Setting user as pre-approved...")
    preapproval_data = {
        "is_preapproved": True,
        "preapproved_amount": 75000.00,
        "preapproved_until": (datetime.utcnow() + timedelta(days=30)).isoformat(),
        "external_financing_bank": "Chase Bank",
        "external_financing_status": "approved"
    }

    response = requests.put(
        f"{BASE_URL}/admin/preapproval/users/{user_id}/preapproval",
        json=preapproval_data,
        headers=headers
    )

    if response.status_code == 200:
        print(f"Pre-approval updated: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"Failed to update pre-approval: {response.text}")

    print("\n3. Checking pending pre-approvals...")
    response = requests.get(
        f"{BASE_URL}/admin/preapproval/preapproval/pending",
        headers=headers
    )
    print(f"Pending pre-approvals: {json.dumps(response.json(), indent=2)}")

    print("\n4. Now the user should be able to request condition reports!")
    print("   Test with: POST /v1/me/vehicles/{vin}/condition-report-request")


def test_document_tracking(token, deal_id):
    """Test document tracking functionality"""
    headers = {"Authorization": f"Bearer {token}"}

    print("\n5. Updating document status for a deal...")
    document_data = {
        "identity_verified": True,
        "income_verified": True,
        "preapproval_letter_url": "https://ghl-storage.example.com/docs/preapproval_12345.pdf",
        "loan_documents_url": "https://ghl-storage.example.com/docs/loan_12345.pdf",
        "documents_collected": {
            "drivers_license": "https://ghl-storage.example.com/docs/dl_12345.jpg",
            "paystub_1": "https://ghl-storage.example.com/docs/paystub1_12345.pdf",
            "paystub_2": "https://ghl-storage.example.com/docs/paystub2_12345.pdf",
            "bank_preapproval": "https://ghl-storage.example.com/docs/chase_approval_12345.pdf"
        }
    }

    response = requests.put(
        f"{BASE_URL}/admin/preapproval/deals/{deal_id}/documents",
        json=document_data,
        headers=headers
    )

    if response.status_code == 200:
        print(f"Documents updated: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"Failed to update documents: {response.text}")


if __name__ == "__main__":
    print("=== VirtualCarHub Pre-Approval Test Script ===")
    print("\nThis script demonstrates the new pre-approval and document tracking features.")
    print("\nTo use this script:")
    print("1. Make sure you have an admin account (email ending in @virtualcarhub.com)")
    print("2. Get the user_id of a test user from the database")
    print("3. Get the deal_id of a test deal from the database")
    print("4. Run: python3 test_preapproval.py")

    # Example usage (you'll need to provide real values):
    # admin_email = "admin@virtualcarhub.com"
    # admin_password = "your-admin-password"
    # test_user_id = "user-uuid-here"
    # test_deal_id = "deal-uuid-here"

    # token = get_auth_token(admin_email, admin_password)
    # if token:
    #     test_preapproval_workflow(token, test_user_id)
    #     test_document_tracking(token, test_deal_id)

    print("\n\n=== Manual Testing Instructions ===")
    print("\n1. To manually set a user as pre-approved (replace USER_ID and TOKEN):")
    print("""
    curl -X PUT http://localhost:8000/v1/admin/preapproval/users/USER_ID/preapproval \\
      -H "Authorization: Bearer TOKEN" \\
      -H "Content-Type: application/json" \\
      -d '{
        "is_preapproved": true,
        "preapproved_amount": 50000,
        "preapproved_until": "2026-04-16T00:00:00"
      }'
    """)

    print("\n2. To check pending pre-approvals:")
    print("""
    curl http://localhost:8000/v1/admin/preapproval/preapproval/pending \\
      -H "Authorization: Bearer TOKEN"
    """)

    print("\n3. To test condition report access (as the pre-approved user):")
    print("""
    curl -X POST http://localhost:8000/v1/me/vehicles/VIN/condition-report-request \\
      -H "Authorization: Bearer USER_TOKEN"
    """)