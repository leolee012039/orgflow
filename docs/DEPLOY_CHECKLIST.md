# Deploy checklist

Run after every deploy. About ten minutes; only step 6 spends Gemini (one sample case).

```bash
API=https://orgflow-api-623155627308.asia-east1.run.app
WEB=https://aibul-510701.web.app
```

| # | Check | How | Expected |
|---|---|---|---|
| 1 | Settings | `gcloud run services describe orgflow-api --region asia-east1 --format="yaml(spec.template.spec.containers[0].env)"` | `ORGFLOW_REQUIRE_AUTH` is not `'0'`; `ALLOWED_ORIGINS` lists both web addresses; no `ORGFLOW_GEMINI_OFF` unless paused on purpose |
| 2 | Health | `curl -s $API/api/health` | `{"ok":true,...}` |
| 3 | The web app may call the API | `curl -s -o /dev/null -D - -X OPTIONS $API/api/analyze -H "Origin: $WEB" -H "Access-Control-Request-Method: POST"` | `access-control-allow-origin: https://aibul-510701.web.app` |
| 4 | Sign-in is on | From the repository root: `curl -s -o /dev/null -w "%{http_code}\n" -F "org_chart=@demo_assets/zh/Xiangying_Fitness_Org_Chart.pdf;type=application/pdf" -F "policies=@demo_assets/zh/Xiangying_Fitness_Purchasing_Policy.pdf;type=application/pdf" $API/api/analyze` | `401`. Anything else means sign-in is off and that call already reached Gemini: fix it now |
| 4b | Firestore rules, before deploying them | `uv run python scripts/test_firestore_rules.py` (Firebase Rules test API; touches no data) | All cases pass |
| 5 | Abuse cases | `uv run --group dev pytest -q tests/test_abuse.py` (CI runs it on every push) | All pass |
| 6 | What a judge sees | Private window: open the site, try the sample, build all, run one case | Every step completes; built workflows say the sample's reading was saved |
| 7 | Monitoring | Cloud console: Monitoring uptime checks and Billing budgets | Uptime checks green; the budget exists |
| 8 | Record the good revision | `gcloud run services describe orgflow-api --region asia-east1 --format="yaml(status.traffic)"`, then `git tag -f last-good && git push -f origin last-good` | The revision with 100% traffic is written in RUNBOOK.md as the rollback target |
