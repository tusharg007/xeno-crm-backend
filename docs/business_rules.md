# Business Rules

1. A user is active on a day if they started at least one session.
2. A delivered message is one where `delivered_at` is present.
3. An opened message is one where `opened_at` is present.
4. A clicked message is one where `clicked_at` is present.
5. Notification open rate is based only on notifications sent in the same period.
6. Retention cohorts are built from first session date, not signup date, to reflect first product activation.
7. Safety anomaly thresholds are intentionally simple for the demo: percentage change against trailing 7-day mean.
8. Revenue attribution is not modeled in the messaging analytics dataset by default; this platform focuses on product and trust analytics.
