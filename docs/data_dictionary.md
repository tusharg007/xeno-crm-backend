# Data Dictionary

## users
- `user_id`: globally unique user identifier
- `signup_at`: signup timestamp
- `country`, `city`: geo dimensions
- `platform`: android / ios / web
- `device_type`: phone / tablet / desktop
- `app_version`: application version string
- `is_premium`: premium subscription status
- `acquisition_channel`: acquisition source
- `persona`: behavioral persona

## sessions
- `session_id`: session identifier
- `user_id`: user who started the session
- `started_at`, `ended_at`: session boundaries
- `session_minutes`: session duration

## messages
- `message_id`, `event_id`: event identifiers
- `sender_user_id`, `receiver_user_id`: messaging relationship
- `created_at`, `delivered_at`, `opened_at`, `clicked_at`: event lifecycle
- `message_type`: text / image / video / audio
- `is_spam`: synthetic spam label

## notifications
- `notification_id`
- `notification_type`
- `sent_at`, `opened_at`

## feature_usage
- `feature_name`
- `used_at`
- `event_type`

## friend_requests
- `request_id`
- `created_at`, `accepted_at`
- `risk_score`

## user_reports
- `report_reason`
- `reported_at`
- `severity`

## spam_flags
- `flagged_at`
- `risk_score`

## app_crashes
- `crashed_at`
- `error_type`
- `severity`
