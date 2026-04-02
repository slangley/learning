# Kubernetes Production Best Practices and Day 2 Operations
## Episode 5 of 5 — Kubernetes Mastery Series
### Date: 2026-04-02

---

*[MUSIC - INTRO]*

## INTRO

[HOST] [excited] Welcome back, architects and developers, to the fifth and FINAL episode of our Kubernetes Mastery series! I'm your host, and [clears throat] if you've been following along from episode one, you've gone from Kubernetes fundamentals all the way through networking, storage, and advanced deployment strategies. Today, we're tying it all together with the stuff that separates a weekend hobby cluster from a production-grade platform — Day 2 operations, security hardening, observability, GitOps, and cost optimization.

[HOST] Here's a stat that should get your attention: the CNCF's latest survey shows over ninety-three percent of organizations are now running or evaluating Kubernetes in production. But here's the thing — adoption is the easy part. The real test begins AFTER deployment, when the complexity of Day 2 operations sets in. (Source: CNCF Annual Survey, 2025)

[HOST] [playfully] So grab your favorite caffeinated beverage, because we've got a LOT to cover. Let's dive in.

*[PAUSE]*

---

## SEGMENT 1 — Autoscaling, Pod Disruption Budgets, and Resource Tuning for JVM Workloads

*[paper rustling]*

[HOST] Let's start with the bread and butter of production Kubernetes — making sure your Spring Boot services scale properly and stay available during disruptions.

[HOST] First up: the Horizontal Pod Autoscaler, or HPA. If you're still using HPA v1 with just CPU thresholds, it's time to upgrade your game. In 2026, the cleanest path for Spring Boot services is HPA v2 with external metrics. The trick is to combine CPU AND request-rate metrics together, because CPU alone reacts late — you're already drowning before it kicks in — while request rate gives you a fifteen to thirty second head start. (Source: TheLinuxCode, 2026)

[HOST] [curious] Now, what about event-driven workloads? If your Spring Boot services are doing a lot of async processing — consuming from Kafka, RabbitMQ, or SQS — then KEDA, the Kubernetes Event Driven Autoscaler, is your best friend. KEDA 2.19.0 just shipped with a new Kubernetes Resource Scaler and file-based authentication support, making it even more flexible. The beauty of KEDA is that it can scale from zero to N based on queue depth or event lag, which CPU-based autoscaling simply cannot do. (Source: GitHub KEDA Releases, 2026)

[HOST] And here's a hot development from KubeCon EMEA 2026 in Amsterdam — Akamas announced HPA-aware optimization that actually understands JVM-specific behavior. Their recommendation engine accounts for JVM warm-up and JIT compilation to prevent cold-start penalties. Instead of aggressive scaling that creates a bunch of cold pods, it favors stable, warmed-up pod configurations. [excited] That's a game changer for Spring Boot shops. (Source: Akamas, KubeCon EMEA 2026)

[HOST] [clears throat] Now, let's talk resource requests and limits — specifically for JVM workloads. This is where I see teams get burned constantly. Here's the golden rule: your memory REQUEST should account for heap PLUS metaspace PLUS thread stacks PLUS direct buffers. A common pattern is setting your JVM max heap to about seventy-five percent of your container memory limit, leaving headroom for off-heap usage. If you set the limit too close to the heap, the OOM killer will visit you at three AM — and trust me, it doesn't bring coffee.

[HOST] [sighs] And please, PLEASE set Pod Disruption Budgets. A PDB specifies the minimum number of pods that must remain available during voluntary disruptions like node upgrades or scaling events. For a Spring Boot service with three replicas, setting minAvailable to two or maxUnavailable to one ensures you never lose the whole fleet during a rolling update. Without PDBs, a cluster autoscaler or node upgrade can cheerfully evict all your pods at once. On GKE specifically, note that PDBs are only respected for up to one hour during node upgrades — after that, they're ignored. Plan accordingly. (Source: Medium, Practical Guide to PDBs, 2026)

*[PAUSE]*

---

