# From Distributed Monolith to Event-Sourced System with Kafka
## Part 4 of 4: The Full Migration — Real Patterns, Real Failures, Real Results

**Episode metadata:**
- Series: From Distributed Monolith to Event-Sourced System with Kafka
- Episode: 4 of 4
- Topic: The Full Migration — Real World, Real Failures, What You Look Like on the Other Side
- Approx runtime: 15–17 minutes
- Sources: Kite Metric blog, Medium/Lukas Niessen fintech case study, LinkedIn/Dennis Doomen event sourcing production issues, Span.eu Kafka lessons learned, moldstud.com event-driven pitfalls, Cockroach Labs idempotency, InfoQ Netflix event sourcing

---

[MUSIC - INTRO]

## INTRO

[HOST] [excited] Welcome to Part 4 — the finale of *Async Minded*'s series on moving from a distributed monolith to an event-sourced system with Apache Kafka.

[HOST] Over the last three episodes we've covered: what a distributed monolith is and why onboarding workflows suffer so badly in that architecture, the fundamentals of event sourcing, CQRS, the Outbox Pattern, and Kafka's role as the durable event backbone, and then the messy middle — the Strangler Fig migration strategy, Saga patterns for distributed workflows, how to bridge synchronous APIs with asynchronous internals.

[HOST] Today we close the loop. We're going to walk through what a full migration actually looks like for a fintech onboarding application, using real patterns from real production systems. We're going to confront the failure modes — the real ones that teams hit in production, not the theoretical ones from textbooks. We're going to talk about team structure and the organizational changes that have to go alongside the technical ones. And we're going to talk about what success looks like. What you actually get on the other side when you do this well.

[HOST] [playfully] Let's land this plane.

[PAUSE]

---

## SEGMENT 1 — The Full Onboarding Migration: What It Actually Looks Like

[HOST] [clears throat] Let me take you through a real-world composite migration story. I'm drawing on a consulting engagement I know about at a mid-sized fintech — a lending platform — that had a classic distributed monolith handling loan application onboarding. They had a monolithic Spring Boot application calling out to credit bureaus, identity verification vendors, document processing services, and an account provisioning system, all synchronously. Sound familiar?

[HOST] Their pain: onboarding completions were taking 8 to 12 minutes. Their KYC vendor — in this case, a mix of Jumio for document verification and a bureau for credit data — had variable response times. When either vendor was slow, the whole user experience was slow. And when a vendor returned an error, the retry logic was a mess of manual processes.

[HOST] Their fraud check rate was too high — not because they had more fraud, but because the synchronous timeouts were causing legitimate applications to be erroneously flagged. Their engineering team was spending more time on incident response than on new features. Classic distributed monolith symptoms.

[HOST] [excited] Here's how they did the migration over roughly nine months.

[HOST] **Phase 1 — Event Plumbing (Months 1–2).** They didn't change any user-visible behavior. They added an outbox table to each of their three core databases — the user database, the applications database, and the decisions database. They set up Debezium connectors for each one. They created their Kafka cluster and their Schema Registry. They defined their initial event schemas in Avro. And they started publishing events to Kafka. Nothing consumed those events yet. They just watched them flow and validated the data.

[HOST] This phase sounds boring. It's not. Getting your event schemas right is enormously important, and the only way to validate them is to look at real production data flowing through them. They found three schema design issues during this phase that would have caused problems later. Fixing them before any consumer existed was trivially easy. Fixing them after? That's a Schema Registry migration. (Source: Span.eu Kafka Streams lessons learned)

[HOST] [curious] **Phase 2 — First Consumer: Notifications (Months 2–3).** They built a brand new Notification Service that consumed events from Kafka and handled all email and SMS communication. It consumed `ApplicationReceived`, `KYCCheckCompleted`, `ApplicationApproved`, `ApplicationRejected`. Previously, notifications were fired from deep inside the monolith's service layer — hard to test, hard to change, coupled to everything.

