# Gmail/TikTok reconciliation v14

For each Amazon account Gmail sync, JSS Xray now looks up TikTok orders that contain an Amazon order reference but remain unmatched. It searches that account's Gmail by the exact Amazon order ID, parses the Amazon email with the existing parser, and links the TikTok order immediately.

The price embedded in the TikTok seller note is never used as Amazon purchase cost. Gmail remains the authoritative source.
