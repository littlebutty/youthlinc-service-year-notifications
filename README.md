# trip-facts

Sends a daily AI-generated fun fact about a country — with a photo — to a GroupMe
channel, to get Youthlinc humanitarian trip participants excited and informed before
they depart.

---

## How it works

Once a day (or on a schedule of your choosing), `send_fact.py` reads every `.yaml`
file in the `config/` directory. For each trip that is currently in its active window
it:

1. Asks Claude to generate a fun, culturally rich fact about the destination country
2. Fetches a landscape photo from Unsplash
3. Uploads the photo to GroupMe's image CDN
4. Posts the fact + photo to the group's GroupMe channel via a bot

---

## Prerequisites

- Python 3.11 or newer
- A free [Unsplash developer account](https://unsplash.com/developers)
- A free [Anthropic API account](https://console.anthropic.com)
- A [GroupMe account](https://groupme.com) that is already a member of the target group

---

## Setup

### 1. Install dependencies

```bash
cd trip-facts
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in the three keys (instructions for each are below).

---

## Getting your API keys

### Anthropic (Claude)

1. Go to [console.anthropic.com/keys](https://console.anthropic.com/keys)
2. Click **Create Key**, give it a name, and copy it
3. Paste it as `ANTHROPIC_API_KEY` in `.env`

### Unsplash

1. Go to [unsplash.com/developers](https://unsplash.com/developers) and click
   **Your apps → New Application**
2. Accept the terms, give it a name and description
3. On the app page, copy the **Access Key** (not the Secret Key)
4. Paste it as `UNSPLASH_ACCESS_KEY` in `.env`

> **Note:** Unsplash's free tier allows 50 requests/hour, which is more than enough
> for this use case.

### GroupMe access token

This token allows the script to upload images to GroupMe's image CDN.

1. Log in at [dev.groupme.com](https://dev.groupme.com)
2. Click your name/avatar in the top-right corner
3. Click **Access Token**
4. Copy the token and paste it as `GROUPME_ACCESS_TOKEN` in `.env`

---

## Creating a GroupMe bot

Each trip needs its own GroupMe bot tied to the group's chat.

**You must already be a member of the GroupMe group.**

1. Log in at [dev.groupme.com](https://dev.groupme.com)
2. Click **Bots** in the top nav, then **Create Bot**
3. Fill in the form:
   - **Group** — select the group this bot will post to
   - **Name** — something like `Youthlinc Trip Facts` or `Daily Kenya Fact`
   - **Avatar URL** — optional, but a nice touch (e.g. a Youthlinc logo URL)
   - **Callback URL** — leave blank
4. Click **Submit**
5. On the next screen you will see the **Bot ID** — copy it

Paste the Bot ID into the `groupme_bot_id` field of that trip's config file.

> Repeat this process for each trip/group.

---

## Configuring a trip

Copy `config/example.yaml`, rename it for your trip, and edit the fields:

```yaml
trip_name: "Kenya Summer 2026"
country: "Kenya"
groupme_bot_id: "abc123def456"   # from the GroupMe bot creation step
start_date: "2026-05-01"         # first day facts are sent
trip_date: "2026-06-15"          # departure date — sending stops this day
frequency: "daily"               # "daily" or "weekly" (Saturdays only)
```

You can have as many config files as you have trips — one per file.

---

## Running the script

### Manual run

```bash
source .venv/bin/activate
python send_fact.py
```

### Preview without sending (dry run)

```bash
python send_fact.py --dry-run
```

This generates a fact and fetches an image but does **not** post to GroupMe.
Useful for testing your setup.

### Force-send outside the normal window

```bash
python send_fact.py --force
```

Sends even if today is before `start_date` or after `trip_date`. Good for testing
a live bot.

### Use a different config directory

```bash
python send_fact.py --config-dir /path/to/other/configs
```

---

## Scheduling with cron (macOS / Linux)

To run automatically every morning at 8:00 AM:

```bash
crontab -e
```

Add this line (adjust the paths to match your setup):

```
0 8 * * * /Users/bpack/Development/Youthlinc/trip-facts/.venv/bin/python /Users/bpack/Development/Youthlinc/trip-facts/send_fact.py >> /Users/bpack/Development/Youthlinc/trip-facts/trip-facts.log 2>&1
```

This runs the script at 8 AM every day and appends output to `trip-facts.log`.

> **macOS note:** For cron to work reliably on macOS, grant your terminal app
> **Full Disk Access** in System Settings → Privacy & Security → Full Disk Access.

### Using launchd instead of cron (macOS preferred)

macOS prefers `launchd` over cron. Create the file
`~/Library/LaunchAgents/com.youthlinc.tripfacts.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.youthlinc.tripfacts</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/bpack/Development/Youthlinc/trip-facts/.venv/bin/python</string>
    <string>/Users/bpack/Development/Youthlinc/trip-facts/send_fact.py</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>

  <key>WorkingDirectory</key>
  <string>/Users/bpack/Development/Youthlinc/trip-facts</string>

  <key>StandardOutPath</key>
  <string>/Users/bpack/Development/Youthlinc/trip-facts/trip-facts.log</string>

  <key>StandardErrorPath</key>
  <string>/Users/bpack/Development/Youthlinc/trip-facts/trip-facts.log</string>
</dict>
</plist>
```

Then load it:

```bash
launchctl load ~/Library/LaunchAgents/com.youthlinc.tripfacts.plist
```

To unload / stop:

```bash
launchctl unload ~/Library/LaunchAgents/com.youthlinc.tripfacts.plist
```

---

## Project structure

```
trip-facts/
├── config/
│   ├── example.yaml        ← template — copy for each trip
│   └── kenya_2026.yaml     ← your real trip configs go here
├── send_fact.py            ← main script
├── requirements.txt
├── .env.example            ← copy to .env and fill in keys
├── .env                    ← your real keys (gitignored)
└── README.md
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing environment variables` | Copy `.env.example` → `.env` and fill in all three keys |
| `Unsplash error 401` | Check your `UNSPLASH_ACCESS_KEY` |
| `GroupMe image upload error 401` | Check your `GROUPME_ACCESS_TOKEN` |
| GroupMe post returns non-202 | Verify your `groupme_bot_id` in the config file |
| No configs processed | Confirm `.yaml` files exist in `config/` with all required fields |
| Facts send on wrong days | Double-check `start_date`, `trip_date`, and `frequency` in the config |
