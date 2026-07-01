"""Basic tests for deterministic synthetic data generation."""

from pipelines.generate_synthetic_data import generate_dataset


def test_generate_dataset_is_deterministic_for_same_row_count():
    first = generate_dataset(500)
    second = generate_dataset(500)

    assert first["users"][0]["user_id"] == second["users"][0]["user_id"]
    assert first["users"][0]["country"] == second["users"][0]["country"]
    assert first["messages"][0]["message_id"] == second["messages"][0]["message_id"]


def test_generate_dataset_contains_expected_entities():
    dataset = generate_dataset(500)

    expected_keys = {
        "users",
        "sessions",
        "messages",
        "group_chats",
        "friend_requests",
        "notifications",
        "feature_usage",
        "user_reports",
        "spam_flags",
        "app_crashes",
    }
    assert expected_keys.issubset(dataset.keys())