[AD BREAK]
[VOICE:rachel] [excited] Hey there, are you a solution architect who's tired of YAML indentation errors ruining your day?
[VOICE:george] [deadpan] Introducing YAMLTherapy dot io — the world's first emotional support platform for Kubernetes configuration files.
[VOICE:rachel] [laughs] Our licensed YAML counselors will gently realign your spaces, validate your schemas, and whisper sweet nothings to your ConfigMaps.
[VOICE:george] [whispers] Side effects may include suddenly understanding Helm chart templates... and an uncontrollable urge to write Kustomize overlays.
[VOICE:rachel] [cheerfully] YAMLTherapy — because your manifests deserve to be heard.
[AD END]

---

## SEGMENT 2 — Health Probes, Security Hardening, and Observability

*[paper rustling]*

[HOST] Alright, let's talk about keeping your Spring Boot services healthy and your clusters locked down.

[HOST] Spring Boot Actuator gives you purpose-built endpoints for Kubernetes probes — slash actuator slash health slash liveness and slash actuator slash health slash readiness. But here's the critical best practice that trips up teams: your liveness probe should NEVER check external dependencies. If your liveness probe calls the database and the database is down, Kubernetes will restart your pod. Then the next pod starts, checks the database, it's still down, gets restarted — and now you've got a cascading failure across your entire fleet. Liveness should only answer the question: is this JVM process fundamentally broken? (Source: Spring Boot Documentation, Baeldung, 2026)

[HOST] [curious] And don't forget the startup probe for JVM workloads. Spring Boot apps can take thirty to ninety seconds to start, especially with heavy dependency injection. Configure a startup probe with a failure threshold of thirty and a period of five seconds — that gives you up to a hundred and fifty seconds of startup time before Kubernetes considers the pod failed. Once the startup probe succeeds, the liveness probe takes over. Also enable graceful shutdown with a thirty-second timeout to let in-flight requests drain before the pod disappears.

[HOST] [clears throat] Now, security. Here's a sobering fact: the CIS Kubernetes Benchmark documents over a hundred security checks, and a fresh cluster typically fails forty to sixty percent of them. Kubernetes is secure by design but insecure by default. (Source: SecureBin, 2026)

[HOST] The foundation is Pod Security Standards — the three profiles are Privileged, Baseline, and Restricted. For production workloads, you want Restricted on your application namespaces. That means all containers run as non-root, read-only root filesystem, all capabilities dropped, and no privilege escalation. Apply these at the namespace level using labels, and use audit mode first to see what would break before enforcing.

[HOST] For RBAC, the golden rules are: use RoleBindings over ClusterRoleBindings, never add service accounts to the system masters group, avoid wildcard permissions, and set automountServiceAccountToken to false by default. Review RBAC bindings quarterly — drift is real. (Source: Kubernetes.io RBAC Good Practices, 2026)

[HOST] [excited] On the observability front, Prometheus plus Grafana remains the de facto stack in 2026. But the big news is Grafana's new native cost and savings tabs released in February — they show spending across the past sixty days and potential savings for the next thirty, powered by OpenCost under the hood. For distributed tracing, OpenTelemetry is now the standard. Spring Boot's auto-instrumentation with the OTel Java agent gives you traces with just a six-line filter configuration and zero code changes. Feed those traces into Jaeger or Grafana Tempo and you've got full request lifecycle visibility. (Source: Grafana Labs, Feb 2026)

*[PAUSE]*

---

## SEGMENT 3 — GitOps, Secrets Management, and Multi-Environment Promotion

*[paper rustling]*

[HOST] GitOps has crossed the tipping point — over sixty-four percent of enterprises now report it as their primary delivery mechanism, and ninety-one percent of cloud-native organizations have adopted it. In 2026, the question isn't WHETHER to do GitOps, it's HOW to do it well. (Source: CNCF Survey, 2025)

[HOST] The two giants remain ArgoCD and Flux, both CNCF graduated projects. ArgoCD holds roughly sixty percent market share and just shipped version 3.3 with a killer feature — PreDelete hooks. For years, deleting applications in a GitOps workflow could leave orphaned resources or cause data loss in stateful applications. PreDelete hooks let you define cleanup jobs that must succeed before ArgoCD removes anything. That's a huge deal for database-backed services. (Source: ArgoCD 3.3 Release Notes, 2026)

