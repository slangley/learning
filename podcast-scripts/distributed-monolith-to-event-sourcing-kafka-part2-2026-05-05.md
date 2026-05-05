# From Distributed Monolith to Event-Sourced System with Kafka
## Part 2 of 4: Event Sourcing Fundamentals with Kafka

**Episode metadata:**
- Series: From Distributed Monolith to Event-Sourced System with Kafka
- Episode: 2 of 4
- Topic: Event Sourcing Fundamentals with Kafka
- Approx runtime: 14–16 minutes
- Sources: Confluent blog, Conduktor, developer.confluent.io, Mia-Platform, Cloudurable, The Honest Coder, Debezium docs

---

[MUSIC - INTRO]

## INTRO

[HOST] [excited] Welcome back to *Async Minded*. This is Part 2 of our four-part series on escaping the distributed monolith using event sourcing and Apache Kafka.

[HOST] Last episode we diagnosed the disease. We talked about what a distributed monolith actually is — those tangled webs of synchronous HTTP calls, shared databases, and cascading failures. We used onboarding as our main example: fintech KYC flows, HR employee provisioning, healthcare patient intake. Long-running, multi-step, multi-vendor workflows that are suffering inside synchronous architectures.

[HOST] Today we get into the medicine. We're going to cover event sourcing fundamentals — what it actually means, how it differs from what most teams are doing, and how Apache Kafka gives you the infrastructure backbone to make it all work. And we're going to stay practical. No abstract whiteboards. Real patterns you can actually implement.

[HOST] Let's go.

[PAUSE]

---

## SEGMENT 1 — What Event Sourcing Actually Means (And What It Doesn't)

[HOST] [clears throat] Let me start with the most important clarification, because I hear this confused all the time.

[HOST] Event sourcing is **not** just publishing events from your services. Almost every system already publishes *some* events. You call a REST endpoint, something happens, you fire a webhook, job done. That's not event sourcing.

[HOST] Event sourcing is a specific architectural decision: **the events are the source of truth**. Not the current state in your database. The events.

[HOST] Let me make that concrete. In a traditional CRUD system — Create, Read, Update, Delete — your database holds the *current state* of things. Your onboarding record has a status column that says "KYC_PENDING" or "ACCOUNT_PROVISIONED". That's all you have. The history of how it got there? Gone. You might have an audit log if someone thought to add one, but it's a second-class citizen.

[HOST] [excited] In an event-sourced system, you store this instead: `OnboardingStarted`, `DocumentSubmitted`, `KYCCheckInitiated`, `KYCCheckPassed`, `AccountProvisioned`, `WelcomeEmailSent`. Each event is an immutable fact. It happened. It's recorded. And the *current state* is derived by replaying those events. (Source: Confluent blog, event sourcing explainer)

[HOST] The analogy I love for this is a bank account. You don't think of your bank account as a number. You think of it as a ledger. There are deposits, withdrawals, transfers, fees. The balance is just what you get when you add them all up. Event sourcing applies that same ledger model to your entire application.

[HOST] And this is where it gets really powerful for onboarding workflows, specifically. Because onboarding is *inherently* a ledger. It's a sequence of things that happened to this application. KYC was checked. Documents were verified. Identity was confirmed. Fraud check passed. Each of those is a discrete, time-stamped fact. Storing them as immutable events is a natural fit.

[HOST] [sighs] The flip side is: event sourcing adds complexity. Reading current state now means replaying events, which can be slow. So almost universally you pair event sourcing with CQRS.

[PAUSE]

---

## SEGMENT 2 — CQRS: The Write Side and the Read Side

[HOST] CQRS — Command Query Responsibility Segregation. Let's break this down because it sounds scarier than it is.

[HOST] The idea is simple. Your system has two sides. The **write side** handles commands — things that change state. "Start onboarding", "Submit document", "Approve KYC". Each command, if valid, produces an event. That event gets appended to the event log. That's it. The write side is concerned only with producing correct events.

[HOST] The **read side** handles queries — things that read state. "What's the current status of this onboarding?" "Show me all onboarding applications that are stuck in KYC pending." The read side doesn't look at the raw event log. It looks at **projections** — pre-built views of the current state that are computed by processing the event stream. (Source: developer.confluent.io, CQRS course)

[HOST] [curious] Here's why this matters for onboarding. The write side — your onboarding commands — are probably a handful of events per application. KYCCheckPassed might happen once. AccountProvisioned happens once. Easy to store, easy to replay.

[HOST] But the read side — you might need a dozen different views of that data. Customer support needs to see the current status. Compliance needs the full audit trail. The risk team needs a dashboard showing how many applications are in each state. The CEO dashboard wants a funnel conversion view. Each of these is a different **projection** of the same underlying events, optimized for its specific query pattern.

[HOST] In a traditional system, you'd torture your OLTP database trying to serve all these different query patterns from a single normalized schema. With CQRS and event sourcing, you build separate read models — maybe your customer support view is in Postgres, the risk dashboard is in Elasticsearch, the compliance audit trail is stored in cold storage — all fed by the same event stream.