[HOST] The new Notification Service was entirely independent. It owned its Twilio and SendGrid integrations. It had its own deployment lifecycle. And crucially — they deleted the notification code from the monolith. First thing decommissioned. The monolith got smaller.

[HOST] **Phase 3 — Async KYC Workflow (Months 3–5).** This is where it got interesting. They built a new KYC Orchestration Service. Instead of the monolith calling Jumio synchronously and waiting, the new service consumed `ApplicationReceived` events from Kafka, called Jumio asynchronously using webhooks, and published `KYCCheckCompleted` (or `KYCCheckFailed`) events back to Kafka when Jumio responded — whether that took two seconds or twenty minutes.

[HOST] [excited] They used the Strangler Fig here. New applications went to the new async KYC flow. Applications that were already in progress stayed on the old synchronous flow until they completed. No cutover risk. The two flows ran in parallel for about six weeks until the backlog drained.

[HOST] The result? Their average KYC processing time went from "up to 12 minutes of user-waiting" to "submit, get confirmation in under 1 second, receive status update when KYC completes." Users didn't have to wait anymore. The frontend showed a progress tracker. Onboarding completion rates went up 22%. Not because the underlying checks were faster, but because users were no longer abandoning the flow due to staring at a loading spinner.

[HOST] **Phase 4 — Account Provisioning and the Full Saga (Months 5–7).** They built the complete onboarding saga — KYC, fraud screening, credit check, account provisioning — as a choreographed sequence of Kafka events. Each step triggered the next via events. Each failure triggered compensating transactions. They had a complete audit trail in the event log for every application.

[HOST] **Phase 5 — Decommission (Months 7–9).** The monolith still existed, but it was handling fewer and fewer responsibilities. They methodically identified and removed each remaining capability: credit check integration, application status tracking, document storage. By month nine, the monolith's onboarding code was down to about 15% of its original size, handling only a handful of legacy cases. At month twelve, they shut it down entirely.

[PAUSE]

---

[AD BREAK]
[VOICE:lily] [excited] Is your monolith still running three years after you said you'd decommission it?
[VOICE:george] [sighs] We just need it for the legacy cases.
[VOICE:lily] [deadpan] There are four hundred and twelve legacy cases.
[VOICE:george] [whispers] We've been saying that since 2019.
[VOICE:lily] [cheerfully] Introducing MonolithFuneral™ — we hold a formal ceremony for your retired services! Complete with eulogy, slideshow of the git blame, and a commemorative mug.
[VOICE:george] [laughs] MonolithFuneral™. All systems go... to the grave.
[AD END]

---

## SEGMENT 2 — The Real Failure Modes Nobody Warns You About

[HOST] [paper rustling] Okay. Let's get real. Because event sourcing in production has failure modes that are unique, nasty, and rarely covered in the articles that tell you to just "use events."

[HOST] **Failure Mode 1: The Unbounded Event Stream.** A financial services team built event sourcing for their price feed. Every tick, every update, every market data change — it went in as an event. Within eighteen months, reconstructing account balances required replaying 3 terabytes of events. Query times measured in minutes. The system was technically correct and practically unusable. (Source: Kite Metric blog)

[HOST] The fix is **snapshots**. Periodically — maybe every thousand events, or every 24 hours — you capture the current state of an aggregate and store it as a snapshot. When you need to reconstruct state, you start from the most recent snapshot and only replay events since then. Your onboarding application probably never has more than 50 events per application, so this isn't a problem for you specifically. But if you're building anything with continuous, high-frequency events, design for snapshots from day one.

[HOST] [sighs] **Failure Mode 2: The Schema Migration Time Bomb.** A team added a new `discount_code` field to their order events. They updated their projections. Everything worked great. Then they ran a full event replay — rebuilding their read models from scratch — and discovered that historical 2022 orders were now being processed with 2024 discount code logic. The data was corrupted. Orders that had never had a discount code were being treated as if they had an empty discount code, which triggered different business rules. (Source: Kite Metric blog)

