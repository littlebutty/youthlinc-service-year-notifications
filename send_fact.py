#!/usr/bin/env python3
"""
trip-facts: Daily fun fact sender for Youthlinc humanitarian trips.

Reads trip config files from the config/ directory, checks whether a fact
should be sent today, generates one via Claude, fetches a photo from Unsplash,
and posts everything to the trip's GroupMe channel via a bot.

Usage:
    python send_fact.py              # process all configs
    python send_fact.py --dry-run    # preview without sending
    python send_fact.py --force      # send even if today is outside the window
"""

import argparse
import glob
import os
import sys
from datetime import date

import anthropic
import requests
import yaml
from dotenv import load_dotenv

load_dotenv()

GROUPME_BOT_POST_URL = "https://api.groupme.com/v3/bots/post"
GROUPME_IMAGE_SERVICE_URL = "https://image.groupme.com/pictures"
UNSPLASH_RANDOM_URL = "https://api.unsplash.com/photos/random"

# Topic rotation — Claude picks one at random each day for variety
FACT_TOPICS = [
    "geography or landscape",
    "food and cuisine",
    "cultural customs or traditions",
    "history",
    "daily life and people",
    "wildlife or nature",
    "language or communication",
    "celebrations or festivals",
    "art, music, or storytelling",
    "economy or way of life",
]


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_configs(config_dir: str = "config") -> list[dict]:
    paths = glob.glob(f"{config_dir}/*.yaml") + glob.glob(f"{config_dir}/*.yml")
    configs = []
    for path in paths:
        with open(path) as f:
            config = yaml.safe_load(f)
            config["_file"] = path
            configs.append(config)
    return configs


def validate_config(config: dict) -> list[str]:
    """Return a list of error strings; empty means valid."""
    errors = []
    required = ["trip_name", "country", "groupme_bot_id", "start_date", "trip_date"]
    for field in required:
        if not config.get(field):
            errors.append(f"Missing required field: '{field}'")
    freq = config.get("frequency", "daily").lower()
    if freq not in ("daily", "weekly"):
        errors.append(f"Invalid frequency '{freq}' — must be 'daily' or 'weekly'")
    return errors


# ---------------------------------------------------------------------------
# Scheduling logic
# ---------------------------------------------------------------------------

def should_send_today(config: dict, today: date, force: bool = False) -> tuple[bool, str]:
    """Return (send, reason_string)."""
    if force:
        return True, "forced"

    start = date.fromisoformat(config["start_date"])
    trip = date.fromisoformat(config["trip_date"])

    if today < start:
        return False, f"campaign hasn't started yet (begins {config['start_date']})"
    if today >= trip:
        return False, f"trip has begun — campaign is complete"

    freq = config.get("frequency", "daily").lower()
    if freq == "weekly" and today.weekday() != 5:  # 5 = Saturday
        return False, "weekly schedule — only sends on Saturdays"

    return True, "scheduled"


# ---------------------------------------------------------------------------
# Fun fact generation
# ---------------------------------------------------------------------------

def generate_fun_fact(country: str, trip_name: str, client: anthropic.Anthropic) -> str:
    import random
    topic = random.choice(FACT_TOPICS)

    prompt = (
        f"Generate an engaging fun fact about {country} focused on {topic}. "
        f"This is for young humanitarian volunteers with Youthlinc preparing for their "
        f'upcoming trip there as part of "{trip_name}".\n\n'
        "Requirements:\n"
        "- Genuinely surprising or little-known\n"
        "- Respectful, positive, and culturally sensitive\n"
        "- Appropriate for teenagers and young adults\n"
        "- 2–4 sentences\n"
        "- Start with a relevant emoji\n"
        "- Written as an enthusiastic message that builds excitement\n"
        "- Do NOT include a title, subject line, or opening like 'Fun Fact:'\n"
        "- Do NOT mention the topic category you were given"
    )

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=350,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


# ---------------------------------------------------------------------------
# Image handling
# ---------------------------------------------------------------------------

