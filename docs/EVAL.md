# OrgFlow evaluation on documents it was not tuned on

Run on 2026-10-05 with Gemini 3.8 Flash (Vertex AI, location global), using `scripts/eval_documents.py`. Real documents were downloaded from the public web and used unchanged.

Origin: **live** = Gemini's first answer passed every check; **repaired** = passed after one correction; **unverified** = still failing, so OrgFlow showed nothing instead of guessing; **fixture** = the NovaGear sample's saved answer.

| Pair | Input | Organization | Opportunities | Workflow | Rules | Gaps found | Requests run |
|---|---|---|---|---|---|---|---|
| NovaGear | sample, English | live, 8.2 s; 4 units, 9 roles | live, 7.1 s | live, 8.3 s | 2 | Director (missing) | 6 (completed ×5, needs human review ×1) |
| NovaGear, scanned | image-only PDFs | live, 8.9 s; 4 units, 9 roles | live, 6.9 s | live, 12.0 s | 2 | Director (missing) | 6 (completed ×5, needs human review ×1) |
| Xiangying Fitness | fictional, Traditional Chinese | live, 9.1 s; 7 units, 11 roles | live, 9.2 s | live, 10.0 s | 3 | 區經理 (missing); amount gap at 100,000 | 6 (completed ×4, needs human review ×2) |
| National Taiwan University | real, Traditional Chinese | live, 13.9 s; 44 units, 3 roles | live, 11.5 s | live, 15.2 s | 4 | 機關首長或其授權人員 (missing) | 9 (completed ×2, needs human review ×7) |
| National Taitung University | real, Traditional Chinese | live, 45.7 s; 82 units, 58 roles | live, 34.8 s | repaired, 25.6 s | 3 | 一級主管 (possible match) | 9 (completed ×2, needs human review ×7) |

## Details

### NovaGear

The demo company (fictional).

Sources: `demo_assets/en/NovaGear_Organization_Chart.pdf` and `demo_assets/en/NovaGear_Purchasing_Policy.pdf`.
- Total time for the three AI stages: 23.6 s
- Test requests came from: Sales
- First request that stopped (amount: reason): 5,001: Role 'Director' is not in the org chart → human review
- Opportunities found: Purchase Requisition and Approval Flow (built); Finance Policy and Threshold Validation; Approved Purchase Procurement Handoff
- Rule `estimated_cost >= 1,000`
  - Policy text: 「USD 1,000 - USD 5,000 Manager approval + Finance validation」
- Rule `estimated_cost > 5,000`
  - Policy text: 「Above USD 5,000 Manager approval + Finance validation + Director approval」
- Amount level up to 1,000: 「Below USD 1,000 Manager approval」
- Amount level 1,000 to 5,000: 「USD 1,000 - USD 5,000 Manager approval + Finance validation」
- Amount level from 5,000: 「Above USD 5,000 Manager approval + Finance validation + Director approval」

### NovaGear, scanned

Same documents rendered as JPEG pages with no text layer.

- Total time for the three AI stages: 36.8 s
- Test requests came from: Sales
- First request that stopped (amount: reason): 5,001: Role 'Director' is not in the org chart → human review
- Opportunities found: Purchase Request Approval and Procurement Handoff (built); Finance Policy and Threshold Validation; Procurement Intake and Order Execution
- Rule `estimated_cost >= 1,000`
  - Policy text: 「USD 1,000 - USD 5,000 Manager approval + Finance validation」
- Rule `estimated_cost > 5,000`
  - Policy text: 「Above USD 5,000 Manager approval + Finance validation + Director approval」
- Amount level up to 1,000: 「Below USD 1,000 Manager approval」
- Amount level 1,000 to 5,000: 「USD 1,000 - USD 5,000 Manager approval + Finance validation」
- Amount level from 5,000: 「Above USD 5,000 Manager approval + Finance validation + Director approval」

### Xiangying Fitness

A made-up gym chain with three planted flaws: an approver missing from the org chart, amounts written in Chinese numerals, and no approval level for exactly NT$100,000.

Sources: `demo_assets/zh/Xiangying_Fitness_Org_Chart.pdf` and `demo_assets/zh/Xiangying_Fitness_Purchasing_Policy.pdf`.
- Total time for the three AI stages: 28.5 s
- Test requests came from: 營運部
- First request that stopped (amount: reason): 100,000: No approval level in the policy covers exactly 100,000 → human review
- Opportunities found: 器材及用品請購與驗收流程 (built); 分店器材損壞回報與請購銜接流程; 採購交貨驗收與請款對帳流程
- Rule `estimated_cost > 20,000`
  - Policy text: 「逾新臺幣二萬元，未達新臺幣十萬元 所屬單位主管及財務經理核准」
- Rule `estimated_cost > 100,000`
  - Policy text: 「逾新臺幣十萬元 所屬單位主管、財務經理及區經理核准後，陳總經理核定」