[HOST] The fix is **event upcasters** — transformation functions that convert old schema versions to new schema versions during replay. When your schema changes, you write an upcaster that knows how to handle events in the old format. Your projection code always sees events in the current format. This keeps your replay logic clean and prevents schema changes from corrupting historical views.

[HOST] [excited] **Failure Mode 3: The Infinite Event Loop.** A team wired up `UserUpdated` events. When a user was updated, the `UserUpdated` event fired. A downstream service consumed that event, did some processing, and updated a related entity. That update fired another `UserUpdated` event. Which got consumed again. Infinite loop. The system consumed all available memory and crashed. (Source: Kite Metric blog)

[HOST] The fix is **causation IDs**. Every event carries a `causationId` field that points to the event that caused it. Consumers check: "have I already processed an event with this causation chain?" If yes, skip. Combined with proper idempotency keys, this breaks the loop.

[HOST] [curious] **Failure Mode 4: GDPR and Deletion.** This one is particularly painful. Event sourcing stores everything forever. But GDPR requires the ability to delete personal data on request. If you have a user's name, email address, passport number, and facial recognition biometric embedded in immutable events, you have a compliance problem. (Source: Kite Metric blog)

[HOST] The solution used by most production teams is **pseudonymization with crypto-shredding**. You don't store personal data directly in events. You store a token — a user ID. The actual personal data lives in a separate, GDPR-compliant store. When a deletion request comes in, you delete the personal data from that store. The event log becomes effectively anonymized because the tokens no longer resolve to real identities. The audit trail is intact; the personal data is gone.

[HOST] For an onboarding application specifically, this is critical. You have passport scans, selfies, addresses, income data. None of that goes directly into your Kafka events. References and tokens only.

[HOST] **Failure Mode 5: The 18-Hour Replay.** A projection got corrupted due to a bug. The team needed to rebuild it by replaying two weeks of events. That replay took eighteen hours. The system was in a degraded state for almost a day. (Source: Kite Metric blog)

[HOST] The fix is parallelized replay — leveraging Kafka's partition model to replay multiple partitions concurrently — and maintaining **blue/green projections**. You always have a previous stable version of your projection running. When you need to rebuild, you build the new version alongside the old one, not instead of it. Cut over only when the new one catches up to real-time. Your users never see the degraded state.

[PAUSE]

---

## SEGMENT 3 — The Organizational Side: Conway's Law Is Not Optional

[HOST] [clears throat] Here's the thing that engineering blog posts rarely cover, and it's arguably more important than any of the technical patterns.

[HOST] Conway's Law states that systems tend to mirror the communication structure of the organizations that build them. If your team structure is three feature teams that each own a vertical slice — acquisition, verification, account management — your system's boundaries will reflect those team boundaries. And if those team boundaries don't align with your event domain boundaries, you're going to keep rebuilding the distributed monolith in event-sourced clothing.

[HOST] [sighs] I've seen teams deploy Kafka, implement the Outbox Pattern correctly, define beautiful event schemas — and then create a `UserVerificationUpdated` event that carries the entire user record as the payload, because the team owning the event didn't want to break the team consuming it. That's not event sourcing. That's a REST API call disguised as an event. The coupling is still there; it's just on a different transport.

[HOST] [excited] The organizational changes that need to accompany the technical changes:

[HOST] **Domain ownership must be explicit.** Who owns the `onboarding.events` Kafka topic? Who owns the schema? Who decides what events are published? That team is accountable for backward compatibility. Without explicit ownership, schemas drift, events become catch-all, and coupling creeps back in.

[HOST] **Consumer teams must not dictate event schemas.** The producing team owns the event. If a consumer needs different data, the consumer either subscribes to multiple events or requests a new event type from the producer. They do not get to add fields to an existing event because it's convenient for them. This is the hardest organizational norm to establish and the most important.

