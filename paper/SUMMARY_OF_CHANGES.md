# Summary of Changes — resubmission of "Erasure-Compliant, Differentially Private Distinct Counting under Continual Observation"

Prepared for resubmission (PoPETs 2027.2 or later, per the 2026.4 decision). This
document maps every reviewer concern from the 2026.4 reviews (45A–45D) and the
meta-review to the change made. Section numbers refer to the revised paper.

## Meta-review critical weaknesses

**(1) "Sections 3–6 too high-level; insufficient detail on how techniques combine."**
- Merged the two redundant threat-model sections (old §3.2 + old §4) into one precise
  §3.2 with explicit trust semantics, adversary capabilities, the KMS contract, gateway
  metadata visibility, and the guarantees summary.
- Removed a stray implementation/latency paragraph from old §3.3 (it belonged in the
  evaluation) and rewrote the flippancy connection.
- The design sections now state mechanisms concretely: the cross-epoch overlap protocol
  is specified operationally and proven correct (§5.2, Prop. "Cross-Epoch Window
  Correctness"); the tombstone lifecycle now distinguishes eager hot-state update,
  historical replay via compaction, settlement, and purge (§5.3); backend admission is
  tied to a formal property (§5.4).
- Introduction rewritten to set up the problem and the tension (continual observation
  vs. retroactive erasure) with intuition before mechanisms; contributions reformatted
  consistently (fixing the malformed item 5).

**(2) "Lack of formalization of the actual protection (what erasure-compliance means;
what GDPR allows/not)."**
- New **Definition (History-Independent Deletion)** (§3.4): the backend property
  required for the erasure guarantee to hold; text explains why append-only sketches
  fail it, under what conditions KMV/Theta satisfy it, and that exact sets satisfy it
  unconditionally. Backend admission requires the property (§5.4). [Raised by 45A(C)
  and 45A's post-rebuttal note.]
- Existing **Definition (Post-Erasure Release Semantics)** is now connected to the new
  property and to the deletion lifecycle.
- New **Theorem (Deployment-Horizon Guarantee)** (§6) with proof (App. A): the ledger-
  enforced $(ε_tot, δ_tot)$ bound over ALL releases, including deletion-triggered
  re-releases, answering "over how long are the theorems valid" [45D]. Per-release
  propositions are explicitly scoped as per-release.
- **Lemma (RDP Composition Benefit) now has a proof** (App. A) [45D: "I do not see a
  proof for lemma 6"].
- GDPR formal positioning: pseudonymization vs. anonymization under Recital 26 was
  already stated in §2.1; the CCTV case study's contradictory "anonymized at the edge"
  sentence is corrected to pseudonymized with the Recital-26 consequence spelled out
  [45D]. Why tombstones are compatible with Article 17 (transient control-plane
  artifacts; hashed only; purged at settlement; end state equivalent to never-ingested)
  is now argued explicitly in §5.3 [45D: "why is it okay to keep deletion records?"].
- Whether erasure requests themselves are DP-protected is now answered explicitly in
  the threat model (§3.2): request fact/timing are control-plane data visible to the
  aggregation tier; DP protects presence in all released statistics [45A other-comment].

**(3) "Concerns about relevance and scalability of the implementation and case study."**
- New **primary case study: product telemetry** (§9.1), grounded in the exact
  configuration the evaluation measures; **CCTV demoted to a stress variant** (§9.2)
  with its purpose stated (testing the architecture where the identity layer is
  weakest) [45C, and 45C's rebuttal-response question].
- Simulation methodology stated up front for both case studies (synthetic traces from
  the evaluation generators; real pipeline; no fielded-deployment claims); "lessons
  learned" reframed as "design considerations surfaced by the exercise," fixing the
  simulated-vs-real mismatch [45B].
- New scalability honesty in Discussion: exact bitmaps are explicitly scoped to
  single-gateway scale; sketch backends are the intended distributed configuration;
  open engineering questions (serialization, deletion fan-out, distributed accounting)
  named; claims scoped to the measured single-node profile [45A evaluation comment].

## Review 45A main comments

- **(A) Salt rotation vs. sliding windows (W=62 across a boundary):** resolved by the
  formalized overlap protocol in §5.2 — dual-salt bridge table during the first
  W_max−1 days of each epoch, with a correctness proposition (proof sketch inline) and
  erasure coverage of the bridge state. Epoch length must exceed W_max; W_max default
  raised to 62 in the exposition to match the reviewer's scenario.
- **(B) KMV/Theta vs. Roaring confusion:** already-clarified in the submission's §2.3
  and §7.2 ("Backend Clarification"); now additionally tied to the formal admission
  property in §5.4, and the abstract/intro no longer imply a sketch is deployed in the
  evaluation.
- **(C) Erasure never formalized / sketches would not work:** the reviewer is correct,
  and the new Definition (History-Independent Deletion) adopts exactly the
  formalization they suggested (state after deletion ≡ state built from D∖{u});
  KMV/Theta are stated to qualify only under conditions.
- **(D) What the KMS hides and from whom:** new "KMS contract" paragraph in §3.2
  (secrets, interface, who is blinded, consequence of compromise, and the fact DP
  survives salt compromise).
- **Jain et al. lower bound misquote:** corrected throughout to
  Ω(min(T^{1/3}/ε^{2/3}, T)) (was already fixed in the current text; re-verified at
  all three occurrences), and the implication of their matching upper bound (correlated
  noise can beat per-release noise) is now acknowledged in §3.3, Limitations, and
  Future Work.

## Review 45B

- Data-minimization question (sketch vs. bitmap attack surface under gateway
  compromise): new dedicated paragraph in §5.4 quantifying the disclosure difference
  and exposing it as a deployment-time choice.
- Tombstones and Roaring bitmaps defined at first use (tombstones at first mention in
  §3.4; Roaring definition at first mention in §2.3).
- backend.remove on historical backends: now explicit as the "Tombstone Replay" step
  with a settlement condition (§5.3).
- Trivial theorems: per-release results are stated as propositions with one-line
  framing of why they are stated at all (compositional inputs to the horizon theorem);
  duplicate inline proofs removed (proofs live in App. A only).
- Case-study simulation procedure clarified (§9 preamble + per-study methodology).

## Review 45C

- Reorganized §3–6 (merge of threat-model sections; displaced content moved; tighter
  flow); intro expanded with motivation and intuition before mechanisms.
- Implementation/evaluation share of the paper rebalanced by strengthening the formal
  core (new definition, theorem, proposition, proofs) rather than deleting measured
  content.
- CCTV case study replaced as primary by telemetry (see meta-(3)).

## Review 45D

- Trusted vs. honest-but-curious contradiction resolved with precise wording (§3.2).
- GDPR-after-pseudonymization corrected in the case study (§9.2).
- Gateway seeing which edge device sent which key: acknowledged explicitly (§3.2,
  "What the gateway sees"); mixing declared out of scope rather than implied.
- Fig. 2 caption now states the timeline is schematic and not to scale.
- Deletion-record retention justified (§5.3, "Why tombstones are compatible with
  erasure").
- Theorem validity over time: Deployment-Horizon theorem (§6); Lemma proof added.
- §7.1: salt-derivation memoization location was already stated (gateway ingestion
  layer, keyed by epoch, invalidated on rotation); retained.
- "82% is impressive" removed; coverage now described by where it concentrates
  (privacy-critical paths) including a property-based test of history independence.
- §8.2: new "What drives accuracy" paragraph identifying exactly which variables
  affect error (ε, true count; not deletion rate, not window length) and why.
- §8.3: naive baseline justified as a quantification of non-compliance error, not a
  competitive alternative.
- §8.4: churn rate of the storm already stated (≈99% effective churn; 500 users × up
  to 5 flips); retained.
- Editorial: first paragraph rewritten; contributions list reformatted (broken item 5
  fixed); figure captions annotated. [A full grammar pass was applied to the sections
  rewritten above; remaining sections were already edited post-rebuttal.]

## Not changed (and why)

- The evaluation's exact-backend instantiation is retained (with the clarified
  rationale): isolating DP noise from sketch error remains the right evaluation
  design; the minimization trade-off and distributed-scale positioning are now stated
  instead of implied.
- Tree aggregation (correlated noise) remains future work; the revision now
  acknowledges explicitly that it can asymptotically beat per-release noise, per the
  corrected reading of Jain et al.
