# OrgFlow evaluation on documents it was not tuned on

Run on 2026-10-05 with Gemini 3.8 Flash (Vertex AI, location global), using `scripts/eval_documents.py`. Real documents were downloaded from the public web and used unchanged.

Each company goes through every stage the web app runs: the organization, the department map (what each department does and hands to the others), the plan (1-3 workflows per department), then every workflow "Build all linked workflows" would build. Cases then run from every start point across departments, at amounts just below, at and above each threshold.

Origin: **live** = Gemini's first answer passed every check; **repaired** = passed after one correction; **unverified** = still failing, so OrgFlow showed nothing instead of guessing; **fixture** = the NovaGear sample's saved answer.

| Company | Input | Organization | Department map | Plan | Workflows built | Problems found | Chains | Cases run |
|---|---|---|---|---|---|---|---|---|
| NovaGear | sample, English, 3 policies | live, 11.8 s; 4 units, 9 roles | live, 13.9 s; 4 departments, 3 handoffs | live, 12.4 s; 5 workflows | 5 of 5 (live ×5) | gap at 10 (discount_percentage) in Sales; Director missing in Operations | Sales → Finance; Operations → Procurement → Finance | 12 (completed ×10, needs human review ×2) |
| NovaGear, scanned | image-only PDFs | live, 10.5 s; 4 units, 9 roles | live, 9.3 s; 4 departments, 3 handoffs | live, 10.8 s; 5 workflows | 5 of 5 (live ×4, repaired ×1) | gap at 10 (discount_percentage) in Sales; Director missing in Operations | Sales → Finance; Operations → Procurement → Finance | 12 (completed ×10, needs human review ×2) |
| Xiangying Fitness | fictional, Traditional Chinese | live, 21.1 s; 6 units, 11 roles | live, 8.2 s; 6 departments, 2 handoffs | live, 14.2 s; 7 workflows | 7 of 7 (live ×7) | 區經理 missing in 台北信義店; gap at 100,000 (estimated_amount) in 台北信義店; 區經理 missing in 新北板橋店; gap at 100,000 (estimated_amount) in 新北板橋店 | 台北信義店 → 採購部; 新北板橋店 → 採購部; 營運部; 財務部; 會員服務部 | 15 (completed ×11, needs human review ×4) |
| National Taiwan University | real, Traditional Chinese | live, 12.7 s; 44 units, 3 roles | live, 12.5 s; 4 departments, 4 handoffs | live, 15.9 s; 7 workflows | 5 of 5 (live ×4, repaired ×1) | 機關首長或其授權人員 missing in 主計室; 機關首長或其授權人員 missing in 主計室 | 研究發展處 → 採購組 → 主計室; 總務處 → 主計室 | 4 (needs human review ×4) |
| National Taitung University | real, Traditional Chinese | live, 40.3 s; 82 units, 47 roles | live, 19.8 s; 10 departments, 0 handoffs | live, 23.0 s; 10 workflows | 10 of 10 (live ×10) | none | 總務處; 學生事務處; 教務處; 研究發展處; 圖書資訊館; 產學營運暨推廣教育處; 秘書室; 運動與健康中心; 主計室; 人事室 | 18 (completed ×18) |

## Details

### NovaGear

The demo company (fictional).

Sources: `demo_assets/en/NovaGear_Organization_Chart.pdf`, `demo_assets/en/NovaGear_Purchasing_Policy.pdf`, `demo_assets/en/NovaGear_Procurement_Payment_Procedures.pdf`, `demo_assets/en/NovaGear_Sales_Discount_Policy.pdf`.
- Total time for every AI stage and build: 85.2 s
- **Sales**: Sales manages customer relationships, prepares quotes, and oversees key customer accounts.
- **Operations**: Operations handles operational purchase requests and approves departmental purchase necessities.
- **Finance**: Finance validates purchase requests, verifies customer credit limits, and processes supplier invoice payments.
- **Procurement**: Procurement selects vendors, requests quotes, and executes and tracks purchase orders.
  - Handoff Sales → Finance: Approved quotes. 「Approved quotes are sent to Finance, which checks the customer's credit limit before the order is confirmed.」
  - Handoff Procurement → Finance: supplier invoice. 「Once the order is placed, Procurement sends the supplier invoice to Finance for payment.」
  - Handoff Operations → Procurement: approved purchase request. 「After all required management and finance approvals are complete, the request is handed to the Procurement Department.」
- Planned in Sales: Customer Quote Discount Approval (policy, hands to Finance): built (live)
- Planned in Operations: Operational Purchase Request (policy, hands to Procurement): built (live)
- Planned in Finance: Customer Credit Check (policy, starts from Sales): built (live)
- Planned in Finance: Supplier Invoice Matching and Payment (policy, starts from Procurement): built (live)
- Planned in Procurement: Vendor Sourcing and Purchase Order Placement (policy, starts from Operations, hands to Finance): built (live)
- Found by code: gap at 10 (discount_percentage) in Sales
- Found by code: Director missing in Operations
- First case that stopped: Customer Quote Discount Approval at 10: Sales, No approval level in the policy covers exactly 10 → human review

