# Kenari Dana Sejahtera (fictional, Indonesia)

A small-business and consumer lender in Jakarta written to test OrgFlow on Indonesian documents: an org chart and three policies (loan approval, late-fee waivers, new customer handover), amounts in rupiah with dots grouping thousands ("Rp 50.000.000") and "juta", and Indonesian boundary words (di bawah, di atas, sampai dengan). No company of this name turned up in a search on 13 October 2026; every page says it is fictional.

Two problems are written in on purpose:
1. Loans above Rp 500.000.000 need Direktur Risiko approval, and the org chart has no Direktur Risiko.
2. Fee waivers "Di bawah Rp 2 juta" go to the Kepala Layanan Nasabah and "Di atas Rp 2 juta" to the Kepala Layanan Nasabah and Kepala Keuangan, so exactly Rp 2,000,000 has no approver.

Rp 50.000.000 and Rp 500.000.000 (sampai dengan, di atas) are covered once; nothing should be flagged there.

Results: [docs/EVAL.md](../../docs/EVAL.md), "Four JAPAC companies".
