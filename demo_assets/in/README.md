# Banyan Lantern Technologies (fictional, India)

A software company in Bengaluru written for trying OrgFlow on documents it has never seen: an org chart and four policies and procedures, in English, with amounts written the Indian way ("Rs. 5,00,000/-", "₹1 lakh"). No company of this name turned up in a search on 13 October 2026; every page says it is fictional. It is one of the samples on https://orgflowai.web.app, which open without an account.

Two problems are written in on purpose:
1. Purchases above Rs. 5,00,000/- need "Chief Financial Officer" approval, and the org chart has no Chief Financial Officer.
2. Travel claims "Below ₹25,000" go to the Head of Sales and "Above ₹25,000" to the Head of Sales and the Finance Controller, so exactly ₹25,000 has no approver.

Every other boundary is covered once: Rs. 50,000/-, Rs. 2,00,000/-, Rs. 5,00,000/- and ₹1 lakh each end one level with "up to" and start the next with "above". OrgFlow should flag nothing there.

Handoffs the documents state: Sales → Delivery (signed statement of work), Delivery → IT & Administration (approved purchase requests), IT & Administration → Finance (vendor GST invoices), Sales → Finance (approved travel claims), Human Resources → IT & Administration (new joiner request), Human Resources → Finance (joining details), Delivery → Finance (signed milestone acceptance).

Results: [docs/EVAL.md](../../docs/EVAL.md), "Banyan Lantern Technologies".
