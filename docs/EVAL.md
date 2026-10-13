# OrgFlow evaluation on documents it was not tuned on

Run on 2026-10-05 with Gemini 3.8 Flash (Vertex AI, location global), using `scripts/eval_documents.py`. Real documents were downloaded from the public web and used unchanged.

Each company goes through every stage the web app runs: the organization, the department map (what each department does and hands to the others), the plan (1-3 workflows per department), then every workflow "Build all linked workflows" would build. Cases then run from every start point across departments, at amounts just below, at and above each threshold.

Origin: **live** = Gemini's first answer passed every check; **repaired** = passed after one correction; **unverified** = still failing, so OrgFlow showed nothing instead of guessing; **fixture** = the NovaGear sample's saved answer.

| Company | Input | Organization | Department map | Plan | Workflows built | Problems found | Chains | Cases run |
|---|---|---|---|---|---|---|---|---|
| NovaGear | sample, English, 3 policies | live, 81.3 s; 4 units, 9 roles | live, 10.7 s; 4 departments, 3 handoffs | live, 14.1 s; 6 workflows | 4 of 5 (live ×4, unverified ×1) | gap at 10 (discount_percentage) in Sales; Director missing in Finance | Sales → Finance; Operations; Finance | 13 (completed ×11, needs human review ×2) |
| NovaGear, scanned | image-only PDFs | live, 11.6 s; 4 units, 9 roles | live, 12.5 s; 4 departments, 3 handoffs | live, 11.9 s; 5 workflows | 5 of 5 (live ×5) | gap at 10 (discount_percentage) in Sales; Director missing in Operations | Sales → Finance; Operations → Procurement → Finance | 12 (completed ×10, needs human review ×2) |
| Xiangying Fitness | fictional, Traditional Chinese | live, 27.0 s; 6 units, 11 roles | live, 17.3 s; 6 departments, 2 handoffs | live, 37.7 s; 7 workflows | 7 of 7 (live ×7) | 區經理 missing in 台北信義店; gap at 100,000 (estimated_amount) in 台北信義店; 區經理 missing in 新北板橋店; gap at 100,000 (estimated_amount) in 新北板橋店 | 台北信義店 → 採購部; 新北板橋店 → 採購部; 營運部; 財務部; 會員服務部 | 15 (completed ×11, needs human review ×4) |
| National Taiwan University | real, Traditional Chinese | live, 22.8 s; 35 units, 3 roles | live, 36.5 s; 4 departments, 4 handoffs | live, 16.6 s; 7 workflows | 5 of 5 (live ×4, repaired ×1) | none | 總務處 → 採購組 → 主計室; 採購組 → 研究發展處 | 6 (completed ×5, needs human review ×1) |
| National Taitung University | real, Traditional Chinese | unverified, 90.0 s | not reached | not reached | - | none | - | - |
| National Changhua University of Education | real, Traditional Chinese | live, 51.7 s; 30 units, 37 roles | live, 20.8 s; 10 departments, 2 handoffs | live, 37.5 s; 13 workflows | 11 of 11 (live ×11) | unclear at 1,500,000 (budget_amount) in 總務處; 國際合作交流委員會 to confirm in 國際暨兩岸事務處 | 總務處; 總務處 → 主計室; 研究發展處; 環境保護暨安全衛生中心; 教務處; 學生事務處; 國際暨兩岸事務處; 圖書與資訊處; 進修學院; 秘書室 | 15 (completed ×13, needs human review ×2) |

## Details

### NovaGear

The demo company (fictional).

