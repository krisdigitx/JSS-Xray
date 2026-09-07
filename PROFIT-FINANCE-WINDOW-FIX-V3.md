# TikTok finance reconciliation window fix

This version fixes a case where a TikTok order was updated recently but its Finance transaction was created earlier than the short order polling window.

Previously, both Orders and Finance used `TIKTOK_LOOKBACK_HOURS`. A delivered order such as `576946475585739420` could therefore be returned by the Orders API because its `update_time` changed, while the associated unsettled Finance transaction (including `est_settlement_amount`) fell outside the Finance search window. That left a previously stored `0.00` estimate in the database.

The sync now keeps the short order update window, but derives the Finance search start from the oldest `create_time` among the orders returned in that sync (with a one-day buffer and a 2025-01-01 floor). This lets JSS Xray recover the correct TikTok estimated earnings and overwrite placeholder zero values with a non-zero Finance value.

Profit remains:

`effective TikTok earnings - Amazon purchase cost`

where effective earnings prefer a non-zero estimated settlement amount, then a non-zero settled amount.
