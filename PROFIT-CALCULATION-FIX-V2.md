# TikTok estimated-profit correction v6

Estimated profit is calculated as TikTok estimated earnings minus Amazon purchase cost.

This revision fixes Finance responses that contain a placeholder `0.00` estimate beside a non-zero estimated settlement value, and prevents later syncs from overwriting an already captured non-zero estimate with `0.00`.

Example: TikTok order `576946475585739420`: customer paid £14.98, estimated earnings £12.38, Amazon cost £9.34, estimated profit £3.04.
