# From Distributed Monolith to Event-Sourced System with Kafka
## Part 1 of 4: Diagnosing the Distributed Monolith

**Episode metadata:**
- Series: From Distributed Monolith to Event-Sourced System with Kafka
- Episode: 1 of 4
- Topic: Diagnosing the Distributed Monolith
- Approx runtime: 13–15 minutes
- Sources: vFunction blog, InfoQ, Confluent blog, Medium/HeyJobs, MerginIT blog, Growin.com, MDPI research paper

---

[MUSIC - INTRO]

## INTRO

[HOST] [excited] Welcome to *Async Minded* — the podcast where we pull apart the tangled wires of distributed systems and figure out how to make software that actually scales. I'm your host, and today we're kicking off a four-part series that I've been wanting to do for a long time.

[HOST] We are going to talk about one of the most painful traps in modern software engineering — the **distributed monolith** — and over these four episodes, we're going to walk you all the way through how to escape it using **event sourcing** and **Apache Kafka**. Real patterns. Real war stories. No shopping carts, no hypothetical bookstores.

[HOST] [playfully] I'm looking at you, every architecture blog written between 2017 and 2023.

[HOST] Today is Part 1: Diagnosing the Problem. Because you can't fix what you haven't actually named. And a lot of teams are living in this particular hell without realizing they've given it a name yet. Let's get into it.

[PAUSE]

---

## SEGMENT 1 — What Is a Distributed Monolith (And Why Did You Build One)?

[HOST] [clears throat] Let's start with a definition. A distributed monolith is a system that *looks* like microservices on the outside — separate repos, separate deployments, separate teams — but behaves like a tightly coupled monolith on the inside.

[HOST] Sam Newman, who wrote *Building Microservices*, put it best: it's a system where you have all the complexity of distributed systems *plus* all the constraints of a monolith. You lose on both sides. You're not getting the independent deployability of microservices, and you're not getting the simplicity of a monolith. You've achieved maximum pain with minimum benefit. (Source: InfoQ, 2025)

[HOST] [sighs] So how does this happen? Nobody sits down and says "you know what we should build today? A distributed monolith." It's almost always accidental. And it usually starts with good intentions.

[HOST] The most common origin story goes like this. Your team has a working monolith. It's getting harder to deploy. Teams are stepping on each other. So leadership says — we're going microservices. And what happens next? You take your existing monolith, and you draw service boundaries *along the lines of your existing code structure*, not along the lines of your business domains.

[HOST] [sarcastic] Brilliant. You've just lifted and shifted your coupling from inside one process to across a network. Congratulations.

[HOST] According to research from vFunction, a platform that helps organizations actually analyze their runtime coupling, the most common culprit is the **shared database**. Multiple services, all reading and writing to the same schema. The schema becomes this invisible contract that nobody owns, everybody depends on, and changing a single column requires a cross-team meeting that takes three weeks to schedule. (Source: vFunction blog, 2025)

[HOST] The second culprit is **synchronous HTTP chains**. Service A calls Service B, which calls Service C, which calls Service D. Your user is waiting for all four to respond. If D is slow, everyone waits. If D is down, the whole request fails. Your system's reliability is now the *product* of all four services' individual reliabilities.

[HOST] [excited] Here's the math on that. If each service has 99.9% uptime — which sounds pretty good — and you have five services in a synchronous chain, your end-to-end availability is 99.9% to the power of 5. That's about 99.5%. That means roughly four extra hours of downtime per year, just from the architecture. Add a few more services, or make any of them a little flakier, and you're looking at serious SLA violations. (Source: Growin blog, 2025)

[HOST] And the third culprit — shared libraries. Teams extract common code into a shared package that everyone imports. And suddenly, updating that package requires coordinating releases across six teams because they all depend on the same version. Conway's Law strikes again.

[PAUSE]

---

[AD BREAK]
[VOICE:george] [excited] Are you tired of your microservices talking to each other *all the time*? Like they just can't stop?
[VOICE:sarah] [deadpan] Introducing ChatterBlock™ — the enterprise firewall that silently drops 40% of your inter-service HTTP calls at random.
[VOICE:george] [cheerfully] Forces your engineers to actually make their services resilient! Whether they like it or not!
[VOICE:sarah] [whispers] Side effects include rage commits, mandatory chaos engineering retrospectives, and one very confused on-call engineer at 3 AM.
[VOICE:george] ChatterBlock™. Stop talking. Start surviving.
[AD END]

---

## SEGMENT 2 — The Onboarding Application: A Perfect Storm

[HOST] [clears throat] Now I want to talk about the domain that I think *perfectly* illustrates the distributed monolith problem, and it's one you almost never see in architecture talks: **user onboarding**.

