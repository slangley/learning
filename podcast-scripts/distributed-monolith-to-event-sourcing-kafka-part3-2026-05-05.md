# From Distributed Monolith to Event-Sourced System with Kafka
## Part 3 of 4: Bridging the Synchronous and Asynchronous Worlds

**Episode metadata:**
- Series: From Distributed Monolith to Event-Sourced System with Kafka
- Episode: 3 of 4
- Topic: Bridging Sync and Async — The Messy Middle
- Approx runtime: 14–16 minutes
- Sources: Conduktor Saga guide, microservices.io, Kai Waehner Strangler Fig blog, AWS prescriptive guidance, architecture-weekly.com, Microsoft Engineering Playbook, Temporal.io

---

[MUSIC - INTRO]

## INTRO

[HOST] [excited] Welcome back to *Async Minded*. Part 3 of 4 in our series on moving from a distributed monolith to an event-sourced system with Kafka.

[HOST] If you've been following along — Part 1, we diagnosed the distributed monolith. Part 2, we built up the foundations: event sourcing, CQRS, the Outbox Pattern, Kafka as the durable log. All the theory and first principles you need.

[HOST] Today is Part 3, and this is the episode I hear people asking for most. Because the theory is one thing. But the *reality* of migration — the messy middle, where you have one foot in the old synchronous world and one foot in the new asynchronous one — that's where real projects live or die.

[HOST] We're going to talk about the Strangler Fig pattern. We're going to talk about the Saga pattern and how to handle long-running, rollback-capable workflows like onboarding in an event-driven world. We're going to talk about how to keep your product team and your users happy when you're introducing eventual consistency into a system they expect to respond immediately. And we're going to talk about how to not lose your mind operationally while all this is happening.

[HOST] [playfully] Let's bridge some gaps.

[PAUSE]

---

## SEGMENT 1 — The Strangler Fig: Your Migration Strategy

[HOST] [clears throat] The Strangler Fig Pattern gets its name from a tree. The strangler fig grows around a host tree, gradually replacing it, until one day the host tree is gone and the strangler fig is standing on its own. And it's a genuinely beautiful metaphor for how to migrate software systems. (Source: Kai Waehner, Strangler Fig blog, 2025)

[HOST] The alternative to the Strangler Fig is the Big Bang Rewrite. This is where you say "our old system is terrible, we're going to build the new one from scratch and then do a cutover." I think most engineers who've been in the industry more than five years have a story about a Big Bang Rewrite gone wrong. They almost always take longer than expected, they discover edge cases that only existed in the old system, and the cutover is terrifying. And they often fail.

[HOST] [sighs] The Strangler Fig says: don't do that. Migrate incrementally. The new system grows alongside the old one. You divert specific features or workflows from the old system to the new one, one by one, until the old system handles nothing and can be safely decommissioned.

[HOST] For a Kafka-based event-sourced migration, the Strangler Fig looks like this. You introduce a routing layer — often called an API gateway or a facade — in front of your existing monolith. Initially, all traffic goes through the facade straight to the old system, exactly as before. Then, as you migrate individual capabilities to the new event-sourced services, the facade routes those specific requests to the new system instead. (Source: AWS Prescriptive Guidance, Strangler Fig)

[HOST] [excited] And critically — you use Kafka as the synchronization layer between the old and new systems during the transition period. The old monolith publishes events via the Outbox Pattern. The new services consume those events. Eventually, the new services also start publishing events back, and the old system can consume those if it needs to be aware of what happened. The two systems run in parallel, sharing a common event bus, until the old one is fully replaced.

[HOST] For an onboarding system, a practical Strangler Fig migration might look like this. Month one: add the Outbox Pattern to the existing identity verification service. Wire up Debezium. Events start flowing to Kafka. Nothing changes for end users. Month two: build a new, dedicated notification service that consumes `OnboardingStatusChanged` events from Kafka and sends emails and SMS. Remove that responsibility from the monolith. Month three: build a new account provisioning service, event-sourced, that handles account creation asynchronously. Route new onboarding submissions through the new service. Old in-flight applications complete on the old service. Month six: the monolith is handling only legacy cases. Month nine: the monolith is decommissioned.

