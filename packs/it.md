# Enterprise SaaS Customer Support — Compliance & Conduct Policy Pack

**Document owner:** Global Trust, Security & Compliance Office (GTSCO)
**Applies to:** All Tier 1–Tier 3 Customer Support Engineers, Technical Account Managers, and
outsourced support partners operating on the vendor's customer-facing voice, chat, and
screen-share channels.
**Regulatory basis:** SOC 2 Type II, ISO/IEC 27001:2022, GDPR (Art. 5, 32, 33), CCPA/CPRA,
PCI-DSS v4.0 (cardholder data handling), and the vendor's Master Subscription Agreement (MSA).
**Classification:** Internal — Compliance Controlled. Deviations are auditable events.

This pack governs what a support agent **must disclose**, what an agent must **never say**, and
the **substantive commercial, security, and data-handling facts** an agent may not contradict.
It is consumed by the on-prem Compliance Corrector in two lanes: a deterministic INSTANT lane
(the two machine-readable sections at the bottom) and a grounded RAG-JUDGE lane (the prose
policy sections that follow).

---

## 1. Subscription, Billing & Refund Policy

All commercial commitments made on a support interaction are binding representations and must
match the published rate card and the MSA.

- **Refund window:** New paid subscriptions and one-time overage charges are refundable within
  **30 calendar days** of the charge date. No refunds are issued after 30 days; agents may only
  offer service credits beyond that window.
- **Metered overage:** Storage consumed beyond the plan allotment is billed at **$0.12 per
  additional GB per month**, prorated daily. API overage is billed at **$2.00 per additional
  million calls**.
- **Plan changes:** Upgrades take effect **immediately** with a prorated charge. Downgrades take
  effect **at the start of the next billing cycle** and never trigger a mid-cycle refund.
- **Late payment:** Past-due invoices accrue a late fee of **1.5% per month** (18% APR). Accounts
  are suspended after **30 days** past due and eligible for termination after **60 days**.
- **Annual commitments** are non-cancellable mid-term except where required by law; unused
  prepaid capacity does not roll over.

Agents must never invent, waive, or exceed these figures without a documented approval from
Billing Operations.

## 2. Service Level Agreement (SLA), Uptime & Support Response

- **Uptime commitments:** Business tier is guaranteed **99.9%** monthly uptime. Enterprise tier is
  guaranteed **99.95%** monthly uptime. There is **no** contractual uptime guarantee on Free or
  Trial tiers.
- **Service credits:** If monthly uptime falls below the committed level but stays at or above
  99.0%, the customer is eligible for a **10%** credit of that month's fee. Below 99.0%, the credit
  is **25%**. Below 95.0%, the credit is **50%**. Credits are the sole remedy for SLA breaches and
  must be requested within **30 days** of the incident.
- **Support response targets:** Severity 1 (production down) — first response within **1 hour**,
  24×7. Severity 2 (major impairment) — within **4 hours**, business hours. Severity 3/4 —
  within **1 business day**.
- Agents must never promise a response time, uptime figure, or credit percentage that exceeds
  these contractual values.

## 3. Data Handling, Encryption & Retention

- **Encryption:** Customer data is encrypted at rest with **AES-256** and in transit with
  **TLS 1.3**. Agents must never claim data is unencrypted, nor claim any control that is not in
  the SOC 2 report.
- **Data residency:** Customers may select a storage region — **US, EU, or APAC** — and data does
  not leave the selected region at rest. Agents must not assert that data is stored elsewhere or
  that residency can be changed on a live call (region changes require a signed change request).
- **Retention & deletion:** After a subscription is cancelled, customer data is retained for
  **90 days** in a recoverable state, then **permanently and irreversibly deleted**. Backups are
  purged on the same 90-day cycle.
- **Support ticket hygiene:** Agents must **never** paste customer secrets, passwords, full
  payment card numbers, or bulk PII into ticket bodies, chat logs, or notes. Card data, if ever
  handled, follows PCI-DSS and is entered only in the tokenized payment tool — never spoken or
  typed into free text.
- **Least privilege:** Support may access only the minimum account scope required for the request,
  and all access is logged and reviewable by the customer's admin.

## 4. Identity Verification & Account Access Control

- **Two-factor identity proof:** Before any account, security, or billing change, the agent must
  verify **at least two** identity factors (e.g., registered email + last-4 of the payment method,
  or a valid in-product verification code). Verbal assurance alone is insufficient.
- **MFA / credential resets:** Multi-factor authentication resets require an open ticket **and**
  approval from the customer's designated account owner or the vendor's support manager, and are
  completed within **24 hours** — never instantly on the call.
- **Credentials are never solicited:** Support will **never** ask a customer to reveal their
  password, full MFA/one-time code, or full card number. Verification codes are validated by the
  system, not read aloud to the agent.
- **Audit integrity:** Access logs and audit trails are immutable. No agent may disable, edit, or
  bypass logging for any reason.

## 5. Incident, Outage & Breach Notification

- **Status transparency:** During a confirmed incident the public status page is updated within
  **30 minutes** and every **60 minutes** thereafter until resolution. Agents must not deny an
  incident that is posted, nor claim the platform is immune to outages.
- **Breach notification:** On a confirmed personal-data breach, affected customers are notified
  without undue delay and no later than **72 hours** after the vendor becomes aware, consistent
  with GDPR Art. 33. Agents must not promise "no breach will ever happen" or minimize a confirmed
  event.
- **Root cause:** A written RCA is delivered for every Severity 1 incident within **5 business
  days**.

---

## Required Disclosures

- Inform the customer that the support session may be recorded and monitored for quality and security purposes. | keywords: may be recorded, recorded and monitored
- State that identity verification is required before any account, security, or billing change is made. | keywords: verify your identity, identity verification
- Before any remote-access or screen-share, disclose that the session is logged and the customer may end it at any time. | keywords: session is logged, you can end the session

## Prohibited Phrases

- just give me your password
- share your full credit card number
- send me your mfa code
- we never have outages
- your data is 100% unhackable
- i'll disable the audit log for you
- we don't need your consent
- your data is stored unencrypted