Sources: `demo_assets/en/NovaGear_Organization_Chart.pdf`, `demo_assets/en/NovaGear_Purchasing_Policy.pdf`, `demo_assets/en/NovaGear_Procurement_Payment_Procedures.pdf`, `demo_assets/en/NovaGear_Sales_Discount_Policy.pdf`.
- Total time for every AI stage and build: 280.4 s
- **Sales**: Sales manages customer relationships, prepares quotes, and leads customer accounts.
- **Operations**: Operations oversees operational purchase needs and departmental business necessity.
- **Finance**: Finance validates purchase requests, checks customer credit limits, and processes supplier invoice payments.
- **Procurement**: Procurement sources vendor quotes, selects vendors, and issues purchase orders.
  - Handoff Finance → Procurement: approved purchase request. 「After all required management and finance approvals are complete, the request is handed to the Procurement Department.」
  - Handoff Procurement → Finance: supplier invoice. 「Once the order is placed, Procurement sends the supplier invoice to Finance for payment.」
  - Handoff Sales → Finance: approved quotes. 「Approved quotes are sent to Finance, which checks the customer's credit limit before the order is confirmed.」
- Planned in Sales: Sales Discount Approval (policy, hands to Finance): built (live)
- Planned in Operations: Operational Purchase Request Submission (org_chart): built (live)
- Planned in Finance: Purchase Request Approval and Validation (policy, hands to Procurement): built (live)
- Planned in Finance: Supplier Invoice Matching and Payment (policy, starts from Procurement): not built
- Planned in Finance: Customer Credit Limit Verification (policy, starts from Sales): built (live)
- Planned in Procurement: Vendor Sourcing and Purchase Order Execution (policy, starts from Finance, hands to Finance): not built (unverified)
- Found by code: gap at 10 (discount_percentage) in Sales
- Found by code: Director missing in Finance
- First case that stopped: Sales Discount Approval at 10: Sales, No approval level in the policy covers exactly 10 → human review
- Checks that failed before the final answer (build procurement_sourcing_and_ordering): timed out after 90s

### NovaGear, scanned

Same documents rendered as JPEG pages with no text layer.

- Total time for every AI stage and build: 306.6 s
- **Sales**: Sales manages customer relationships, prepares quotes, and leads key accounts.
- **Operations**: Operations handles operational purchase requests and approves departmental purchasing needs.
- **Finance**: Finance validates purchase requests, checks customer credit limits, and processes supplier payments.
- **Procurement**: Procurement manages vendor selection, quote requests, and purchase order execution.
  - Handoff Procurement → Finance: supplier invoice. 「Once the order is placed, Procurement sends the supplier invoice to Finance for payment.」
  - Handoff Sales → Finance: approved quotes. 「Approved quotes are sent to Finance, which checks the customer's credit limit before the order is confirmed.」
  - Handoff Operations → Procurement: approved purchase request. 「After all required management and finance approvals are complete, the request is handed to the Procurement Department.」
- Planned in Sales: Customer Quote Discount Approval (policy, hands to Finance): built (live)
- Planned in Operations: Operational Purchase Request Approval (policy, hands to Procurement): built (live)
- Planned in Finance: Supplier Payment Processing and Approval (policy, starts from Procurement): built (live)
- Planned in Finance: Customer Credit Limit Verification (policy, starts from Sales): built (live)
- Planned in Procurement: Vendor Sourcing and Order Execution (policy, starts from Operations, hands to Finance): built (live)
- Found by code: gap at 10 (discount_percentage) in Sales
- Found by code: Director missing in Operations
- First case that stopped: Sales Discount Policy at 10: Sales, No approval level in the policy covers exactly 10 → human review

### Xiangying Fitness

A made-up gym chain with three planted flaws: an approver missing from the org chart, amounts written in Chinese numerals, and no approval level for exactly NT$100,000.

