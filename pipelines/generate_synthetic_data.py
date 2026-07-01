"""Generate synthetic product analytics data for a global messaging platform."""

from __future__ import annotations

import argparse
import csv
import random
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from config import resolve_path, settings


COUNTRIES = {
    "India": ["Delhi", "Mumbai", "Bangalore", "Pune", "Hyderabad"],
    "Brazil": ["Sao Paulo", "Rio de Janeiro", "Brasilia"],
    "Indonesia": ["Jakarta", "Bandung", "Surabaya"],
    "Nigeria": ["Lagos", "Abuja", "Ibadan"],
    "United States": ["New York", "San Francisco", "Austin"],
}
PLATFORMS = ["android", "ios", "web"]
DEVICES = ["phone", "tablet", "desktop"]
FEATURES = ["stories", "channels", "voice_calls", "video_calls", "communities", "stickers"]
REPORT_REASONS = ["spam", "abuse", "misinformation", "harassment", "fake_account"]
NOTIFICATION_TYPES = ["friend_request", "message", "group_invite", "story_alert", "safety_warning"]
MESSAGE_TYPES = ["text", "image", "video", "audio"]


def raw_dir() -> Path:
    path = resolve_path(settings.RAW_DATA_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_csv(file_path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with file_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_users(total_users: int, rng: random.Random) -> list[dict]:
    users = []
    now = datetime.utcnow()
    for index in range(total_users):
        country = rng.choice(list(COUNTRIES.keys()))
        city = rng.choice(COUNTRIES[country])
        signup_days_ago = rng.randint(1, 365)
        signup_at = now - timedelta(days=signup_days_ago, hours=rng.randint(0, 23))
        users.append(
            {
                "user_id": str(uuid.uuid4()),
                "signup_at": signup_at.isoformat(),
                "country": country,
                "city": city,
                "platform": rng.choices(PLATFORMS, weights=[0.6, 0.25, 0.15])[0],
                "device_type": rng.choices(DEVICES, weights=[0.72, 0.08, 0.2])[0],
                "app_version": rng.choice(["5.1.0", "5.2.0", "5.2.1", "5.3.0"]),
                "is_premium": rng.random() < 0.12,
                "acquisition_channel": rng.choice(["organic", "referral", "ads", "creator", "partner"]),
                "persona": rng.choice(["creator", "casual", "power_user", "student", "community_admin"]),
                "age_bucket": rng.choice(["18-24", "25-34", "35-44", "45+"]),
                "index_id": index,
            }
        )
    return users


def build_sessions(users: list[dict], total_rows: int, rng: random.Random) -> list[dict]:
    sessions = []
    now = datetime.utcnow()
    for _ in range(total_rows):
        user = rng.choice(users)
        start = now - timedelta(days=rng.randint(0, 89), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        duration = rng.randint(1, 90)
        sessions.append(
            {
                "session_id": str(uuid.uuid4()),
                "user_id": user["user_id"],
                "started_at": start.isoformat(),
                "ended_at": (start + timedelta(minutes=duration)).isoformat(),
                "session_minutes": duration,
                "country": user["country"],
                "city": user["city"],
                "platform": user["platform"],
                "app_version": user["app_version"],
            }
        )
    return sessions


def build_messages(users: list[dict], total_rows: int, rng: random.Random) -> list[dict]:
    messages = []
    now = datetime.utcnow()
    for _ in range(total_rows):
        sender = rng.choice(users)
        receiver = rng.choice(users)
        while receiver["user_id"] == sender["user_id"]:
            receiver = rng.choice(users)
        created_at = now - timedelta(days=rng.randint(0, 89), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        delivered = rng.random() > 0.04
        opened = delivered and rng.random() < 0.67
        clicked = opened and rng.random() < 0.12
        messages.append(
            {
                "event_id": str(uuid.uuid4()),
                "message_id": str(uuid.uuid4()),
                "sender_user_id": sender["user_id"],
                "receiver_user_id": receiver["user_id"],
                "session_id": str(uuid.uuid4()),
                "message_type": rng.choice(MESSAGE_TYPES),
                "created_at": created_at.isoformat(),
                "country": sender["country"],
                "city": sender["city"],
                "platform": sender["platform"],
                "is_spam": rng.random() < 0.02,
                "delivered_at": (created_at + timedelta(seconds=rng.randint(2, 60))).isoformat() if delivered else "",
                "opened_at": (created_at + timedelta(minutes=rng.randint(1, 120))).isoformat() if opened else "",
                "clicked_at": (created_at + timedelta(minutes=rng.randint(2, 240))).isoformat() if clicked else "",
            }
        )
    return messages


def build_group_chats(users: list[dict], total_rows: int, rng: random.Random) -> list[dict]:
    rows = []
    now = datetime.utcnow()
    for _ in range(total_rows):
        creator = rng.choice(users)
        created_at = now - timedelta(days=rng.randint(0, 180))
        rows.append(
            {
                "group_id": str(uuid.uuid4()),
                "creator_user_id": creator["user_id"],
                "created_at": created_at.isoformat(),
                "member_count": rng.randint(3, 256),
                "country": creator["country"],
                "platform": creator["platform"],
                "is_public": rng.random() < 0.35,
                "topic": rng.choice(["sports", "study", "work", "family", "gaming", "creators"]),
            }
        )
    return rows


def build_friend_requests(users: list[dict], total_rows: int, rng: random.Random) -> list[dict]:
    rows = []
    now = datetime.utcnow()
    for _ in range(total_rows):
        sender = rng.choice(users)
        receiver = rng.choice(users)
        while receiver["user_id"] == sender["user_id"]:
            receiver = rng.choice(users)
        created_at = now - timedelta(days=rng.randint(0, 89), hours=rng.randint(0, 23))
        accepted = rng.random() < 0.62
        rows.append(
            {
                "request_id": str(uuid.uuid4()),
                "sender_user_id": sender["user_id"],
                "receiver_user_id": receiver["user_id"],
                "created_at": created_at.isoformat(),
                "accepted_at": (created_at + timedelta(hours=rng.randint(1, 72))).isoformat() if accepted else "",
                "country": sender["country"],
                "platform": sender["platform"],
                "risk_score": round(rng.uniform(0.01, 0.99), 3),
            }
        )
    return rows


def build_notifications(users: list[dict], total_rows: int, rng: random.Random) -> list[dict]:
    rows = []
    now = datetime.utcnow()
    for _ in range(total_rows):
        user = rng.choice(users)
        sent_at = now - timedelta(days=rng.randint(0, 89), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        opened = rng.random() < 0.39
        rows.append(
            {
                "notification_id": str(uuid.uuid4()),
                "user_id": user["user_id"],
                "notification_type": rng.choice(NOTIFICATION_TYPES),
                "sent_at": sent_at.isoformat(),
                "opened_at": (sent_at + timedelta(minutes=rng.randint(1, 240))).isoformat() if opened else "",
                "country": user["country"],
                "platform": user["platform"],
                "session_id": str(uuid.uuid4()),
            }
        )
    return rows


def build_feature_usage(users: list[dict], total_rows: int, rng: random.Random) -> list[dict]:
    rows = []
    now = datetime.utcnow()
    for _ in range(total_rows):
        user = rng.choice(users)
        used_at = now - timedelta(days=rng.randint(0, 89), hours=rng.randint(0, 23))
        rows.append(
            {
                "event_id": str(uuid.uuid4()),
                "user_id": user["user_id"],
                "feature_name": rng.choice(FEATURES),
                "used_at": used_at.isoformat(),
                "country": user["country"],
                "platform": user["platform"],
                "session_id": str(uuid.uuid4()),
                "event_type": "feature_use",
            }
        )
    return rows


def build_user_reports(messages: list[dict], rng: random.Random) -> list[dict]:
    rows = []
    for message in messages:
        if message["is_spam"] or rng.random() < 0.025:
            rows.append(
                {
                    "report_id": str(uuid.uuid4()),
                    "user_id": message["receiver_user_id"],
                    "message_id": message["message_id"],
                    "report_reason": rng.choice(REPORT_REASONS),
                    "reported_at": message["created_at"],
                    "country": message["country"],
                    "platform": message["platform"],
                    "severity": rng.choice(["low", "medium", "high"]),
                }
            )
    return rows


def build_spam_flags(messages: list[dict], rng: random.Random) -> list[dict]:
    rows = []
    for message in messages:
        if message["is_spam"] or rng.random() < 0.015:
            rows.append(
                {
                    "flag_id": str(uuid.uuid4()),
                    "message_id": message["message_id"],
                    "user_id": message["sender_user_id"],
                    "flagged_at": message["created_at"],
                    "risk_score": round(rng.uniform(0.5, 0.99), 3),
                    "country": message["country"],
                    "platform": message["platform"],
                    "is_spam": True,
                }
            )
    return rows


def build_app_crashes(users: list[dict], total_rows: int, rng: random.Random) -> list[dict]:
    rows = []
    now = datetime.utcnow()
    for _ in range(total_rows):
        user = rng.choice(users)
        crashed_at = now - timedelta(days=rng.randint(0, 89), hours=rng.randint(0, 23))
        rows.append(
            {
                "crash_id": str(uuid.uuid4()),
                "user_id": user["user_id"],
                "crashed_at": crashed_at.isoformat(),
                "platform": user["platform"],
                "country": user["country"],
                "city": user["city"],
                "app_version": user["app_version"],
                "error_type": rng.choice(["oom", "network_timeout", "ui_freeze", "decoder_error", "db_lock"]),
                "severity": rng.choice(["minor", "major", "critical"]),
            }
        )
    return rows


def generate_dataset(rows: int) -> dict[str, list[dict]]:
    rng = random.Random(settings.SYNTHETIC_RANDOM_SEED)
    total_users = max(3000, rows // 20)
    users = build_users(total_users, rng)
    dataset = {
        "users": users,
        "sessions": build_sessions(users, max(rows, 12000), rng),
        "messages": build_messages(users, max(rows * 2, 25000), rng),
        "group_chats": build_group_chats(users, max(rows // 15, 2000), rng),
        "friend_requests": build_friend_requests(users, max(rows // 4, 8000), rng),
        "notifications": build_notifications(users, max(rows, 14000), rng),
        "feature_usage": build_feature_usage(users, max(rows * 2, 30000), rng),
        "app_crashes": build_app_crashes(users, max(rows // 12, 1500), rng),
    }
    dataset["user_reports"] = build_user_reports(dataset["messages"], rng)
    dataset["spam_flags"] = build_spam_flags(dataset["messages"], rng)
    return dataset


def main(rows: int) -> None:
    dataset = generate_dataset(rows)
    target_dir = raw_dir()
    write_csv(target_dir / "users.csv", dataset["users"], list(dataset["users"][0].keys()))
    write_csv(target_dir / "sessions.csv", dataset["sessions"], list(dataset["sessions"][0].keys()))
    write_csv(target_dir / "messages.csv", dataset["messages"], list(dataset["messages"][0].keys()))
    write_csv(target_dir / "group_chats.csv", dataset["group_chats"], list(dataset["group_chats"][0].keys()))
    write_csv(target_dir / "friend_requests.csv", dataset["friend_requests"], list(dataset["friend_requests"][0].keys()))
    write_csv(target_dir / "notifications.csv", dataset["notifications"], list(dataset["notifications"][0].keys()))
    write_csv(target_dir / "feature_usage.csv", dataset["feature_usage"], list(dataset["feature_usage"][0].keys()))
    write_csv(target_dir / "user_reports.csv", dataset["user_reports"], list(dataset["user_reports"][0].keys()))
    write_csv(target_dir / "spam_flags.csv", dataset["spam_flags"], list(dataset["spam_flags"][0].keys()))
    write_csv(target_dir / "app_crashes.csv", dataset["app_crashes"], list(dataset["app_crashes"][0].keys()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic messaging product analytics data.")
    parser.add_argument("--rows", type=int, default=settings.DEFAULT_SYNTHETIC_ROWS)
    arguments = parser.parse_args()
    main(arguments.rows)
