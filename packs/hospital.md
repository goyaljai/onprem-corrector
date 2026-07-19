# Patient Services Representative — Compliance & Communication SOP

**Document ID:** PSR-COMPLIANCE-SOP-v4.2
**Owner:** Office of Corporate Compliance & Health Information Management (HIM)
**Applies to:** All patient-services representatives, scheduling coordinators, and patient-access staff handling inbound/outbound patient calls
**Regulatory basis:** HIPAA Privacy & Security Rules (45 CFR Parts 160 & 164), HITECH breach-notification standards, the No Surprises Act / Good Faith Estimate requirements, EMTALA emergency-access principles, and state patient-rights statutes.

This Standard Operating Procedure governs what a patient-services representative ("the agent") **must** say, **must never** say, and the **specific factual rules** the agent must state accurately on every patient interaction. It is enforced by an automated compliance-corrector service operating in two lanes: a deterministic INSTANT lane (parsing the machine-readable sections below) and an LLM RAG-JUDGE lane (grounding agent statements against the prose policy sections).

---

## Required Disclosures

The agent MUST make each of the following disclosures during any call that reaches the corresponding stage. A disclosure is considered satisfied if the associated keyword phrase appears anywhere in the conversation transcript.

- Identity verification: before discussing any protected health information, the agent must verify the caller using at least two independent identifiers (full legal name, date of birth, and one of: medical record number, last four of SSN, or address on file). | keywords: verify your identity, date of birth
- Call-recording notice: at the start of the interaction the agent must disclose that the call may be monitored or recorded for quality and training purposes. | keywords: this call may be recorded, recorded for quality
- Notice of Privacy Practices: the agent must inform the patient of their right to receive the organization's Notice of Privacy Practices describing how health information is used and disclosed. | keywords: notice of privacy practices, how we use your health information
- Billing estimate nature: any cost figure quoted for a scheduled service must be disclosed as a non-binding good-faith estimate that depends on insurance adjudication. | keywords: good-faith estimate, your out-of-pocket, subject to your insurance

## Prohibited Phrases

The agent must NEVER utter any of the following phrases. These are matched case-insensitively as substrings of the agent's spoken line. Any occurrence is an immediate compliance violation.

- you probably have cancer
- just take double the dose
- we can't help you here
- your condition is hopeless
- i guarantee you'll be cured
- stop taking your prescribed medication
- hipaa doesn't apply here
- that's not my problem

---

## Policy Section 1 — Appointment Scheduling, Cancellation & No-Show Rules

Patients may cancel or reschedule any non-urgent appointment without penalty provided they give at least **24 hours' notice** before the scheduled start time. Cancellations made with less than 24 hours' notice, and failures to attend ("no-shows"), incur a flat **$50 no-show fee** for standard clinic visits and **$100** for procedural/imaging appointments. The no-show fee is **waived automatically after the first occurrence in a rolling 12-month period** and is never charged for pediatric patients under 18. New-patient referrals for non-urgent primary care must be offered an appointment **within 14 calendar days**; behavioral-health intake must be offered **within 10 business days**. Agents may not double-book a provider slot, and may not schedule any patient into a "hold" or "block" slot reserved for clinical overflow without supervisor approval.

## Policy Section 2 — Billing, Financial Responsibility & Good-Faith Estimates

For self-pay or uninsured patients, a written **Good-Faith Estimate** must be provided **within 3 business days** of scheduling a service, per the No Surprises Act. Any verbally quoted cost is an estimate only and remains **subject to insurance adjudication and the patient's out-of-pocket** obligations (deductible, copay, coinsurance). Standard specialist-visit copays collected at scheduling are **$40**; primary-care copays are **$25**. The organization offers interest-free payment plans (**0% APR**) for balances over $200, payable over **up to 12 monthly installments**. Patients whose household income is **at or below 250% of the Federal Poverty Level** qualify for the charity-care / financial-assistance program, which discounts eligible balances by 60–100%. Agents must never demand payment as a condition of scheduling medically necessary care, and must never state that an account has been "sent to collections" unless the account is verified as **more than 120 days delinquent**.

## Policy Section 3 — Protected Health Information (HIPAA) & Data Handling

All disclosures of protected health information (PHI) are governed by the **minimum-necessary standard**: the agent discloses only the information required for the task. PHI may be discussed only after two-identifier verification (see Required Disclosures). A patient may request a copy of their medical records, which must be fulfilled **within 30 calendar days** of a valid written request. Any authorization to release records to a third party is valid for a maximum of **12 months** unless the patient specifies a shorter period, and may be revoked in writing at any time. In the event of a suspected breach of unsecured PHI, the incident must be reported to the Privacy Officer immediately, and affected patients must be notified **no later than 60 days** after discovery. Agents may never send PHI to a personal email address, and may never leave detailed clinical information on an unconfirmed voicemail — only a callback request and a general practice name.

## Policy Section 4 — Clinical Triage & Safety Escalation

Patient-services representatives are **non-clinical staff** and are strictly prohibited from providing medical advice, interpreting test results, diagnosing conditions, or recommending medication changes. When a patient reports a potentially emergent symptom (chest pain, difficulty breathing, stroke signs, suicidal ideation, uncontrolled bleeding), the agent must immediately advise the patient to **call 911 or go to the nearest emergency department**, and must warm-transfer any urgent-but-non-emergent clinical question to the **registered-nurse (RN) triage line**, which maintains a target callback of **within 30 minutes**. Agents must never tell a patient to disregard a symptom, delay emergency care, or alter a prescribed treatment. Documentation of every triage escalation must be entered into the patient record before the call ends.

## Policy Section 5 — Prescription & Refill Handling

Routine (non-controlled) prescription-refill requests are forwarded to the prescribing provider's queue and are processed **within 72 hours (2 business days)**. Agents may confirm receipt of a refill request but may never confirm approval, alter a dose, or advise on medication use — those are clinical determinations. Refills for **controlled substances (DEA Schedule II–IV)** cannot be authorized by phone, require an in-person or telehealth evaluation per the provider's cadence, and are never expedited outside protocol. Agents must direct any question about drug interactions, side effects, or dosing to a pharmacist or the RN triage line, and must never instruct a patient to change how they take a medication.

## Policy Section 6 — Patient Rights, Complaints & Communication Standards

Every patient has the right to be treated with dignity and respect and to file a grievance without fear of retaliation. A formal complaint or grievance must be **acknowledged within 5 business days** and resolved with a written response **within 30 calendar days**. Agents must maintain a professional, empathetic tone at all times, especially with distressed, grieving, or frustrated patients; dismissive, blaming, or hostile language is a documented conduct violation even when no prohibited phrase is used. Language-assistance (interpreter) services must be offered at no cost to any patient with limited English proficiency, and reasonable accommodations must be offered to patients with disabilities.

---

## Enforcement Notes (for the compliance-corrector service)

- **INSTANT lane** parses *Required Disclosures* (keyword anchors) and *Prohibited Phrases* (exact substrings) above.
- **RAG-JUDGE lane** grounds each agent statement against Policy Sections 1–6; any numeric or procedural contradiction (fees, notice windows, timelines, thresholds) is a violation.
- Violation classes: **A** = SOP/policy violation (missing disclosure, prohibited phrase, or factual contradiction of policy); **B** = self-contradiction against the agent's own prior claims; **C** = tone/empathy/conduct violation.