### NovaGear, scanned

Same documents rendered as JPEG pages with no text layer.

- Total time for every AI stage and build: 96.4 s
- **Sales**: Sales manages customer relationships, prepares quotes, and oversees key customer accounts.
- **Operations**: Operations handles operational purchase requests and approves departmental purchase needs.
- **Finance**: Finance validates purchase requests, checks customer credit limits, and processes supplier invoice payments.
- **Procurement**: Procurement manages vendor selection, quote requests, and purchase execution.
  - Handoff Sales → Finance: approved quotes. 「Approved quotes are sent to Finance, which checks the customer's credit limit before the order is confirmed.」
  - Handoff Procurement → Finance: supplier invoice. 「Once the order is placed, Procurement sends the supplier invoice to Finance for payment.」
  - Handoff Operations → Procurement: approved purchase request. 「After all required management and finance approvals are complete, the request is handed to the Procurement Department.」
- Planned in Sales: Customer Quote and Discount Approval (policy, hands to Finance): built (live)
- Planned in Operations: Operational Purchase Request Approval (policy, hands to Procurement): built (live)
- Planned in Finance: Customer Credit Check Verification (policy, starts from Sales): built (live)
- Planned in Finance: Supplier Invoice Matching and Payment (policy, starts from Procurement): built (repaired)
- Planned in Procurement: Vendor Quoting and Purchase Execution (policy, starts from Operations, hands to Finance): built (live)
- Found by code: gap at 10 (discount_percentage) in Sales
- Found by code: Director missing in Operations
- First case that stopped: Customer Quote and Discount Approval at 10: Sales, No approval level in the policy covers exactly 10 → human review
- Checks that failed before the final answer (build finance_supplier_payment_processing): Rule 'rule_payment_all' threshold value 0 does not appear in its source quote: 'Up to USD 10,000 Finance Manager approval' (write amounts in

### Xiangying Fitness

A made-up gym chain with three planted flaws: an approver missing from the org chart, amounts written in Chinese numerals, and no approval level for exactly NT$100,000.

Sources: `demo_assets/zh/Xiangying_Fitness_Org_Chart.pdf`, `demo_assets/zh/Xiangying_Fitness_Purchasing_Policy.pdf`.
- Total time for every AI stage and build: 102.5 s
- **營運部**: 負責督導各分店的營運管理、人力排班與整體服務品質。
- **財務部**: 負責預算與支出審核、付款作業、帳務登錄及發票核對。
- **採購部**: 負責器材與用品之詢價、訂購、交貨驗收及供應商管理。
- **會員服務部**: 負責會員服務督導、諮詢接待、會員續約以及客訴處理。
- **台北信義店**: 負責分店日常營運並提出店內所需器材與用品需求。
- **新北板橋店**: 負責分店日常營運並提出店內所需器材與用品需求。
  - Handoff 台北信義店 → 採購部: 核准後之請購案. 「請購案核准後，交由採購部辦理詢價、訂購及交貨驗收，並於驗收完成後通知申請人。」
  - Handoff 新北板橋店 → 採購部: 核准後之請購案. 「請購案核准後，交由採購部辦理詢價、訂購及交貨驗收，並於驗收完成後通知申請人。」
- Planned in 台北信義店: 分店器材與用品請購簽核流程 (policy, hands to 採購部): built (live)
- Planned in 新北板橋店: 分店器材與用品請購簽核流程 (policy, hands to 採購部): built (live)
- Planned in 採購部: 台北信義店請購執行與驗收通知流程 (policy, starts from 台北信義店): built (live)
- Planned in 採購部: 新北板橋店請購執行與驗收通知流程 (policy, starts from 新北板橋店): built (live)
- Planned in 營運部: 分店人力排班與營運督導流程 (org_chart): built (live)
- Planned in 財務部: 付款與發票核對帳務處理流程 (org_chart): built (live)
- Planned in 會員服務部: 會員續約與客訴處理流程 (org_chart): built (live)
- Found by code: 區經理 missing in 台北信義店
- Found by code: gap at 100,000 (estimated_amount) in 台北信義店
- Found by code: 區經理 missing in 新北板橋店
- Found by code: gap at 100,000 (estimated_amount) in 新北板橋店
- First case that stopped: 分店器材與用品請購簽核流程 at 100,000: 台北信義店, No approval level in the policy covers exactly 100,000 → human review

### National Taiwan University

Organization table (vertical text) and purchase request rules.

- Organization: https://ntuinfo.ntu.edu.tw/pdf/p1_2_0_strusys.pdf
- Policy: https://ga.ntu.edu.tw/main_ch/fileRename/fileRename/123/938/1/7/請購作業規範112.1.7修正.pdf
- Total time for every AI stage and build: 112.1 s
- **採購組**: 負責辦理全校各單位財物及勞務採購案之文件審查與擇商後續作業。
- **總務處**: 負責校內各項總務經費管理及請購案之審定與決行。
- **主計室**: 負責各單位採購與請購案件之經費與帳務審核。
- **研究發展處**: 負責審查全校科學技術研究發展採購案件。
  - Handoff 總務處 → 採購組: 請購單. 「自本校帳務系統產生請購單，由單位主管核准送採購組，經總務長核定後，得不經公告程序，逕洽廠商辦理。」
  - Handoff 總務處 → 主計室: 已核定採購案. 「總務處核定後送主計室審核。」
  - Handoff 研究發展處 → 採購組: 科研採購案件. 「4.2.2.2送研發處審查；以國科會經費辦理者免會研發處，但如有疑義仍由研發處認定。 4.2.2.3送採購組審查。」
  - Handoff 採購組 → 主計室: 審查後之科研採購案件. 「4.2.2.3送採購組審查。……4.2.2.4送主計室審查；院系所未逾 30 萬元免會主計室。」
- Planned in 研究發展處: 科研採購案件審查作業 (policy, hands to 採購組): built (repaired)
- Planned in 採購組: 科研採購案件審查作業 (policy, starts from 研究發展處, hands to 主計室): built (live)
- Planned in 採購組: 總務經費請購單審定與擇商作業 (policy, starts from 總務處): not built
- Planned in 總務處: 一般採購案核定作業 (policy, hands to 主計室): built (live)
- Planned in 總務處: 總務處經費請購申請作業 (policy, hands to 採購組): not built
- Planned in 主計室: 一般請購案經費審核作業 (policy, starts from 總務處): built (live)
- Planned in 主計室: 科研採購案件經費審查作業 (policy, starts from 採購組): built (live)
- Found by code: 機關首長或其授權人員 missing in 主計室
- Found by code: 機關首長或其授權人員 missing in 主計室
- First case that stopped: 科研採購案件審查作業 at 99,999: 主計室, Role '機關首長或其授權人員' is not in the org chart → human review
- Checks that failed before the final answer (build rd_review_scientific_procurement): Rule 'rule_non_nstc_funding' value '非國科會經費' does not appear in its source quote: '4.2.2.2送研發處審查；以國科會經費辦理者免會研發處，但如有疑義仍由研發處認定。'

### National Taitung University

Organization regulations (18 pages) and procurement rules with amounts in Chinese numerals.

- Organization: https://law.nttu.edu.tw/var/file/70/1070/img/1828/327627930.pdf
- Policy: https://dga.nttu.edu.tw/var/file/8/1008/img/715/738540495.pdf
- Total time for every AI stage and build: 246.0 s
- **總務處**: 主持學校總務工作及統籌各類採購事宜。
- **學生事務處**: 主持全校學生事務、就業服務、軍訓及校園安全業務。
- **教務處**: 主持全校教務相關工作。
- **研究發展處**: 綜理全校校務發展及學術研究等業務。
- **圖書資訊館**: 主持圖書資訊典藏、推廣及校園網路資訊系統之建置與維護。
- **產學營運暨推廣教育處**: 綜理產學合作營運、推廣教育及創新育成等工作。
- **秘書室**: 承校長之命主持各項秘書與公關事務。
- **運動與健康中心**: 主持全校運動與健康活動相關事務。
- **主計室**: 依法辦理歲計、會計及統計等財務管理事項。
- **人事室**: 依法辦理全校各項人事管理事項。
- Planned in 總務處: 集中採購與營繕專案辦理流程 (policy): built (live)
- Planned in 學生事務處: 學生自治團體選舉辦法核備流程 (org_chart): built (live)
- Planned in 教務處: 教務綜合業務審核流程 (org_chart): built (live)
- Planned in 研究發展處: 校務發展與研究計畫申辦流程 (org_chart): built (live)
- Planned in 圖書資訊館: 校園網路與資訊系統維護申請流程 (org_chart): built (live)
- Planned in 產學營運暨推廣教育處: 產學合作與創新育成申請流程 (org_chart): built (live)
- Planned in 秘書室: 秘書處公文陳核與公關事務處理流程 (org_chart): built (live)
- Planned in 運動與健康中心: 全校運動與健康活動申辦流程 (org_chart): built (live)
- Planned in 主計室: 歲計與會計經費報支審核流程 (org_chart): built (live)
- Planned in 人事室: 教職員人事管理事項申辦流程 (org_chart): built (live)