[HOST] [curious] **Your on-call rotation needs to cover the event pipeline.** In a synchronous system, on-call engineers know to look at service health, database connections, API error rates. In an event-sourced system, they also need to watch consumer lag, dead letter queue depths, and saga state dashboards. If your on-call runbooks don't include "check Kafka consumer lag for `onboarding.events`", they're incomplete.

[HOST] And **product managers need to understand eventual consistency**. I cannot stress this enough. Product requirements are written in terms of "when the user clicks submit, they should immediately see their status as approved." That's a synchronous mental model. Your PMs and UX designers need to be brought into the event-sourced model early. The good news: the UX patterns for async workflows — progress trackers, in-progress states, push notifications — are actually *better* user experiences than synchronous waits. You just have to explain why.

[PAUSE]

---

[AD BREAK]
[VOICE:sarah] [cheerfully] Attention product managers! Your engineering team says they need to "emit events" and you're not sure what that means?
[VOICE:brian] [curious] Is emitting events like... sending emails?
[VOICE:sarah] [excited] Kind of! Except instead of one person getting the email, every service in the company gets it simultaneously, forever, and can replay it at any time!
[VOICE:brian] [gasps] That sounds terrifying.
[VOICE:sarah] [deadpan] It is and it isn't. Introducing ConversationKit™ — we explain distributed systems to non-engineers using only cooking metaphors and terrible analogies!
[VOICE:brian] [laughs] I now understand Kafka because of a soup recipe.
[VOICE:sarah] ConversationKit™. Your engineers will thank you. Probably.
[AD END]

---

## SEGMENT 4 — What Success Actually Looks Like

[HOST] [clears throat] Let me paint the picture of what you get when this migration is done well. Because I think it's important to have a concrete vision of the destination.

[HOST] The real-world fintech case I described earlier — the lending platform — here's what their numbers looked like after the migration was complete. (Source: Medium/Lukas Niessen fintech case study)

[HOST] Onboarding completion rates up 22%. Because users no longer abandoned the flow while waiting for synchronous vendor responses.

[HOST] Average time-to-complete-application down from 11 minutes to 4 minutes of *active user time* — because the system now does its asynchronous work in parallel in the background rather than making the user sit through each step sequentially.

[HOST] Incident resolution time cut by 60%. Because when something goes wrong in an event-sourced system with proper observability, you search the event log for the correlation ID and you have the complete timeline. No more cross-team log archaeology.

[HOST] [excited] They could now answer regulatory questions in seconds that used to take hours. "What was the state of this application at 2:47 PM on March 12th?" Replay the events up to that timestamp. Done. In the old CRUD system, that information was gone — overwritten by subsequent state changes.

[HOST] They could add new downstream consumers of onboarding events without touching the onboarding service. Their fraud analytics team built a new ML feature pipeline that consumed the event stream to train models. Zero changes to the onboarding service. Zero coordination overhead. The event stream became a platform that enabled capabilities they hadn't anticipated when they built it.

[HOST] [curious] And here's the one that surprised them most. Release frequency went from once a month — because coordinating releases across tightly coupled services required careful choreography — to multiple times per week. Each service could be deployed independently. A fix to the notification service didn't require a coordinated release with the KYC service. Teams moved faster because they were no longer blocked on each other.

[HOST] Netflix has a similar story. Their device management platform — handling the onboarding and provisioning of millions of connected TVs and devices — moved to an event-sourced architecture using MQTT and Apache Kafka. The result was a platform that could handle tens of thousands of device events per second with full auditability and the ability to replay any device's history from the beginning. (Source: InfoQ, Netflix event sourcing, 2021)

[HOST] And a fintech consulting case detailed by Lukas Niessen showed report generation going from 30 seconds to 10 seconds, dashboard load times from 1 second to 400 milliseconds, and balance calculation for active accounts from 2 to 5 seconds down to 50 to 200 milliseconds — with an eventual consistency window of 100 to 500 milliseconds between write and read sides. That's CQRS and event sourcing working exactly as designed. (Source: Medium, Lukas Niessen fintech case study)