[HOST] [curious] Flux, on the other hand, shines in edge computing and resource-constrained environments. Flux 2.8 introduced the ability to cancel ongoing health checks and immediately trigger a new reconciliation when a fix lands in Git. If you're running Kubernetes at the edge — manufacturing, telecom, IoT — Flux's minimal footprint and no inbound network requirements make it the clear choice. (Source: DEV Community, GitOps Standard 2026)

[HOST] Now, secrets management. Neither ArgoCD nor Flux manages secrets natively, so you need an external solution. The two main contenders are External Secrets Operator and Sealed Secrets. External Secrets Operator is the most operationally mature choice for teams already using a cloud secrets manager like AWS Secrets Manager, HashiCorp Vault, or Azure Key Vault. You rotate the value in your secrets manager and the operator picks it up automatically — no Git commit required. For regulated industries that need secrets committed to Git, Flux plus SOPS produces cleaner audit trails than ArgoCD's plugin approach.

[HOST] [excited] And here's the exciting frontier — multi-environment promotion. A tool called Kargo has emerged specifically to formalize environment promotion pipelines on top of ArgoCD and Flux. It supports auto-promotion in lower environments — dev pushes straight through — while requiring manual approval gates for production. If verification fails in staging, the freight isn't marked as verified and simply cannot be promoted downstream. It's a natural quality gate that prevents broken changes from reaching production. (Source: Burrell Tech, Kargo Introduction, 2026)

[HOST] For repo structure, the 2026 consensus is clear: folder-per-environment on a single Git branch beats branch-per-environment. All your environments — dev, staging, production — are folders in main. You want to know what's deployed? Just look at the folder. Simple, traceable, and it works beautifully with Kustomize overlays to reduce duplication.

*[PAUSE]*

---

[AD BREAK]
[VOICE:adam] [nervous] Uh, excuse me, is this the Kubernetes support group?
[VOICE:lily] [cheerfully] Welcome to CrashLoopBackoff Anonymous! Here at CLBA, we understand that your pods have feelings too.
[VOICE:adam] [crying] My deployment had forty-seven restarts last Tuesday and I didn't even NOTICE until the CEO asked why the website was down.
[VOICE:lily] [calm] That's okay, Adam. Step one is admitting you have no liveness probes. Step two is accepting that YAML indentation is four spaces, not tabs.
[VOICE:adam] [gasps] It's... it's been tabs this whole time?!
[VOICE:lily] [whispers] CrashLoopBackoff Anonymous — because OOMKilled is not a personality trait. Meetings every Tuesday at slash dev slash null.
[AD END]

---

## SEGMENT 4 — Cost Optimization and Series Wrap-Up

*[paper rustling]*

[HOST] Let's talk money — because running Kubernetes in production is not cheap, and most teams are leaving significant savings on the table.

[HOST] Tip number one: right-size your resource requests. Most teams over-provision by thirty to fifty percent because they set requests based on Day 1 estimates and never revisit them. Use Kubecost or OpenCost integrated with Prometheus and Grafana to see actual versus requested resources. In 2026, Grafana's new Kubernetes Monitoring feature even gives you AI-powered right-sizing recommendations. (Source: Grafana Labs, Feb 2026)

[HOST] [playfully] Tip number two: stop paying for idle environments. Schedule your dev and QA namespaces to scale down outside business hours. KEDA can scale to zero, remember? That alone can cut your non-production spend by forty to sixty percent.

[HOST] Tip number three: use spot or preemptible instances for fault-tolerant workloads. Combined with proper Pod Disruption Budgets and pod topology spread constraints, you can run batch jobs and stateless services on spot instances and save up to seventy percent compared to on-demand pricing.

[HOST] Tip number four: implement namespace-level resource quotas and limit ranges. Without them, a single runaway deployment can consume an entire node's resources. Tag everything — team, project, environment — so you can attribute costs and hold teams accountable.

[HOST] [sighs] And tip number five — the one nobody wants to hear — audit your persistent volumes. Orphaned PVCs from deleted deployments are silent budget killers. Set up a recurring job to find and clean them up.

*[PAUSE]*

[HOST] [clears throat] Now, as we wrap up this five-part Kubernetes Mastery series, let me leave you with a roadmap for continued learning.

