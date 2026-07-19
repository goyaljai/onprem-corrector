# Retail & Credit Card Banking — Collections & Servicing Compliance SOP

**Applies to:** All customer-facing voice agents (in-house tele-callers and empanelled Direct
Recovery / Collection Agencies) handling credit-card **servicing**, **dunning**, and **collections**
calls.
**Regulatory basis:** RBI *Master Direction – Credit Card and Debit Card – Issuance and Conduct
Directions, 2022*; RBI *Fair Practices Code for Lenders* and *Recovery Agent* guidelines;
*Digital Personal Data Protection Act, 2023 (DPDP)*; *PCI-DSS v4.0*.
**Owner:** Chief Compliance Officer, Cards & Unsecured Lending.
**Review cadence:** Quarterly, or on any regulatory circular.

This SOP is machine-parsed by the on-prem Compliance Corrector. Two sections below
(**Required Disclosures**, **Prohibited Phrases**) are consumed deterministically by the INSTANT
lane. The prose policy sections are grounding context for the RAG-JUDGE lane. Do not reformat the
two machine-readable sections without Compliance sign-off.

---

## Required Disclosures

Each customer interaction MUST contain the following statements. The INSTANT lane treats a
disclosure as satisfied if any listed keyword phrase appears anywhere in the transcript.

- The agent must state that the call is being recorded for quality, training and regulatory purposes before substantive discussion. | keywords: this call is being recorded, call may be recorded, call is recorded for
- The agent must disclose that the purpose of the call is to collect an outstanding amount on the customer's card account. | keywords: collect a debt, outstanding due, attempt to collect a debt
- The agent must inform the customer of the grievance redressal path (nodal / principal nodal officer) available if they are dissatisfied. | keywords: grievance redressal, nodal officer, raise a complaint

## Prohibited Phrases

The following phrases (case-insensitive substring match on the agent's utterance) are absolutely
banned as coercive, deceptive, or in breach of the RBI Recovery Agent conduct norms. Any occurrence
is a hard compliance failure.

- we will send recovery agents to your home
- you will be arrested if you don't pay
- we will inform your employer about your debt
- we will publish your name as a defaulter
- pay immediately or face legal consequences today
- we will seize your property
- you have no choice but to pay right now

---

## Policy 1 — Interest, Finance Charges & Fee Schedule

The **retail finance charge (APR)** on the Standard Consumer Credit Card is **3.60% per month**,
equivalent to **43.2% per annum**, applied on the outstanding balance from the date of transaction
whenever the Total Amount Due is not paid in full by the payment due date. There is **no
interest-free grace period** on any balance once revolving credit is triggered.

The **late payment fee** is tiered by Total Amount Due (TAD): Nil for TAD up to Rs 100; **Rs 500**
for TAD from Rs 100 to Rs 10,000; **Rs 800** for TAD from Rs 10,001 to Rs 25,000; and **Rs 1,300**
for TAD above Rs 25,000. Late fee is levied at most **once per billing cycle**. The **cash
withdrawal fee** is **2.5% of the amount, subject to a minimum of Rs 500**, plus applicable finance
charge from the withdrawal date. GST at **18%** applies to all fees and interest. No fee not listed
in the current Most Important Terms & Conditions (MITC) may be quoted or levied.

## Policy 2 — Billing, Minimum Amount Due & Payment Allocation

The **Minimum Amount Due (MAD)** is **5% of the Total Amount Due, subject to a floor of Rs 200**
(plus any EMI, over-limit amount, and unpaid MAD carried forward). Paying only the MAD keeps the
account current for reporting but does **not** stop finance charges from accruing on the residual
balance. The **payment due date is 18 days** from statement generation. Payments are appropriated
in the RBI-mandated order: taxes and fees first, then interest, then the highest-interest principal
(cash, then retail). Reporting to Credit Information Companies (CIC/CIBIL) as **"overdue" occurs
only after the amount remains unpaid beyond 30 days** past the due date, and any adverse tagging
must be preceded by a **7-day written notice**.

## Policy 3 — Collections Conduct & Contact Rules (RBI Fair Practices)

Collection contact is permitted **only between 08:00 and 19:00 hours** at the customer's location.
Agents must not call before 08:00 or after 19:00, and must not contact the customer on days the
customer has designated as inconvenient without justification. A maximum of **three call attempts
per day** is permitted. Agents must **not use threats, intimidation, obscene language, or contact
third parties** (employer, relatives, neighbours) regarding the debt except to obtain location
information where the customer is unreachable. The customer must always be given the identity of the
lender and the agent's authorization reference. Any physical field visit requires **prior notice**
and must be logged; unannounced visits are prohibited.

## Policy 4 — Disputes, Chargebacks & Provisional Credit

A billing dispute or unauthorised-transaction claim must be accepted whenever the customer reports
it **within 30 days of the statement date**. For a reported unauthorised electronic transaction with
**zero customer negligence reported within 3 working days**, the customer bears **zero liability**
and the bank must credit (shadow-reverse) the disputed amount within **10 working days**. The bank
must **resolve the dispute within 90 days**; failure to resolve within this window entitles the
customer to compensation of **Rs 100 per day** of delay beyond 90 days. Agents must never tell a
customer that a dispute cannot be raised, or demand payment of a genuinely disputed amount while it
is under investigation.

## Policy 5 — Data Handling, Consent & Retention (DPDP 2023 + PCI-DSS)

The agent must **never ask for, nor accept, the full card number, CVV, card PIN, OTP, or
Internet-banking password** — these are never stored and any capture is a reportable security
incident. Only the **last 4 digits** of the card may be used for verification. Personal data may be
processed only for the notified purpose with the customer's consent; the customer may **withdraw
consent** for non-essential processing, and a **data-erasure / grievance request must be actioned
within 30 days** under DPDP. A personal-data breach must be reported to the customer and the Data
Protection Board **without undue delay**. Call recordings and account notes are retained for **7
years** for regulatory audit, then securely purged.

## Policy 6 — Settlement, Waivers & Authorization

A one-time settlement (OTS), waiver of fees, or "no-cost" restructuring may be **offered only from
an approved, system-generated offer** within the tele-caller's sanctioned authority. A frontline
agent's **discretionary fee-waiver authority is capped at Rs 500 per account per cycle**; anything
larger requires a documented supervisor approval reference. Agents must **not promise verbal
settlements, interest freezes, or "closure with nil dues" that are not reflected in the system**, and
every settlement must be confirmed to the customer in writing (SMS/email) with the exact amount and
the reporting status ("settled" vs "closed"). Misrepresenting a "settled" account as "closed" —
which carry different CIC implications — is prohibited.

---

*End of SOP. Machine-readable sections above are authoritative for the INSTANT lane; prose Policies
1–6 are the grounding corpus for the RAG-JUDGE lane.*