- Rule `estimated_cost > 100,000`
  - Policy text: 「逾新臺幣十萬元 所屬單位主管、財務經理及區經理核准後，陳總經理核定」
- Amount level up to 20,000: 「新臺幣二萬元以下 所屬單位主管核准」
- Amount level 20,000 to 100,000: 「逾新臺幣二萬元，未達新臺幣十萬元 所屬單位主管及財務經理核准」
- Amount level from 100,000: 「逾新臺幣十萬元 所屬單位主管、財務經理及區經理核准後，陳總經理核定」
- Amount gap at 100,000 (found by code): 「逾新臺幣二萬元，未達新臺幣十萬元 所屬單位主管及財務經理核准」 then 「逾新臺幣十萬元 所屬單位主管、財務經理及區經理核准後，陳總經理核定」

### National Taiwan University

Organization table (vertical text) and purchase request rules.

- Organization: https://ntuinfo.ntu.edu.tw/pdf/p1_2_0_strusys.pdf
- Policy: https://ga.ntu.edu.tw/main_ch/fileRename/fileRename/123/938/1/7/請購作業規範112.1.7修正.pdf
- Total time for the three AI stages: 41.4 s
- Test requests came from: 總務處
- First request that stopped (amount: reason): 100,001: Role '機關首長或其授權人員' is not in the org chart → human review
- Opportunities found: 科研採購審查與核定流轉自動化 (built); 一般採購案件跨處室審查與簽核; 總務處小額請購及統籌經費簽核流程
- Rule `estimated_cost > 100,000`
  - Policy text: 「4.2.2採購金額逾 10 萬元之請購案件流程如下：」
- Rule `estimated_cost > 300,000`
  - Policy text: 「4.2.2.4送主計室審查；院系所未逾 30 萬元免會主計室。」
- Rule `estimated_cost >= 1,000,000`
  - Policy text: 「4.2.2.5.2 100 萬元以上採購案經核定後由採購組辦理後續採購。」
- Rule `estimated_cost < 1,000,000`
  - Policy text: 「4.2.2.5.1 未達 100 萬元之採購案由院系所、研究中心或行政單位自行辦理採購。」
- Amount level up to 100,000: 「4.2.1採購金額 10 萬元以下之請購：」
- Amount level from 100,000: 「4.2.2採購金額逾 10 萬元之請購案件流程如下：」
- Amount level up to 300,000: 「4.2.2.4送主計室審查；院系所未逾 30 萬元免會主計室。」
- Amount level up to 1,000,000: 「4.2.2.5.1 未達 100 萬元之採購案由院系所、研究中心或行政單位自行辦理採購。」
- Amount level from 1,000,000: 「4.2.2.5.2 100 萬元以上採購案經核定後由採購組辦理後續採購。」

### National Taitung University

Organization regulations (18 pages) and procurement rules with amounts in Chinese numerals.

- Organization: https://law.nttu.edu.tw/var/file/70/1070/img/1828/327627930.pdf
- Policy: https://dga.nttu.edu.tw/var/file/8/1008/img/715/738540495.pdf
- Total time for the three AI stages: 110.4 s
- Test requests came from: 師範學院
- First request that stopped (amount: reason): 30,001: Role '一級主管' is not in the org chart → human review
- Opportunities found: 採購申請授權分流與審核流程 (built); 學生會會費代收申請與審核作業; 系所學位學程增設調整審議流程
- Rule `estimated_cost > 30,000`
  - Policy text: 「1. 新臺幣三萬元以下之採購，授權由系所及學院二級中心主管代為決行。」
- Rule `estimated_cost > 50,000`
  - Policy text: 「2. 新臺幣五萬元以下之採購，授權由一級主管代為決行。」
- Rule `estimated_cost > 80,000`
  - Policy text: 「(四)新臺幣八萬元以下之採購，授權由總務長代為決行。」
- Amount level up to 30,000: 「1. 新臺幣三萬元以下之採購，授權由系所及學院二級中心主管代為決行。」
- Amount level up to 50,000: 「2. 新臺幣五萬元以下之採購，授權由一級主管代為決行。」
- Amount level up to 80,000: 「(四)新臺幣八萬元以下之採購，授權由總務長代為決行。」
- Amount level 50,000 to 150,000: 「(二)逾新臺幣五萬元至十五萬元以下之採購，估價時，使用單位得取得一家廠商估價單，總務處至少應取得一家以上廠商之估價單，報支時均得為傳真影本。」
- Amount level from 150,000: 「五、 逾新臺幣十五萬元之採購均依政府採購法等相關法令規定辦理。」
- Checks that failed before the final answer (wf): Rule 'cost_gt_30000' threshold value 30000 does not appear in its source quote: '2. 新臺幣五萬元以下之採購，授權由一級主管代為決行。' (write amounts in full, for ex; Rule 'cost_gt_50000' threshold value 50000 does not appear in its source quote: '(四)新臺幣八萬元以下之採購，授權由總務長代為決行。' (write amounts in full, for exa

