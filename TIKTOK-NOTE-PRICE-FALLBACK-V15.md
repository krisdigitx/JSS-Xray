# TikTok note purchase-cost fallback (v15)

Amazon/Gmail remains the authoritative purchase-cost source.

Fallback is allowed only when all of the following are true:

1. The Gmail sync is connected and its normal message-list call succeeded.
2. JSS Xray performs an exact Gmail lookup for the Amazon order reference.
3. That lookup succeeds with **zero** Gmail candidate messages.
4. The TikTok order is still unmatched after processing all Gmail candidates.
5. The TikTok seller note contains an explicit `Price: £x.xx` value.

The fallback is **not** used for OAuth/refresh-token failures, Gmail API errors, quota failures, timeouts, or targeted lookup exceptions.

Fallback-created Amazon rows use status `tiktok_note_fallback`. If the real Gmail email becomes available later, the normal Gmail sync enriches the same order and replaces the fallback total/status with Gmail-derived data.
