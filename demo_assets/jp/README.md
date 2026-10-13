# Hamakaze Seiko (fictional, Japan)

A precision parts maker in Higashiosaka written to test OrgFlow on Japanese documents: an org chart and three rules (purchasing, expenses, order to shipment), amounts in 万円 with Japanese boundary words (未満, を超え, 以上, 以下). No company of this name turned up in a search on 13 October 2026; every page says it is fictional.

Two problems are written in on purpose:
1. Purchases of 500万円 or more need 常務取締役 approval, and the org chart has no 常務取締役.
2. Purchases 「50万円未満」 go to the 製造部長 and those 「50万円を超え」 to the 製造部長 and 経理部長, so exactly 500,000 yen has no approver.

500万円 (未満, 以上) and 10万円 (以下, を超える) are covered once; nothing should be flagged there.

Results: [docs/EVAL.md](../../docs/EVAL.md), "Four JAPAC companies".