[HOST] And I don't mean a little sign-up form with an email and password. I mean *real* onboarding. Fintech onboarding. Healthcare patient intake. HR employee onboarding. The kind where the stakes are high, there are regulatory requirements, multiple external vendors involved, and the user experience needs to feel smooth even though the backend is doing an enormous amount of work.

[HOST] Let me paint you a picture. You're building an onboarding flow for a challenger bank. A new customer downloads the app, fills in their details, and hits submit. Here's what has to happen in the next few seconds or minutes.

[HOST] [excited] The user registration service creates an account. The KYC service kicks off an identity check — maybe with Jumio or Onfido, which are external APIs with their own latency, their own rate limits, and their own failure modes. The document upload service handles their passport scan. There's an AML screening service talking to a sanctions database. There's an account provisioning service that creates their actual bank account number. There's a notification service sending a welcome SMS via Twilio. And there's a compliance service writing audit records. (Source: Apriorit KYC development guide, 2025)

[HOST] Now here's the question. Are all of these happening synchronously? Is the user sitting there waiting while your onboarding service makes eight sequential API calls and hopes none of them time out?

[HOST] [sighs] In a lot of systems? Yes. Exactly that.

[HOST] I've talked to engineering teams at fintech companies where a single onboarding submission triggers a chain of 12 synchronous calls. Twelve. And if the KYC vendor's API is having a rough morning — which they do, they're external vendors, it happens — the whole onboarding fails. The user gets an error. They try to resubmit. And now you've sent their documents to Jumio twice.

[HOST] This is the synchronous fan-out problem. You've got one incoming request fanning out to many downstream services, all synchronously, all in-process in terms of the user's experience. And the worst part is that some of those calls — like the KYC check — can take anywhere from two seconds to several minutes depending on what the vendor needs to do. You can't hold an HTTP connection open for several minutes. Well, technically you can, but you really shouldn't.

[HOST] [curious] And the healthcare version of this is equally wild. Patient intake for a hospital system. A patient books an appointment online. Behind the scenes, you need to verify their insurance eligibility against the payer's system — that's an EDI 270/271 transaction, which is its own adventure. You need to check if they've been a patient before and merge records if so. You need to notify the scheduling system, potentially alert a care coordinator, and send appointment reminders. All of this involves external systems, some of which are running on technology from a different decade.

[HOST] And HR onboarding — think about what happens when a new employee joins a company. The HRIS system needs to create their profile. Active Directory or Okta needs to create their account. IT needs to provision their laptop and assign software licenses. Payroll needs their banking details. Slack, Jira, GitHub all need to add them. Their manager needs a notification. Their buddy needs a notification. Building access gets provisioned. Benefits enrollment opens. Compliance training gets assigned.

[HOST] [playfully] That's about fifteen systems that need to be notified, and in most companies those notifications happen through a spaghetti of synchronous calls, webhooks, and someone manually running a script on Fridays.

[PAUSE]

---

## SEGMENT 3 — The Death Star and Why Your Architecture Diagram Is Lying

[HOST] [paper rustling] Let me introduce you to what engineers have started calling the **Death Star architecture**. This is where your microservices component diagram starts looking like a dense web of lines connecting every service to every other service. It's technically separate services, but they're all talking to each other synchronously in a haphazard, unplanned way.

[HOST] The Confluent team published a great piece on this, referencing a concept from functional programming: when you build microservices around the request-response pattern, you're essentially doing object-oriented programming across the network. Every service is an object with methods. You call the methods synchronously. The problems that come with OOP at scale — deep call stacks, state entanglement, difficulty testing in isolation — all of those problems come with you into the distributed world. Except now they're slower and they fail with 503 errors. (Source: Confluent blog)

[HOST] [gasps] And here's the thing that kills me about the Death Star: your architecture diagrams don't show it. You have a nice clean diagram with boxes and arrows. But the arrows only show the *intentional* dependencies. They don't show the implicit ones. The shared database tables. The shared configuration service that everyone quietly polls. The scheduled job that reads from five different services' databases directly.

[HOST] vFunction did research on this — they have tooling that observes actual runtime traffic in production rather than relying on documentation — and they found that the actual dependency graph in most enterprise systems is typically two to three times more connected than the architecture diagrams suggest. The diagrams are aspirational. The code is the truth. (Source: vFunction blog, 2025)

[HOST] And in an onboarding context, this is especially dangerous. Because onboarding workflows are **long-running**. They don't complete in milliseconds. A KYC check might come back in two seconds or twenty minutes. A manual review might take 24 hours. An account provisioning step might depend on a batch job that runs nightly.