[HOST] [curious] That's not a fantasy timeline. That's actually achievable for a reasonably sized team with good test coverage and a clear domain model. The key is discipline: one capability at a time, validate thoroughly, then move to the next.

[PAUSE]

---

[AD BREAK]
[VOICE:brian] [excited] Is your Big Bang Rewrite currently six months late and twelve million dollars over budget?
[VOICE:domi] [deadpan] Of course it is. They all are.
[VOICE:brian] [cheerfully] Introducing StranglerKit™ — the migration tool that lets you replace your system ONE FUNCTION at a time!
[VOICE:domi] [curious] How many functions until I'm done?
[VOICE:brian] [whispers] ...We'll get back to you on that.
[VOICE:domi] [sighs] StranglerKit™. Incremental progress, indefinite timeline.
[AD END]

---

## SEGMENT 2 — The Saga Pattern: Long-Running Workflows With Rollback

[HOST] [clears throat] Let's talk about the Saga pattern. Because onboarding is the textbook use case for this, and I think it's under-explained most of the time.

[HOST] The problem: you have a workflow that involves multiple steps across multiple services — register user, verify identity, check fraud, provision account, send welcome message. In a synchronous world, you'd wrap all of this in a transaction. If step four fails, steps one through three roll back. The database guarantees it. Problem solved.

[HOST] In an event-sourced, asynchronous world, there's no global transaction. Each service owns its own data. There's no coordinator that can say "roll back everything." So how do you maintain correctness when a multi-step process fails halfway through? (Source: microservices.io saga pattern)

[HOST] The Saga pattern is the answer. A saga is a sequence of local transactions, one per service, where each local transaction publishes an event to trigger the next step. If a step fails, instead of rolling back — which you can't do across distributed services — you execute **compensating transactions**. These are the business-level undos for each prior step.

[HOST] [excited] Let's walk through an onboarding saga. Step 1: `OnboardingService` receives a new application. It creates a local record and publishes `ApplicationReceived`. Step 2: `KYCService` consumes `ApplicationReceived`, runs the identity check, and publishes either `KYCCheckPassed` or `KYCCheckFailed`. Step 3: `FraudService` consumes `KYCCheckPassed`, runs fraud screening, publishes `FraudCheckPassed` or `FraudCheckFailed`. Step 4: `AccountService` consumes `FraudCheckPassed`, provisions the account, publishes `AccountProvisioned`. Step 5: `NotificationService` consumes `AccountProvisioned`, sends the welcome email, publishes `WelcomeEmailSent`.

[HOST] Now — what happens if the fraud check fails? The `FraudService` publishes `FraudCheckFailed`. The `OnboardingService` is listening for this event. When it gets it, it executes its compensating transaction: update the application status to `REJECTED`, archive the KYC data appropriately, trigger a rejection notification. The application is cleanly in a terminal state. No orphaned data. No inconsistency.

[HOST] [curious] There are two flavors of saga: **choreography** and **orchestration**.

[HOST] In **choreography**, there's no central coordinator. Each service just reacts to events. `KYCService` listens for `ApplicationReceived`. `FraudService` listens for `KYCCheckPassed`. It's decentralized and fits naturally with Kafka's event-driven model. But as the number of steps grows, it becomes hard to understand the full workflow just by looking at any one service. You have to understand the entire event topology to reason about the end-to-end flow.

[HOST] In **orchestration**, there's a dedicated orchestrator service — a `SagaOrchestrator` or a workflow engine like Temporal — that explicitly tells each service what to do next. The orchestrator knows the full sequence. It issues commands like `InitiateKYCCheck` and listens for responses. This makes the workflow explicit and easier to debug, but introduces a central service that becomes a dependency. (Source: Conduktor Saga guide, 2025)

