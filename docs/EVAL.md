# OrgFlow evaluation on documents it was not tuned on

Run on 2026-10-05 with Gemini 3.8 Flash (Vertex AI, location global), using `scripts/eval_documents.py`. Real documents were downloaded from the public web and used unchanged.

Origin: **live** = Gemini's first answer passed every check; **repaired** = passed after one correction; **unverified** = still failing, so OrgFlow showed nothing instead of guessing; **fixture** = the NovaGear sample's saved answer.

| Pair | Input | Organization | Opportunities | Workflow | Rules | Gaps found | Requests run |
|---|---|---|---|---|---|---|---|
| NovaGear | sample, English | live, 8.2 s; 4 units, 9 roles | live, 6.7 s | live, 6.7 s | 2 | Director (missing) | 6 (completed ×5, needs human review ×1) |
| NovaGear, scanned | image-only PDFs | live, 7.5 s; 4 units, 9 roles | live, 7.3 s | live, 7.0 s | 2 | Director (missing) | 6 (completed ×5, needs human review ×1) |
| National Taiwan University | real, Traditional Chinese | live, 12.8 s; 44 units, 3 roles | live, 11.4 s | live, 9.8 s | 3 | 機關首長或其授權人員 (missing) | 9 (completed ×2, needs human review ×7) |
| National Taitung University | real, Traditional Chinese | live, 47.0 s; 53 units, 25 roles | live, 13.5 s | live, 11.3 s | 4 | none | 9 (completed ×9) |

## Details

### NovaGear

The demo company (fictional).

Sources: the bundled NovaGear PDFs in `demo_assets/en/`.
- Total time for the three AI stages: 21.6 s
- Test requests came from: Sales
- First request that stopped (amount: reason): 5,001: Role 'Director' is not in the org chart → human review
- Opportunities found: Purchase Request Routing and Approval (built); Finance Policy and Amount Validation; Procurement Handoff and Order Follow-up
- Rule `estimated_cost >= 1,000`
  - Policy text: 「USD 1,000 - USD 5,000 Manager approval + Finance validation」
- Rule `estimated_cost > 5,000`
  - Policy text: 「Above USD 5,000 Manager approval + Finance validation + Director approval」

### NovaGear, scanned

Same documents rendered as JPEG pages with no text layer.

- Total time for the three AI stages: 28.0 s
- Test requests came from: Sales
- First request that stopped (amount: reason): 5,001: Role 'Director' is not in the org chart → human review
- Opportunities found: Operational Purchase Requisition and Multi-Tier Approval (built); Finance Policy and Approval Compliance Validation; Procurement Handoff and Order Execution Tracking
- Rule `estimated_cost >= 1,000`
  - Policy text: 「USD 1,000 - USD 5,000 Manager approval + Finance validation」
- Rule `estimated_cost > 5,000`
  - Policy text: 「Above USD 5,000 Manager approval + Finance validation + Director approval」

### National Taiwan University

Organization table (vertical text) and purchase request rules.

- Organization: https://ntuinfo.ntu.edu.tw/pdf/p1_2_0_strusys.pdf
- Policy: https://ga.ntu.edu.tw/main_ch/fileRename/fileRename/123/938/1/7/請購作業規範112.1.7修正.pdf
- Total time for the three AI stages: 34.9 s
- Test requests came from: 總務處
- First request that stopped (amount: reason): 100,001: Role '機關首長或其授權人員' is not in the org chart → human review
- Opportunities found: 科研採購審查與核定作業 (built); 一般採購送審與決行審核作業; 總務處統籌款採購簽核作業
- Rule `estimated_cost > 100,000`
  - Policy text: 「4.2.2採購金額逾 10 萬元之請購案件流程如下：」
- Rule `estimated_cost > 300,000`
  - Policy text: 「4.2.2.4送主計室審查；院系所未逾 30 萬元免會主計室。」
- Rule `estimated_cost >= 1,000,000`
  - Policy text: 「4.2.2.5.2 100 萬元以上採購案經核定後由採購組辦理後續採購。」

### National Taitung University

Organization regulations (18 pages) and procurement rules with amounts in Chinese numerals.

- Organization: https://law.nttu.edu.tw/var/file/70/1070/img/1828/327627930.pdf
- Policy: https://dga.nttu.edu.tw/var/file/8/1008/img/715/738540495.pdf
- Total time for the three AI stages: 75.7 s
- Test requests came from: 師範學院
- Opportunities found: 校內採購分級簽核與轉送總務處流程 (built); 學生會費代收跨單位協同作業; 採購違規案件講習通知與扣款查核作業
- Rule `estimated_cost <= 30,000`
  - Policy text: 「1. 新臺幣三萬元以下之採購，授權由系所及學院二級中心主管代為決行。」
- Rule `estimated_cost <= 50,000`
  - Policy text: 「2. 新臺幣五萬元以下之採購，授權由一級主管代為決行。」
- Rule `estimated_cost <= 80,000`
  - Policy text: 「(四)新臺幣八萬元以下之採購，授權由總務長代為決行。」
- Rule `estimated_cost > 80,000`
  - Policy text: 「(四)新臺幣八萬元以下之採購，授權由總務長代為決行。」