[HOST] [sighs] But your synchronous REST APIs can't model that. So what do engineers do? They poll. They add webhooks. They add status fields to a shared database. They build little retry loops and timeout handlers and compensating transactions. And now you've got the worst of all worlds: a synchronous architecture that's desperately trying to simulate asynchronous behavior using synchronous tools.

[HOST] This is the **two-phase commit nightmare**. When something fails midway through your onboarding flow — say the account provisioning worked but the welcome email failed — what do you do? You need to either roll back the account provision (good luck doing that atomically across two separate services) or accept that you're in an inconsistent state and write special recovery code. And that recovery code becomes the most important and least tested code in your entire system.

[PAUSE]

---

[AD BREAK]
[VOICE:dave] [curious] Having trouble with distributed transactions leaving your data in an inconsistent state?
[VOICE:lily] [excited] Introducing FinagleDB™ — the database that's simultaneously committed AND rolled back, using proprietary quantum superposition technology!
[VOICE:dave] [deadpan] Your data is in every state at once. Schrödinger's row.
[VOICE:lily] [laughs] Finally, your inconsistent state is a *feature*, not a bug! Just tell your auditors it's eventual consistency!
[VOICE:dave] [whispers] FinagleDB™. If you can observe it, it's your fault.
[AD END]

---

## SEGMENT 4 — Opinion Corner: The Real Reason This Keeps Happening

[HOST] [clears throat] Okay, here's my hot take. And I say this with love for everyone who's built a distributed monolith, because I've absolutely done it too.

[HOST] The reason distributed monoliths keep happening isn't a technology problem. It's an organizational problem dressed up as a technology problem. (Source: Beware the Distributed Monolith, TechNode Global, 2025)

[HOST] Teams decompose their monolith by asking "what are the natural modules in our code?" But that's the wrong question. The right question is "what are the independently deployable, independently scalable units of *business capability*?" Those are often very different things.

[HOST] [sighs] In an onboarding system, the code might have modules like: user module, document module, notification module. But the *business capabilities* are things like: verify identity, provision account, communicate status. And the boundaries of those capabilities don't always align with how the code was originally organized.

[HOST] Domain-Driven Design gives us a tool for this — the Bounded Context. Each bounded context should have its own data, its own language, and its own deployment lifecycle. When you violate bounded context boundaries — when one service reaches into another service's data — that's where coupling enters.

[HOST] [curious] There's also an organizational dynamic at play. Synchronous APIs feel *safe* because they give you immediate feedback. You call a service, you get a response, you know if it worked. Asynchronous messaging feels *scary* because you fire and forget. How do you know if it worked? What happens if the consumer is down? What's the retry behavior?

[HOST] And so teams default to synchronous REST even when the problem domain is fundamentally asynchronous. KYC verification is asynchronous by nature — you submit the documents, you wait. Account provisioning is asynchronous by nature — you request it, it happens. The domain is screaming "use events!" and the architecture is stubbornly responding "but I like HTTP."

[HOST] [playfully] This is what I call the synchronous comfort blanket. And we're going to rip it off in this series.

[PAUSE]

---

## OUTRO

[HOST] [excited] So that's Part 1. We've diagnosed the patient. We know what a distributed monolith looks like, we know why teams build them, and we've seen exactly why onboarding workflows are the perfect storm for this kind of architectural pain.

[HOST] In Part 2, we're going to get into the medicine. We're going to talk about event sourcing fundamentals — what it actually means to model your system as a sequence of immutable events rather than mutable state — and we're going to see why Apache Kafka is the infrastructure backbone that makes this possible at scale.

[HOST] We'll talk about the Outbox Pattern, CQRS, event schemas, consumer groups, and all the good stuff. And we'll keep coming back to our onboarding example so everything stays grounded in something real.

[HOST] [cheerfully] If you're finding this useful, share it with someone on your team who keeps proposing adding more REST endpoints to fix your distributed monolith. That's the person who needs this series.

[HOST] I'm your host. This has been *Async Minded*. We'll see you in Part 2.

[MUSIC - OUTRO]

---

*Sources:*
- vFunction: "Distributed Monolith Architecture: What It Is, Why It Happens, and How to Fix It" (2025)
- InfoQ: "From Monolith to Event-Driven: Finding Seams in Your Future Architecture" (2025)
- Confluent Blog: "Toward a Functional Programming Analogy for Microservices"
- Medium/HeyJobs Tech: "Using Event-Driven Architecture to Break Apart a Monolith"
- TechNode Global: "Beware the Distributed Monolith: Why Agentic AI Needs Event-Driven Architecture" (2025)
- Growin: "Event Driven Architecture Done Right: How to Scale Systems with Quality in 2025"
- Apriorit: "Guide to KYC Software Development for FinTech" (2025)
- MerginIT: "Many Microservice Architectures Are Just Distributed Monoliths" (2025)