Sources: `demo_assets/zh/Xiangying_Fitness_Org_Chart.pdf`, `demo_assets/zh/Xiangying_Fitness_Purchasing_Policy.pdf`.
- Total time for every AI stage and build: 197.7 s
- **營運部**: 負責督導各分店日常營運、人力排班與服務品質。
- **財務部**: 負責審核預算與支出，以及辦理付款與會計帳務。
- **採購部**: 負責督導採購作業、供應商管理及執行詢價、訂購與驗收。
- **會員服務部**: 負責處理會員諮詢、續約與客訴服務。
- **台北信義店**: 負責管理分店日常營運並提出器材與用品需求。
- **新北板橋店**: 負責管理分店日常營運並提出器材與用品需求。
  - Handoff 台北信義店 → 採購部: 核准後之請購案. 「請購案核准後，交由採購部辦理詢價、訂購及交貨驗收，並於驗收完成後通知申請人。」
  - Handoff 新北板橋店 → 採購部: 核准後之請購案. 「請購案核准後，交由採購部辦理詢價、訂購及交貨驗收，並於驗收完成後通知申請人。」
- Planned in 台北信義店: 信義店器材及用品請購簽核 (policy, hands to 採購部): built (live)
- Planned in 新北板橋店: 板橋店器材及用品請購簽核 (policy, hands to 採購部): built (live)
- Planned in 採購部: 信義店採購執行與驗收 (policy, starts from 台北信義店): built (live)
- Planned in 採購部: 板橋店採購執行與驗收 (policy, starts from 新北板橋店): built (live)
- Planned in 營運部: 分店營運排班與服務督導 (org_chart): built (live)
- Planned in 財務部: 付款與帳務登錄核對 (org_chart): built (live)
- Planned in 會員服務部: 客訴與會員服務處理 (org_chart): built (live)
- Found by code: 區經理 missing in 台北信義店
- Found by code: gap at 100,000 (estimated_amount) in 台北信義店
- Found by code: 區經理 missing in 新北板橋店
- Found by code: gap at 100,000 (estimated_amount) in 新北板橋店
- First case that stopped: 器材及用品採購作業 at 100,000: 台北信義店, No approval level in the policy covers exactly 100,000 → human review

### National Taiwan University

Organization table (vertical text) and purchase request rules.

- Organization: https://ntuinfo.ntu.edu.tw/pdf/p1_2_0_strusys.pdf
- Policy: https://ga.ntu.edu.tw/main_ch/fileRename/fileRename/123/938/1/7/請購作業規範112.1.7修正.pdf
- Total time for every AI stage and build: 193.5 s
- **採購組**: 負責全校各類財物及勞務採購案件之請購文件審查、招標方式確認及後續擇商或採購辦理作業。
- **總務處**: 負責綜理校內各項總務經費管理及請購案件之核定作業。
- **主計室**: 負責審核學校各單位及請購案件之經費與採購案支出程序。
- **研究發展處**: 負責審查校內科研採購案件及認定科研採購經費相關疑義事項。
  - Handoff 總務處 → 採購組: 請購單. 「自本校帳務系統產生請購單，由單位主管核准送採購組，經總務長核定後，得不經公告程序，逕洽廠商辦理。」
  - Handoff 採購組 → 主計室: 經總務處核定之請購案. 「總務處核定後送主計室審核。」
  - Handoff 採購組 → 研究發展處: 逾10萬元科研採購案件請購文件. 「送研發處審查；以國科會經費辦理者免會研發處，但如有疑義仍由研發處認定。」
  - Handoff 採購組 → 主計室: 科研採購案件. 「送主計室審查；院系所未逾 30 萬元免會主計室。」
- Planned in 總務處: 總務處請購單核准與送件作業 (policy, hands to 採購組): built (live)
- Planned in 採購組: 一般請購案件審查與送審作業 (policy, starts from 總務處, hands to 主計室): built (live)
- Planned in 採購組: 科研採購案件送研發處審查作業 (policy, hands to 研究發展處): built (repaired)
- Planned in 採購組: 科研採購案件送主計室審查作業 (policy, hands to 主計室): not built
- Planned in 主計室: 一般請購案預算審核作業 (policy, starts from 採購組): built (live)
- Planned in 主計室: 科研採購案審查作業 (policy, starts from 採購組): not built
- Planned in 研究發展處: 科研採購案件審查作業 (policy, starts from 採購組): built (live)
- First case that stopped: 科研採購案件送研發處審查作業 at 100,001: 採購組, The org chart names no head for '採購組' → human review
- Checks that failed before the final answer (build procurement_send_research_procurement): Rule 'rule_not_nstc_funding' value '非國科會經費' does not appear in its source quote: '4.2.2.2送研發處審查；以國科會經費辦理者免會研發處，但如有疑義仍由研發處認定。'