def fetch_unsplash_image(country: str, access_key: str) -> tuple[bytes | None, str]:
    """Return (image_bytes, content_type) or (None, '')."""
    try:
        resp = requests.get(
            UNSPLASH_RANDOM_URL,
            params={
                "query": country,
                "orientation": "landscape",
                "client_id": access_key,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"    Unsplash error {resp.status_code}: {resp.text[:120]}")
            return None, ""

        data = resp.json()
        image_url = data["urls"]["regular"]
        img_resp = requests.get(image_url, timeout=20)
        if img_resp.status_code == 200:
            content_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
            return img_resp.content, content_type

        print(f"    Image download error {img_resp.status_code}")
        return None, ""

    except Exception as exc:
        print(f"    Failed to fetch Unsplash image: {exc}")
        return None, ""


def upload_image_to_groupme(image_bytes: bytes, content_type: str, access_token: str) -> str | None:
    """Upload image to GroupMe's CDN. Returns the hosted picture_url or None."""
    try:
        resp = requests.post(
            GROUPME_IMAGE_SERVICE_URL,
            headers={
                "X-Access-Token": access_token,
                "Content-Type": content_type,
            },
            data=image_bytes,
            timeout=30,
        )
        if resp.status_code == 200:
            payload = resp.json().get("payload", {})
            return payload.get("picture_url") or payload.get("url")
        print(f"    GroupMe image upload error {resp.status_code}: {resp.text[:120]}")
        return None
    except Exception as exc:
        print(f"    Failed to upload image to GroupMe: {exc}")
        return None


# ---------------------------------------------------------------------------
# GroupMe posting
# ---------------------------------------------------------------------------

def post_to_groupme(bot_id: str, text: str, picture_url: str | None = None) -> bool:
    payload: dict = {"bot_id": bot_id, "text": text}
    if picture_url:
        payload["picture_url"] = picture_url

    try:
        resp = requests.post(GROUPME_BOT_POST_URL, json=payload, timeout=10)
        return resp.status_code == 202
    except Exception as exc:
        print(f"    GroupMe post failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Per-trip processing
# ---------------------------------------------------------------------------

def process_trip(config: dict, dry_run: bool = False) -> bool:
    trip_name = config["trip_name"]
    country = config["country"]
    bot_id = config["groupme_bot_id"]

    anthropic_key = os.environ["ANTHROPIC_API_KEY"]
    unsplash_key = os.environ["UNSPLASH_ACCESS_KEY"]
    groupme_token = os.environ["GROUPME_ACCESS_TOKEN"]

    print(f"  Generating fun fact about {country}...")
    client = anthropic.Anthropic(api_key=anthropic_key)
    fact = generate_fun_fact(country, trip_name, client)
    print(f"  Fact ({len(fact)} chars):\n    {fact[:120]}{'...' if len(fact) > 120 else ''}")

    print("  Fetching Unsplash photo...")
    image_bytes, content_type = fetch_unsplash_image(country, unsplash_key)

    picture_url = None
    if image_bytes:
        if not dry_run:
            print("  Uploading image to GroupMe...")
            picture_url = upload_image_to_groupme(image_bytes, content_type, groupme_token)
            if picture_url:
                print(f"  Image ready: {picture_url}")
            else:
                print("  Image upload failed — sending text only")
        else:
            print("  [dry-run] Skipping image upload")
    else:
        print("  No image retrieved — sending text only")

    if dry_run:
        print(f"  [dry-run] Would post to bot {bot_id}")
        return True

    success = post_to_groupme(bot_id, fact, picture_url)
    if success:
        print(f"  Posted to GroupMe bot {bot_id}")
    else:
        print(f"  GroupMe post failed for bot {bot_id}")
    return success


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Send daily trip fun facts to GroupMe")
    parser.add_argument("--dry-run", action="store_true", help="Generate and preview without sending")
    parser.add_argument("--force", action="store_true", help="Send even if outside the scheduled window")
    parser.add_argument("--config-dir", default="config", help="Path to config directory (default: config)")
    args = parser.parse_args()

    # Check required env vars
    required_env = ["ANTHROPIC_API_KEY", "UNSPLASH_ACCESS_KEY", "GROUPME_ACCESS_TOKEN"]
    missing = [k for k in required_env if not os.getenv(k)]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your keys.")
        sys.exit(1)

    configs = load_configs(args.config_dir)
    if not configs:
        print(f"No .yaml config files found in '{args.config_dir}/'")
        sys.exit(0)

    today = date.today()
    mode = " [DRY RUN]" if args.dry_run else (" [FORCED]" if args.force else "")
    print(f"trip-facts{mode} | {today.isoformat()} | {len(configs)} trip config(s) loaded\n")

    sent = 0
    skipped = 0

    for config in configs:
        trip_name = config.get("trip_name", config["_file"])
        print(f"── {trip_name} ──")

        errors = validate_config(config)
        if errors:
            for err in errors:
                print(f"  CONFIG ERROR: {err}")
            skipped += 1
            continue

        send, reason = should_send_today(config, today, force=args.force)
        if not send:
            print(f"  Skipping: {reason}")
            skipped += 1
            continue

        print(f"  Sending ({reason})...")
        if process_trip(config, dry_run=args.dry_run):
            sent += 1
        else:
            skipped += 1

        print()

    print(f"Done — {sent} sent, {skipped} skipped.")


if __name__ == "__main__":
    main()