[HOST] [playfully] Same events. Multiple materialized views. Each optimized for its consumers. It's like running multiple financial reports from the same ledger. The ledger doesn't change; the reports are just different aggregations of it.

[PAUSE]

---

[AD BREAK]
[VOICE:rachel] [excited] Attention engineers! Are you still deriving state by reading a single giant database table with seventeen LEFT JOINs?
[VOICE:josh] [gasps] You MONSTER.
[VOICE:rachel] [cheerfully] Try new ProjectionPro™ — we build a separate optimized database for every single query pattern your stakeholders can dream up!
[VOICE:josh] [deadpan] Current clients include one team with forty-seven read models for a login page.
[VOICE:rachel] [whispers] We're not saying it's a good idea. We're saying it's YOUR idea.
[VOICE:josh] ProjectionPro™. Every view, everywhere, always.
[AD END]

---

## SEGMENT 3 — Kafka as the Event Backbone

[HOST] [clears throat] Now let's talk about why Kafka is the right infrastructure for event sourcing at scale.

[HOST] Kafka is often called a distributed log. And that's exactly what event sourcing needs. An immutable, ordered, durable, replayable log of events. Kafka's core data structure — the topic — is exactly that. Events go in, they don't get updated, they don't get deleted by default. They sit there for as long as your retention policy allows, and any consumer can read them from the beginning. (Source: Confluent blog)

[HOST] Let's talk about a few Kafka concepts that are particularly important for event-sourced onboarding systems.

[HOST] **Topics and partitions.** A Kafka topic for onboarding might be called `onboarding.events`. But inside that topic, events are distributed across partitions. For an onboarding system, you'd typically partition by application ID — all events for one user's onboarding go to the same partition, which guarantees ordering for that application. You don't care about ordering across different users' applications, only within a single application's timeline. This is a critical design decision. (Source: Confluent best practices)

[HOST] [excited] **Consumer groups.** Kafka consumer groups let multiple independent services consume the same event stream. Your KYC processing service consumes `onboarding.events`. Your account provisioning service consumes `onboarding.events`. Your notification service consumes `onboarding.events`. They all get every event, independently. They can process at their own pace. They can be down for maintenance and pick up where they left off. No service-to-service coupling. This is the foundational shift from the synchronous fan-out we saw in Part 1.

[HOST] **Event retention and replay.** Unlike a message queue that deletes messages once consumed, Kafka retains events for a configurable period — often days or weeks, sometimes indefinitely with compacted topics. This means if you need to rebuild a projection, you just rewind to the beginning and replay. If you add a new service that needs historical onboarding data, it reads from the beginning of the topic. This is event sourcing's superpower.

[HOST] [curious] **Schema Registry.** This is something teams often skip in the beginning and regret later. Event schemas evolve. Maybe you need to add a field to `KYCCheckPassed` to include the vendor's confidence score. But you have consumers that were built against the old schema. Schema Registry — typically running alongside Kafka using the Confluent Schema Registry or an open-source equivalent — manages schema versions and enforces compatibility rules. You can add fields, you can deprecate fields, but you can't remove a required field without a major version bump. This prevents the "I changed the event format and broke four downstream services" incident that haunts distributed systems. (Source: Cloudurable, 2025)

[HOST] **CloudEvents.** Worth a mention — CloudEvents is a CNCF standard for event envelope format. It defines standard fields: an ID, a source, a type, a timestamp. The actual payload is your domain data. Using CloudEvents as your envelope format means your events are immediately interoperable with any CloudEvents-compatible tooling, and it gives every event a consistent metadata structure that your infrastructure layer can reason about without understanding your domain. (Source: Quarkus CloudEvents blog)

[PAUSE]

---

## SEGMENT 4 — The Outbox Pattern: Bridging Your Database and Kafka

[HOST] [paper rustling] Okay, here's a pattern that is absolutely foundational for migrating an existing system to event sourcing. And it's one that doesn't get nearly enough attention: the **Transactional Outbox Pattern**.

[HOST] Here's the problem it solves. In your onboarding service, you're handling a command: "Approve this KYC check." You need to do two things atomically: update the status in your database, and publish a `KYCCheckApproved` event to Kafka. The problem is that these are two different systems. You can't do a distributed transaction across your Postgres database and Kafka without either a two-phase commit — which we discussed in Part 1 is a nightmare — or accepting that one might succeed and the other might fail.

[HOST] [sighs] The outbox pattern solves this elegantly. Instead of publishing to Kafka directly from your application code, you write the event into a special table in your *same database* — the outbox table — in the same transaction as your business data change. Now you have atomicity. Either both the business change and the outbox record commit together, or neither does. Your database transaction is the atomic unit. (Source: Conduktor outbox pattern guide)

[HOST] A separate process then reads from the outbox table and publishes to Kafka. And this is where **Debezium** comes in. Debezium is a change data capture tool that plugs into your database's transaction log — the write-ahead log in Postgres, the binlog in MySQL — and streams every change to an outbox table directly into Kafka. No polling. It reads the log, so it gets changes the instant they're committed. And because it tracks its position in the log, if it goes down and comes back up, it resumes exactly where it left off. No events are lost. No events are duplicated. (Source: The Honest Coder, Debezium outbox guide)