### National Taitung University

Organization regulations (18 pages) and procurement rules with amounts in Chinese numerals.

- Organization: https://law.nttu.edu.tw/var/file/70/1070/img/1828/327627930.pdf
- Policy: https://dga.nttu.edu.tw/var/file/8/1008/img/715/738540495.pdf
- Total time for every AI stage and build: 90.9 s
- Checks that failed before the final answer (org): timed out after 90s

### National Changhua University of Education

Organization regulations in force from 1 August 2026 (some characters stored as look-alike code points) and research purchasing rules amended 2 April 2025, whose top approval level reads 「逾新臺幣150萬元以上」: "over" and "at or above" at once.

**Correction (2026-10-12):** the finding at 1,500,000 below is a false alarm. The same document's table on page 8 gives 「150萬元（含）以上」 to the president or an authorized signer, and clause 2(3) says 「達新臺幣150萬元以上」, so exactly NT$1,500,000 has an approver. OrgFlow read clause 4's inconsistent wording but not the table. See [ISSUES.md](ISSUES.md) #21.

- Organization: https://personnelweb.ncue.edu.tw/var/file/1/1001/attach/73/pta_24345_9114766_02987.pdf
- Policy: https://generalweb.ncue.edu.tw/var/file/4/1004/img/131/838494933.pdf
- Total time for every AI stage and build: 310.5 s
- **總務處**: 掌理出納、保管、事務、營繕、校園安全、採購及其他總務事項。
- **研究發展處**: 掌理研究發展與企劃、計畫業務、智財與技術管理、培育新創企業及科研採購計畫審查等事項。
- **主計室**: 依法掌理歲計、會計、統計事項以及採購案件之監辦與經費審核製票。
- **環境保護暨安全衛生中心**: 掌理學校安全衛生管理及特定危險性機械設備之安全衛生審查事項。
- **教務處**: 掌理註冊、課務、招生、教學資源、數位學習發展、教學發展、大學社會責任及其他教務事項。
- **學生事務處**: 掌理生活輔導、課外活動指導、衛生保健、學生安全、原住民族學生資源、職涯發展及其他輔導事項。
- **國際暨兩岸事務處**: 掌理國際學生招生與事務、兩岸學術文化交流合作及語言教育推展等事項。
- **圖書與資訊處**: 掌理教學研究資料之蒐集支援、全校資訊系統統籌規劃及資訊網路設備服務。
- **進修學院**: 掌理各類在職進修、推廣教育之規劃及其他相關教學研究事項。
- **秘書室**: 掌理文書、議事、管制考核、性別平等教育及公共關係等事項。
  - Handoff 總務處 → 主計室: 採購契約. 「採購契約經用印後分送廠商、請購單位、主計室及採購單位保管備用。」
  - Handoff 主計室 → 總務處: 傳票憑證. 「主計室審核→校長或授權代簽人核准→主計室製票→總務處出納組（撥款）。」
