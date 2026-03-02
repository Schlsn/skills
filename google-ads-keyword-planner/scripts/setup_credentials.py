#!/usr/bin/env python3
"""
Google Ads API — OAuth2 Authentication Script
Helps generate a fresh refresh_token and saves a complete google-ads.yaml file.
"""
import argparse
import os
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Missing library. Run: pip3 install google-auth-oauthlib", file=sys.stderr)
    sys.exit(1)

# Google Ads API Scope
SCOPES = ["https://www.googleapis.com/auth/adwords"]

# Default paths
DEFAULT_CREDENTIALS_DIR = os.path.expanduser("~/Documents/credentials")
DEFAULT_YAML_PATH = os.path.join(DEFAULT_CREDENTIALS_DIR, "google-ads.yaml")


def get_client_credentials(client_secrets_path: str):
    """Fallback interactive prompt if client secrets JSON isn't provided."""
    import json
    
    if os.path.exists(client_secrets_path):
        with open(client_secrets_path, "r") as f:
            data = json.load(f)
            if "installed" in data:
                return data["installed"]["client_id"], data["installed"]["client_secret"]
            elif "web" in data:
                return data["web"]["client_id"], data["web"]["client_secret"]

    print("\n--- Google Cloud Platform OAuth 2.0 Client ID ---")
    print("Create this in Google Cloud Console -> APIs & Services -> Credentials.")
    print("Choose 'Desktop app' as the application type.")
    
    client_id = input("\nEnter Client ID: ").strip()
    client_secret = input("Enter Client Secret: ").strip()
    
    return client_id, client_secret


def main():
    parser = argparse.ArgumentParser(description="Authenticate Google Ads API")
    parser.add_argument("--client-secrets", default=os.path.join(DEFAULT_CREDENTIALS_DIR, "google_client_secrets.json"),
                        help="Path to GCP downloaded client_secrets.json")
    parser.add_argument("--developer-token", help="Google Ads MCC Developer Token (overrides interactive prompt)")
    parser.add_argument("--login-customer-id", help="MCC ID without dashes (overrides interactive prompt)")
    parser.add_argument("--out", default=DEFAULT_YAML_PATH, help=f"Where to save yaml (default: {DEFAULT_YAML_PATH})")
    
    args = parser.parse_args()
    
    # 1. Get Client ID / Secret
    try:
        client_id, client_secret = get_client_credentials(args.client_secrets)
    except Exception as e:
        print(f"Error reading client secrets: {e}", file=sys.stderr)
        client_id, client_secret = get_client_credentials("force_prompt")

    if not client_id or not client_secret:
        print("Client ID and Secret are required.", file=sys.stderr)
        sys.exit(1)

    # 2. Get Developer Token & MCC
    dev_token = args.developer_token
    if not dev_token:
        print("\n--- Google Ads MCC Developer Token ---")
        print("Found in Google Ads UI -> Tools & Settings -> API Center")
        dev_token = input("Enter Developer Token: ").strip()

    mcc_id = args.login_customer_id
    if not mcc_id:
        print("\n--- MCC Login Customer ID ---")
        mcc_id = input("Enter MCC ID (digits only, no dashes): ").strip()
        mcc_id = mcc_id.replace("-", "").replace(" ", "")

    # 3. OAuth Flow
    print("\n--- Generating Refresh Token ---")
    print("A browser window will open. Please log in with the Google Account that has access to the Google Ads MCC.")
    print("If you get an 'Unverified App' warning, click Advanced -> Go to App.")
    
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    # Use a fixed port to avoid weird redirect URI mismatch issues
    credentials = flow.run_local_server(port=8080, access_type="offline", prompt="consent")

    refresh_token = credentials.refresh_token
    if not refresh_token:
        print("\n❌ Failed to get a refresh token. Did you already authorize this app? Try revoking access in Google Account permissions and run this again.", file=sys.stderr)
        sys.exit(1)

    print("\n✅ Authentication successful!")
    
    # 4. Save YAML
    yaml_content = f"""developer_token: {dev_token}
client_id: {client_id}
client_secret: {client_secret}
refresh_token: {refresh_token}
login_customer_id: "{mcc_id}"
use_proto_plus: True
"""

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(yaml_content)

    print(f"\nConfiguration successfully saved to: {args.out}")
    print("\nYou can now use the 'google-ads-keyword-planner' skill.")

if __name__ == "__main__":
    main()