[HOST] [sighs] My recommendation for onboarding specifically: start with choreography for simplicity, but be prepared to introduce an orchestrator as the workflow complexity grows. Once you have more than five or six steps with complex branching logic — like "if the user is in the EU, route to this KYC vendor, otherwise use that one" — choreography becomes a debugging nightmare. That's when Temporal or a similar workflow engine pays for itself.

[PAUSE]

---

## SEGMENT 3 — The Hardest Part: Bridging the Synchronous API

[HOST] [paper rustling] Here's the scenario that breaks people's brains during the migration. Your frontend sends a `POST /onboarding/start` request. In the synchronous old world, that request returns 200 OK with the status of the completed onboarding. In the new event-sourced async world, that request just starts the saga. The result isn't available yet — the KYC vendor might take 30 seconds, or 30 minutes.

[HOST] What do you return to the frontend? How does the user know what's happening?

[HOST] [excited] The answer is the **Asynchronous Request-Response Pattern**, sometimes called polling or push-based status updates. Here's how it works.

[HOST] Your API endpoint receives the `POST /onboarding/start`. It validates the request, writes an `ApplicationReceived` event to Kafka, and returns immediately — not with the completed result, but with a `202 Accepted` response that includes an application ID and a status URL. Something like: `{ "applicationId": "app-12345", "status": "PROCESSING", "statusUrl": "/onboarding/app-12345/status" }`.

[HOST] The frontend now polls that status URL, or — even better — connects via WebSocket or Server-Sent Events to receive real-time status updates as the saga progresses. As events flow through the system — `KYCCheckPassed`, `FraudCheckPassed`, `AccountProvisioned` — each one updates the read model. The status endpoint reflects the latest state. The user sees a progress tracker: "Verifying identity... ✓ Checking fraud... ✓ Provisioning account..."

[HOST] [curious] This isn't weird or unfamiliar to users. Your bank already does this. You submit a payment, you get a "Payment submitted" confirmation immediately, and then you see "Payment processing" and "Payment completed" as status updates. The pattern is well-established for long-running operations.

[HOST] The key technical piece that makes this work is the **Correlation ID**. Every request gets a unique ID — your application ID. That ID travels on every Kafka event as a header or payload field. Every service that processes events for this application includes the correlation ID in its logs. Every status update in the read model is keyed to the correlation ID. When something goes wrong, you search your logs for the correlation ID and you can reconstruct the entire saga timeline. (Source: Microsoft Engineering Playbook, Correlation ID)

[HOST] [sighs] Without correlation IDs, debugging an async saga is genuinely terrible. You're looking at logs across five different services trying to figure out which log lines belong to the same user's onboarding. With correlation IDs, it's one search query and you have the full picture.

[HOST] There's another subtlety here: the **read-your-own-writes problem**. In a CQRS system, the write side and the read side are separate. After you publish an event on the write side, there's a tiny delay before the read model is updated. If the user immediately queries the status after submitting, they might see stale data.

[HOST] The fix is to have your write side return a **version number** along with the correlation ID. When the frontend queries the status, it sends that version number. The read model can check: "do I have data at least as recent as version N?" If not, it waits briefly or returns a "still processing" response. This gives users the "read your own writes" guarantee without tight coupling between write and read sides. (Source: architecture-weekly.com, eventual consistency)

[PAUSE]

---

[AD BREAK]
[VOICE:sam] [excited] Is your 202 Accepted response leaving your users confused about whether anything actually happened?
[VOICE:arnold] [deadpan] I've been staring at a loading spinner for eleven minutes. Is that normal?
[VOICE:sam] [cheerfully] Introducing StatusMaxPro™ — we generate deeply reassuring progress messages for your users while your saga does... whatever sagas do!
[VOICE:arnold] [curious] Like what messages?
[VOICE:sam] [playfully] "Almost there!" "Just a few more moments!" "Your future bank account is manifesting!"
[VOICE:arnold] [whispers] None of these are the actual status.
[VOICE:sam] [laughs] StatusMaxPro™. Feelings over facts. Always.
[AD END]