- Planned in 總務處: 科研採購分層核定與招標作業 (policy): built (live)
- Planned in 總務處: 採購契約用印與分送 (policy, hands to 主計室): built (live)
- Planned in 總務處: 採購經費核銷出納撥款 (policy, starts from 主計室): not built
- Planned in 主計室: 採購契約歸檔與監辦列管 (policy, starts from 總務處): built (live)
- Planned in 主計室: 經費核銷審核與製票 (policy, hands to 總務處): not built
- Planned in 研究發展處: 科研採購計畫資格審查 (policy): built (live)
- Planned in 環境保護暨安全衛生中心: 危險性機械設備安全審查 (policy): built (live)
- Planned in 教務處: 學生畢業資格審查 (org_chart): built (live)
- Planned in 學生事務處: 學生生活輔導與救助申請審查 (org_chart): built (live)
- Planned in 國際暨兩岸事務處: 學生出國進修交換申請審查 (org_chart): built (live)
- Planned in 圖書與資訊處: 校園資訊系統需求與設備諮詢申請 (org_chart): built (live)
- Planned in 進修學院: 推廣教育課程開班申請審查 (org_chart): built (live)
- Planned in 秘書室: 校務會議提案與管制考核列管 (org_chart): built (live)
- Found by code: unclear at 1,500,000 (budget_amount) in 總務處
- Found by code: 國際合作交流委員會 to confirm in 國際暨兩岸事務處
- First case that stopped: 科研採購分層核定與招標作業 at 1,500,000: 總務處, The policy's wording doesn't say which approval level covers exactly 1,500,000 → human review

### Larkspur Bay Logistics (added 13 October 2026)

A fictional freight company in Singapore, written for this test: an org chart and three policies (purchasing, customer credit notes, shipment handover) in English and Singapore dollars, with two problems planted. The PDFs and the answer key are in [demo_assets/sg](../demo_assets/sg). Read live with Gemini 3.8 Flash on the local app.

- First run: 5 departments and all 5 handoffs the documents state; 10 of 10 planned workflows built, 82 s from upload; found the Regional Director the org chart doesn't have. Missed exactly SGD 1,000: the boundary reader didn't know "SGD" ([ISSUES.md](ISSUES.md) #23).
- After the fix, three complete runs (130 to 155 s from upload to every workflow built, 8 of 8 each time): all three found both planted problems, shown as "The policy requires Regional Director approval, and the org chart has no Regional Director" and "No approval level covers exactly SGD 1,000". One more attempt stopped when Gemini took over 90 s on the department map; the page said so and a second try went through.

### Banyan Lantern Technologies (added 13 October 2026)

A fictional software company in Bengaluru, written for this test and offered on the upload page: an org chart and four policies and procedures (purchases, travel claims, employee onboarding, client project handover) in English, with amounts written the Indian way ("Rs. 5,00,000/-", "₹1 lakh"), and two problems planted. The PDFs and the answer key are in [demo_assets/in](../demo_assets/in). Read live with Gemini 3.8 Flash on the local app.

- First, `normalize_amounts` read "Rs. 5,00,000/-" as 5 and 0 and "₹2 lakh" as 2 ([ISSUES.md](ISSUES.md) #25). After the fix:
- Run 1: 5 departments and all 7 handoffs; 12 of 12 workflows built; found the Chief Financial Officer the org chart doesn't have; nothing flagged at Rs. 50,000/-, 2,00,000/-, 5,00,000/- or ₹1 lakh. It missed exactly ₹25,000 because the travel claims were written for Delivery, which then had four processes, one more than a department's three: the claims workflow was left out. The documents now give travel claims to Sales.
- Run 2: both planted problems found and no false alarm; 11 of 13 built, because one workflow's Gemini call ran past 90 s and the workflow handed to it waited. The same button builds the rest.
- Run 3: 5 departments, 8 handoffs, 12 of 12 workflows built in 196 s from upload; both planted problems found ("The policy requires Chief Financial Officer approval, and the org chart has no Chief Financial Officer", "No approval level covers exactly INR 25,000"), nothing else flagged. Cases: Rs. 30,000 and Rs. 3,00,000 complete (shown as INR 3,00,000), Rs. 6,00,000 stops at the missing CFO; claims of ₹10,000 and ₹1,50,000 complete, exactly ₹25,000 stops.