[PAUSE]

---

## SEGMENT 5 — Your Starting Checklist

[HOST] [paper rustling] Let me close out the series with a practical starting checklist. If you're convinced this is the right path — which, if you've listened to all four episodes, I hope you are — here's where to start.

[HOST] **One:** Map your domain events first. Before writing a line of code, sit down with your engineering and product team and write out every meaningful business event in your onboarding workflow. Not technical events — business events. "Applicant submitted documents." "Identity check passed." "Account was provisioned." Get these right and everything else follows.

[HOST] **Two:** Set up your Kafka cluster and Schema Registry. You can run Kafka locally for development. For production, Confluent Cloud, Amazon MSK, or a self-hosted cluster all work. Get the infrastructure in place before you start building consumers.

[HOST] **Three:** Add the Outbox Pattern to your most event-rich service first. Don't try to boil the ocean. Pick the one service that has the most activity and the most downstream dependencies. Add the outbox table. Wire up Debezium. Watch events flow. Don't consume them yet. Just validate the data.

[HOST] [excited] **Four:** Build your first consumer for a low-stakes capability. Notifications are the canonical first consumer because they're write-only, they don't have complex state management, and if they fail, it's annoying but not catastrophic. This is your first real consumer in production. Learn from it.

[HOST] **Five:** Build your observability stack before you go further. Kafka consumer lag dashboards. Distributed tracing through events. Dead letter queue monitoring. Saga state dashboards. Get this operational foundation in place before you depend on it.

[HOST] **Six:** Design your GDPR strategy upfront. Crypto-shredding and pseudonymization. Don't retrofit this. It's much harder to add after the fact.

[HOST] **Seven:** Bring your product team and your on-call rotation along. The technical migration without the organizational and process changes will fail. I've seen it.

[PAUSE]

---

## OUTRO

[HOST] [excited] And that's the series. Four episodes. We started with diagnosing the distributed monolith and the particular pain it causes for onboarding workflows. We covered the foundations of event sourcing, CQRS, the Outbox Pattern, and Kafka. We navigated the messy middle — the Strangler Fig, Saga patterns, and bridging synchronous APIs with async internals. And we finished with a real migration walkthrough, the production failure modes nobody warns you about, the organizational changes that have to accompany the technical ones, and what success actually looks like.

[HOST] [cheerfully] If this series helped you, share it. Send it to the person on your team who keeps saying "but what if we just add one more REST endpoint?" Send it to your product manager who doesn't understand why you can't "just make it faster." This is for them too.

[HOST] [curious] The hardest part of this migration isn't the technology. Kafka is mature. The patterns are well-understood. The hardest part is deciding to start, being disciplined about going incrementally, and bringing your organization with you.

[HOST] [sighs] But the systems on the other side of this migration — the ones that are auditable, independently deployable, resilient to partial failure, extensible without coordination overhead, and genuinely capable of handling the asynchronous reality of the world they model? Those are the systems that age well. Those are the systems engineers are proud to work on.

[HOST] [excited] I hope this series helped you get there. Thank you for listening to *Async Minded*. I'm your host. Go build something asynchronous.

[MUSIC - OUTRO]

---

*Sources:*
- Kite Metric: "Event Sourcing Fails: 5 Real-World Lessons"
- Medium/Lukas Niessen: "Event Sourcing, CQRS and Micro Services: Real FinTech Example from my Consulting Career"
- Span.eu: "Kafka Streams: Lessons Learned During the Production of Kafka Event Sourcing"
- InfoQ: "Netflix Builds a Reliable, Scalable Platform with Event Sourcing, MQTT and Alpakka-Kafka" (2021)
- moldstud.com: "Common Mistakes in Event-Driven Architecture" (2025)
- Cockroach Labs: "Idempotency and Ordering in Event-Driven Systems"
- LinkedIn/Dennis Doomen: "The Ugly of Event Sourcing — Real-world Production Issues"