---

## SEGMENT 4 — Operational Reality: Observability in an Async World

[HOST] [clears throat] Let's talk about something that is absolutely critical and absolutely underestimated: **observability** in an event-driven system.

[HOST] In a synchronous system, a request comes in, your service handles it, and you get a response. The whole lifecycle lives in one trace. Your APM tool — Datadog, New Relic, whatever you use — can capture a single request trace from start to finish.

[HOST] In an async event-driven system, the "request" is actually a cascade of events across multiple services, potentially spread over minutes or hours. No single trace captures it. Your conventional APM tracing breaks.

[HOST] [excited] You need distributed tracing that propagates through Kafka. The W3C Trace Context standard gives you a way to propagate trace IDs through Kafka message headers, so that every service that processes an event as part of a saga can be linked to the same root trace. Tools like OpenTelemetry support this out of the box now. You instrument your Kafka producers and consumers once, and every event flowing through the system carries trace context.

[HOST] Beyond tracing, you need **event-level monitoring**. How many events are being produced per minute on your `onboarding.events` topic? How long is the consumer lag — the gap between when events are produced and when they're consumed? Consumer lag is your canary in the coal mine. If your `AccountService` consumer lag is growing, that service is falling behind. You need to know that before it becomes a user-visible problem.

[HOST] [curious] Dead letter queues are essential. Events that can't be processed — because of a bug, a schema mismatch, an unexpected payload — should not be silently dropped and not be endlessly retried. They go to a dead letter topic, where they can be inspected, fixed, and replayed. Every Kafka consumer should have dead letter handling. This is not optional. I've seen production incidents where millions of events quietly went to /dev/null because someone forgot to add DLQ handling to a consumer.

[HOST] And you need **saga monitoring** — a way to see the current state of all in-flight sagas. How many onboarding applications are currently in progress? How many are stuck in `KYC_PENDING` for more than their SLA window? Which ones have been waiting for a fraud check response for longer than expected? This is operational data that lives in your read model projections, and you need dashboards for it.

[HOST] [playfully] If you can't answer "how many onboarding applications are currently stuck and why?" in under sixty seconds by looking at a dashboard, your observability is not there yet. Build that before you go to production with your event-sourced system. Non-negotiable.

[PAUSE]

---

## OUTRO

[HOST] [excited] Alright, that's Part 3. We've covered the messy middle — the Strangler Fig migration strategy, the Saga pattern for long-running distributed workflows, how to bridge the synchronous API world with the asynchronous event world using 202 Accepted and correlation IDs, and what operational observability needs to look like in an async system.

[HOST] In Part 4 — the final episode — we're bringing it all together. A real, concrete walkthrough of taking a fintech onboarding application from a distributed monolith to a fully event-sourced, Kafka-backed system. We'll talk about team structure, the political and organizational challenges, common failure modes and how to avoid them, and what the system looks like once you're on the other side.

[HOST] [cheerfully] I'll see you in the finale. This is *Async Minded*.

[MUSIC - OUTRO]

---

*Sources:*
- Kai Waehner: "Replacing Legacy Systems One Step at a Time with Data Streaming: The Strangler Fig Approach" (2025)
- AWS Prescriptive Guidance: "Strangler Fig Pattern"
- microservices.io: "Pattern: Saga"
- Conduktor: "Saga Pattern for Distributed Transactions" (2025)
- Temporal.io: "Mastering Saga Patterns for Distributed Transactions in Microservices"
- Microsoft Engineering Playbook: "Correlation IDs" 
- architecture-weekly.com: "Dealing with Eventual Consistency and Causal Consistency using Predictable Identifiers"
- Enterprise Integration Patterns: "Asynchronous Request-Response"