[HOST] [excited] This is a game-changer for migration. You don't have to rearchitect your entire system at once. You can start adding outbox tables to your existing services today. Write events there in your existing transactions. Wire up Debezium. And suddenly you have a reliable event stream coming out of your monolith — without changing the monolith's core architecture yet. That event stream becomes your bridge to the new event-sourced world.

[HOST] Let me make this concrete for onboarding. Your existing `IdentityService` has a `verify_identity` method that calls the KYC vendor and updates the `identity_checks` table. Step one: you add an `outbox` table to that same database. Step two: `verify_identity` now also writes a `KYCCheckCompleted` event to the outbox, in the same transaction. Step three: Debezium picks it up and publishes to Kafka. Zero change to your downstream services. They just start getting events on a Kafka topic instead of waiting for a synchronous callback.

[HOST] That is incremental. That is safe. That is how you do this without a big-bang rewrite.

[PAUSE]

---

[AD BREAK]
[VOICE:adam] [excited] Tired of your application and your message broker being in two completely different transactions?
[VOICE:matilda] [deadpan] Of course you are. We all are.
[VOICE:adam] [cheerfully] Introducing OutboxMax™ — just write one extra row to your database! Problem solved! Philosophically!
[VOICE:matilda] [curious] Does it guarantee exactly-once delivery?
[VOICE:adam] [whispers] We prefer the term... *at-least-once with idempotent consumers*. It's the same thing but it sounds like a feature.
[VOICE:matilda] [laughs] OutboxMax™. One table to rule them all.
[AD END]

---

## SEGMENT 5 — Event Design: Getting Your Events Right from Day One

[HOST] [clears throat] Let me spend a few minutes on event design, because this is where teams make mistakes that are very hard to undo later.

[HOST] Events should describe **what happened**, not **what to do**. This sounds obvious but gets violated constantly. A bad event name is `SendWelcomeEmail`. That's a command dressed up as an event. A good event name is `OnboardingCompleted`. The fact that you send a welcome email in response to `OnboardingCompleted` is the email service's business, not the onboarding service's.

[HOST] [sarcastic] The moment you name an event `SendWelcomeEmail`, you've created an implicit dependency. The onboarding service now knows about the email service. You've just recreated coupling through your message bus. Congratulations, you've built an asynchronous distributed monolith. That's somehow worse.

[HOST] Events should be **coarse-grained at the domain level**. Don't publish an event every time a database field changes. Publish an event when something meaningful happens in the business process. `DocumentVerified`, `IdentityConfirmed`, `AccountProvisioned`. These are meaningful domain events. `user_table_row_updated` is not a domain event.

[HOST] [curious] Events should be **self-contained**. An event should carry enough information that a consumer can process it without having to call back to the source service for more data. If your `KYCCheckPassed` event only carries the application ID, every consumer that needs to do something with it has to call back to the KYC service to get the details. That's a synchronous dependency hiding inside your asynchronous system. Include the relevant context in the event payload.

[HOST] And events should be **immutable and versioned**. Once published, an event's meaning doesn't change. If your domain model evolves, you create a new event version. Your Schema Registry enforces this. This is non-negotiable for event sourcing systems that need to replay history correctly.

[PAUSE]

---

## OUTRO

[HOST] [excited] That's Part 2. We've covered the foundations: what event sourcing actually is, how CQRS splits your system into a clean write side and a flexible read side, how Kafka's durable log gives you the infrastructure backbone, how the Outbox Pattern with Debezium gives you a practical bridge out of your existing synchronous system, and how to design events that don't recreate the coupling you're trying to escape.

[HOST] In Part 3, we're going to get into the hardest part of the transition — the messy middle. How do you run your old synchronous system and your new event-sourced system side by side? How do you handle the Saga pattern for workflows that span multiple services and need rollback semantics? How do you deal with the eventual consistency mindset shift that your product managers are going to resist? And how do you keep your onboarding SLAs intact while the architecture is evolving underneath you?

[HOST] That's where things get really interesting. Trust me, you don't want to miss it.

[HOST] [cheerfully] I'm your host. This is *Async Minded*. See you in Part 3.

[MUSIC - OUTRO]

---

*Sources:*
- Confluent Blog: "Event Sourcing, CQRS, Stream Processing and Apache Kafka: What's the Connection?"
- developer.confluent.io: "Event Sourcing and Event Storage with Apache Kafka — CQRS" course
- Conduktor: "Outbox Pattern for Reliable Event Publishing" (2025)
- The Honest Coder: "Reliable Event Publishing: Outbox Pattern with PostgreSQL, Debezium, and Kafka"
- Cloudurable: "Apache Avro 2025 Guide: Schema Evolution, Microservices, and Modern Data Streaming"
- Quarkus: "Sending and Receiving Cloud Events with Kafka"
- Debezium documentation (2025)