[HOST] [excited] First, if you haven't already, get your Certified Kubernetes Administrator or CKA certification. It forces you to understand the internals that make Day 2 operations intuitive. Second, dive deeper into platform engineering — tools like Backstage for developer portals, Crossplane for infrastructure composition, and Kargo for promotion pipelines are defining the next wave of Kubernetes maturity.

[HOST] Third, explore the emerging world of agentic automation. In 2026, AI agents are acting as autonomous SREs — proactively detecting memory leaks, configuration drift, and silent failures before they become outages. This is the future of Day 2 operations, and getting familiar with these tools now puts you ahead of the curve. (Source: Qovery, 2026 Guide to Kubernetes Management)

[HOST] Fourth, attend KubeCon. The hallway track alone is worth the trip — the conversations you'll have with other practitioners will accelerate your learning faster than any tutorial.

[HOST] And fifth, contribute back. Open an issue on a CNCF project, write a blog post about a gnarly production problem you solved, or help a colleague get started. The cloud-native community is only as strong as its contributors.

[HOST] [calm] Thank you for joining me across all five episodes of the Kubernetes Mastery series. From pods and containers to production-grade Day 2 operations — you now have a comprehensive foundation to build, ship, and operate resilient systems at scale. Keep learning, keep shipping, and keep those pods healthy.

*[MUSIC - OUTRO]*

[HOST] [cheerfully] If you found this series valuable, subscribe, leave a review, and share it with your team. You can find all the episode notes and source links on our website. Until next time — may your deployments be boring and your SLOs be green. Happy shipping!

*[MUSIC - OUTRO FADE]*

---

## Sources

1. [CNCF Annual Survey - Kubernetes Adoption](https://www.cncf.io/blog/2026/01/19/top-28-kubernetes-resources-for-2026-learn-and-stay-up-to-date/)
2. [Qovery - 2026 Guide to Kubernetes Management & Day 2 Ops](https://www.qovery.com/blog/kubernetes-management)
3. [Akamas HPA-Aware Optimization - KubeCon EMEA 2026](https://akamas.io/akamas-introduces-hpa-aware-optimization-and-expands-its-autonomous-kubernetes-capabilities-at-kubecon-emea-2026/)
4. [KEDA 2.19.0 Release - GitHub](https://github.com/kedacore/keda/releases)
5. [Autoscaling GPU Workloads with KEDA and HPA](https://dasroot.net/posts/2026/02/autoscaling-gpu-workloads-keda-hpa/)
6. [Spring Boot Health Probes for Kubernetes](https://oneuptime.com/blog/post/2026-01-25-health-probes-kubernetes-spring-boot/view)
7. [Baeldung - Liveness and Readiness Probes in Spring Boot](https://www.baeldung.com/spring-liveness-readiness-probes)
8. [Kubernetes Security Best Practices 2026 - SecureBin](https://securebin.ai/blog/kubernetes-security-best-practices/)
9. [Pod Security Standards - Kubernetes.io](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
10. [RBAC Good Practices - Kubernetes.io](https://kubernetes.io/docs/concepts/security/rbac-good-practices/)
11. [Grafana - Costs and Savings in Kubernetes Monitoring](https://grafana.com/whats-new/2026-02-10-costs-and-savings-in-kubernetes-monitoring/)
12. [ArgoCD vs FluxCD in 2026 - DEV Community](https://dev.to/mechcloud_academy/the-gitops-standard-in-2026-a-comparative-research-analysis-of-argocd-and-fluxcd-46d8)
13. [GitOps Guide 2026 - ArgoCD and Flux](https://www.askantech.com/gitops-infrastructure-management-continuous-deployment-argocd-flux/)
14. [Introduction to Kargo - Burrell Tech](https://burrell.tech/blog/kargo/)
15. [Kubernetes Best Practices for Production 2026 - Qovery](https://www.qovery.com/guides/kubernetes-best-practices)
16. [Pod Disruption Budget Practical Guide - Medium](https://medium.com/@bregman.arie/pod-disruption-budget-the-practical-guide-1eb4ff78b6c9)
17. [Pod Security Standards Enforcement](https://oneuptime.com/blog/post/2026-02-09-pod-security-standards-enforcement/view)
