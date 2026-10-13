# Nurisol Market (fictional, Korea)

An online household goods shop in Seoul written to test OrgFlow on Korean documents: an org chart and three rules (purchase approval, refunds, promotions), amounts in 만원 with Korean boundary words (미만, 초과, 이하). No company of this name turned up in a search on 13 October 2026; every page says it is fictional.

Two problems are written in on purpose:
1. Purchases 「5,000만원 초과」 need 부사장 approval, and the org chart has no 부사장.
2. Refunds 「30만원 미만」 go to the 고객지원팀장 and 「30만원 초과」 to the 고객지원팀장 and 재무팀장, so exactly 300,000 won has no approver.

1,000만원 and 5,000만원 (이하, 초과) are covered once; nothing should be flagged there.

Results: [docs/EVAL.md](../../docs/EVAL.md), "Four JAPAC companies".
