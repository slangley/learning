# Kubernetes Mastery — Spring Cloud Kubernetes Deep Dive
**Episode: Spring Boot + Spring Cloud Kubernetes**
*Recorded: 2026-04-20*

---

*[MUSIC - INTRO]*

## INTRO

[HOST] [calm] Welcome back to Kubernetes Mastery. I'm your host, and this is the episode where we stop treating Spring Boot and Kubernetes as two separate concerns and look at how they were actually designed to work together.

[HOST] If you've been following the series, you've covered cluster anatomy, workload objects, Helm, networking with Gateway API, sidecar patterns, and production operations. We've referenced Spring Boot throughout — health probes wired to Actuator, JVM tuning for container memory limits, graceful shutdown with preStop hooks. But we haven't yet talked about Spring Cloud Kubernetes as a dedicated integration layer.

[HOST] [curious] Today we go deep. We're covering the Spring Cloud Kubernetes project — what it gives you, how the two client backends differ, how it integrates ConfigMaps and Secrets directly into your application properties, how service discovery works without a Eureka server, and what the broader ecosystem of Kubernetes Java libraries looks like from a Spring Boot perspective.

[HOST] [calm] This is a technical episode. We'll look at dependency declarations, configuration properties, and some code-level patterns. Let's get into it.

*[PAUSE]*

---

## SEGMENT 1 — Spring Cloud Kubernetes Architecture

[HOST] [calm] Spring Cloud Kubernetes, often abbreviated SCK, is a project under the Spring Cloud umbrella. Its purpose is to replace the infrastructure primitives you'd normally get from Netflix OSS — service registries, distributed config servers, client-side load balancers — with native Kubernetes equivalents.

[HOST] The core idea is that when you're already running on Kubernetes, you don't need a separate Eureka server to do service discovery. Kubernetes already knows which pods are running and what endpoints they expose. Similarly, you don't need a separate Spring Cloud Config Server to serve configuration. Kubernetes ConfigMaps and Secrets are already there. Spring Cloud Kubernetes bridges those Kubernetes primitives into the standard Spring Cloud interfaces your application code already uses.

[HOST] [curious] Now, the first thing to understand is that SCK ships with two client backends, and you choose one at dependency time.

[HOST] [calm] The first option is the Fabric8 backend. You bring this in with the `spring-cloud-starter-kubernetes-fabric8` starter. Fabric8 is a mature, independently maintained Kubernetes Java client that predates a lot of the official tooling. It has a rich DSL, strong OpenShift support, and has been used in production clusters for years.

[HOST] The second option is the official Kubernetes Java client backend. That's `spring-cloud-starter-kubernetes-client`. This uses the `io.kubernetes:client-java` library, which is the officially maintained Java client generated from the Kubernetes OpenAPI spec. The Spring Cloud Kubernetes team maintains adapters for both, and they're functionally equivalent from the application's perspective. The choice mostly comes down to what's already in your dependency tree and which community you're more comfortable supporting.

[HOST] [matter-of-fact] For new Spring Boot 3.x projects in 2026, the official client backend tends to be the default recommendation in the documentation. Fabric8 has slightly richer operator-building ergonomics, which we'll revisit in the advanced segment. Either way, you pick one and don't mix them.

[HOST] [calm] Beyond the client choice, there's an important operational requirement: RBAC. Your application runs as a Kubernetes ServiceAccount, and SCK needs that account to have API access to read the resources it's bridging.

[HOST] At minimum, you'll need a Role that grants `get` and `list` on `configmaps` and `endpoints`, and a RoleBinding that attaches it to your ServiceAccount. If you're enabling secrets monitoring — which is opt-in and disabled by default for good reason — you'll need the same permissions on `secrets`.

[HOST] [curious] A common mistake is deploying an SCK application without the RBAC and wondering why config isn't loading or discovery isn't returning any services. The startup logs will tell you clearly — look for 403 responses from the Kubernetes API. The fix is always a missing Role or RoleBinding, not a bug in your code.

[HOST] [calm] One more architectural note before we move on. Spring Cloud Kubernetes 3.x, released as part of the Spring Cloud 2025.0 train — the most recent being 3.3.2 from April 2026 — requires Spring Boot 3.x and Java 17 as a baseline. If you're still on Spring Boot 2.x, you're on the 2.x SCK branch, and many of the features we'll discuss today work differently or don't exist yet. (Source: spring.io blog, April 2, 2026)

*[PAUSE]*

---

[AD BREAK]
[VOICE:dave] [matter-of-fact] Having trouble getting your RBAC roles right? Introducing RBACulator Pro — the only tool that reads your mind and generates perfect Kubernetes role manifests every time.
[VOICE:lily] [sarcastic] It's just a guy named Kevin who writes YAML really fast.
[VOICE:dave] [deadpan] Kevin has a 97 percent accuracy rate and charges by the binding.
[VOICE:lily] RBACulator Pro. Because reading the docs is for quitters.
[VOICE:dave] [whispers] Kevin is not liable for production outages.
[AD END]

*[PAUSE]*

---

## SEGMENT 2 — Config from the Cluster

[HOST] [calm] Let's talk about configuration. This is one of the most immediately useful things Spring Cloud Kubernetes provides: the ability to read Kubernetes ConfigMaps and Secrets directly as Spring property sources.

[HOST] To enable it, you bring in the config starter — either `spring-cloud-starter-kubernetes-fabric8-config` or `spring-cloud-starter-kubernetes-client-config` depending on your backend choice. With that on the classpath, SCK will look for a ConfigMap whose name matches your application's `spring.application.name` in the same namespace where the pod is running.

[HOST] [curious] The ConfigMap just needs a key named `application.properties` or `application.yaml`, and SCK will load that data into the Spring Environment alongside your local property files. It's hierarchical — the ConfigMap source has lower precedence than your packaged `application.yml` by default, but you can adjust the ordering.

[HOST] [calm] What makes this genuinely useful is profile awareness. You can have a ConfigMap named `my-service` that holds base configuration, and then a ConfigMap named `my-service-dev` that holds dev overrides. When your Spring active profile is `dev`, SCK loads both and merges them, exactly as you'd expect from standard Spring profile mechanics. You get the full profile composition system, but sourced from the cluster's ConfigMap API rather than a config server or environment variables.

[HOST] [paper rustling] Now let's talk secrets. By default, SCK does not read Secrets into the Spring Environment. You have to opt in explicitly with `spring.cloud.kubernetes.secrets.enabled=true`. This is intentional. Secrets in Kubernetes are not actually encrypted at rest by default — they're base64-encoded etcd entries — so the project takes a conservative position and requires you to consciously enable the integration.

[HOST] [calm] When you do enable it, SCK will look for a Secret matching your application name, same as it does for ConfigMaps. The Secret's data entries are base64-decoded and loaded as properties. This lets you keep database passwords and API keys out of your Docker image and away from your source code, resolved at pod start time from the cluster's Secrets store.

[HOST] [curious] The more interesting feature is hot reload. Spring Cloud Kubernetes can watch for changes to ConfigMaps and Secrets and re-inject them into your running application without requiring a pod restart. You enable this with `spring.cloud.kubernetes.reload.enabled=true`.

[HOST] [calm] There are two reload modes. Event mode, which is the default, uses a Kubernetes API watch — a long-lived websocket connection — to receive change notifications in near real-time. When a change event comes in, SCK checks whether the relevant values actually changed, and if so, triggers a refresh. Polling mode is the alternative: SCK re-reads ConfigMaps and Secrets on an interval, defaulting to fifteen seconds. Polling is simpler and more reliable in environments where websocket connections are unreliable, but it introduces latency proportional to the interval.

[HOST] There are also three reload strategies. The default is `refresh`, which only refreshes beans annotated with `@ConfigurationProperties` or `@RefreshScope`. This is the least disruptive — no restarts, just property rebinding. The second is `restart_context`, which restarts the Spring Application Context. The third is `shutdown`, which terminates the JVM and relies on Kubernetes to restart the pod. Most teams stay with `refresh` for configuration updates and reserve the others for cases where the changed property affects beans that can't be refreshed in-place.

[HOST] [calm] One configuration anti-pattern worth calling out: do not put your `spring.cloud.kubernetes.reload.*` properties inside a ConfigMap that SCK is watching. If those properties change and SCK triggers a reload using the new configuration, you get undefined behavior. Keep reload configuration in your pod's environment variables or your packaged application properties.

[HOST] [paper rustling] Finally, there's a related component called the Spring Cloud Kubernetes Configuration Watcher. This is a separate Spring Boot application you deploy into your cluster whose job is to watch ConfigMaps and Secrets and send refresh signals to other applications via Spring Cloud Bus or direct HTTP calls to Actuator's `/actuator/refresh` endpoint. If you have many microservices that all need to reload when a single shared ConfigMap changes, the Configuration Watcher is the component that coordinates that fan-out. (Source: Spring Cloud Kubernetes docs, docs.spring.io)

*[PAUSE]*

---

## SEGMENT 3 — Service Discovery and Load Balancing

[HOST] [calm] With configuration covered, let's move to service discovery. In previous episodes we looked at how CoreDNS handles service resolution — you call `my-service.my-namespace.svc.cluster.local` and DNS resolves it to the ClusterIP. That works, and for simple request-response between services, it's often all you need.

[HOST] Spring Cloud Kubernetes goes a step further. It implements the standard Spring Cloud `DiscoveryClient` interface backed by the Kubernetes Endpoints API. Instead of resolving DNS to a single ClusterIP and relying on kube-proxy to distribute traffic, the SCK discovery client reads the individual pod endpoints directly from the Kubernetes API and makes them available to your application.

[HOST] [curious] Why would you want that? Two reasons. First, you can integrate with Spring Cloud LoadBalancer — the Spring-native replacement for Netflix Ribbon — and implement load balancing algorithms in your application process. Round-robin is the default, but you can wire in custom load balancing policies, health-aware routing, or zone-aware routing without changing your cluster infrastructure.

[HOST] [calm] Second, the DiscoveryClient gives you access to pod metadata — labels, annotations, namespace, node name — that is invisible at the DNS level. If your service has instances with a `region=us-east` label and instances with `region=us-west`, you can write load balancer logic that reads those labels and routes accordingly. That's a level of routing intelligence you cannot get from a ClusterIP.

[HOST] [matter-of-fact] The dependency for this is `spring-cloud-starter-kubernetes-fabric8-loadbalancer` or the client-equivalent. With it on the classpath and a `@LoadBalanced` RestTemplate or WebClient configured, SCK intercepts outgoing calls to service names and resolves them using the Kubernetes Endpoints API rather than DNS.

[HOST] [calm] Namespace scoping deserves attention. By default, the DiscoveryClient only sees services in the namespace where your application is running. If you have a multi-namespace architecture, you configure `spring.cloud.kubernetes.discovery.all-namespaces=true` to enable cross-namespace discovery. That requires broader RBAC — your ServiceAccount will need list and watch permissions on Endpoints across namespaces, so think carefully before enabling it in security-sensitive environments.

[HOST] [curious] You can also use label selectors to filter which services appear in discovery results. If your cluster has a mix of public-facing and internal services and you don't want your application discovering everything, you add a label like `spring-boot-service=true` to the services that should participate, and configure SCK to filter by that label. This is a useful pattern in larger clusters where the Endpoints list can be noisy.

[HOST] [calm] On the health indicator side, SCK automatically contributes a `kubernetes` health indicator to Spring Boot Actuator. This indicator reflects whether the application can successfully reach the Kubernetes API — it's essentially a liveness check for the SCK integration itself. If the API is unreachable, this indicator goes DOWN, which you can use as a signal in your overall readiness probe logic. (Source: Spring Cloud Kubernetes DiscoveryClient docs, docs.spring.io)

*[PAUSE]*

---

[AD BREAK]
[VOICE:rachel] [calm] Tired of writing RBAC manifests, ConfigMap reload policies, and namespace selectors by hand?
[VOICE:adam] [deadpan] Introducing YAML Feelings — the journaling app for Kubernetes operators.
[VOICE:rachel] Just describe your emotional relationship with your cluster. YAML Feelings generates the manifests.
[VOICE:adam] [sarcastic] It once generated a ClusterRoleBinding because a user said they felt misunderstood.
[VOICE:rachel] YAML Feelings. The cluster doesn't care. But we do.
[AD END]

*[PAUSE]*

---

## SEGMENT 4 — Industry Standard Libraries

[HOST] [calm] Let's step back from Spring Cloud Kubernetes specifically and look at the broader landscape of Kubernetes Java libraries you'll likely encounter in a Spring Boot shop.

[HOST] The most widely used is the Fabric8 Kubernetes Client — `io.fabric8:kubernetes-client`. This is an independent project that predates the official Kubernetes Java client by several years. Fabric8 7.4 is the current release as of early 2026, and it brings a fluent DSL that lets you interact with the Kubernetes API in a way that feels fairly natural in Java. Creating a pod, listing deployments, or reading a ConfigMap is a few lines of chained method calls rather than raw HTTP.

[HOST] [curious] What Fabric8 excels at is its Watch and Informer APIs. A Watch is a long-lived HTTP connection to the Kubernetes API server that streams change events — added, modified, deleted — for a resource type. An Informer builds on top of that: it maintains a local in-memory cache of the resource state, backed by a reflector that resynchronizes periodically, so your application can read resource state from memory rather than making API calls on every query.

[HOST] [calm] The practical pattern looks like this: you create a SharedInformerFactory, start informers for the resource types you care about — say, ConfigMaps and Services — and register event handlers that fire when those resources change. The informer keeps the cache warm, you read from the cache, and your application stays in sync with cluster state without hammering the API server. This is the same mechanism that Kubernetes controllers themselves use internally.

[HOST] [matter-of-fact] The official Kubernetes Java client — `io.kubernetes:client-java` — takes a different approach. It's generated from the Kubernetes OpenAPI spec, so the model classes are comprehensive and always up to date with the latest API version. The trade-off is verbosity: the generated code is less fluent than Fabric8's DSL, and building complex watch or informer logic requires more boilerplate. The Spring Cloud Kubernetes team maintains an SCK adapter for both, but if you need to write custom operator logic in a Spring Boot application, Fabric8 tends to feel more ergonomic.

[HOST] [curious] Speaking of testing — Testcontainers has a k3s module that deserves attention. k3s is a lightweight, production-grade Kubernetes distribution that starts in seconds inside a Docker container. The Testcontainers k3s module spins up a real k3s cluster as part of your test lifecycle. This means you can write JUnit integration tests that actually deploy your Kubernetes resources, apply ConfigMaps, and assert on pod behavior — all running locally or in CI with no external cluster dependency.

[HOST] [calm] The pattern is: annotate your test with `@Testcontainers`, declare a `K3sContainer` as a static field, extract the kubeconfig from the running container, and point your Fabric8 or official client at it. Your test then has a real API server to interact with. This is particularly valuable for testing operator logic, custom controllers, or any code that speaks the Kubernetes API directly. (Source: Testcontainers k3s module docs, java.testcontainers.org)

[HOST] For the inner development loop — the cycle of edit, build, deploy, observe — Skaffold remains the standard tool in the Java-on-Kubernetes world. Skaffold watches your source files, triggers incremental builds, builds a container image, pushes it to a local registry, and applies the updated manifests to your local cluster. For Spring Boot specifically, you configure Skaffold to use Jib for image building, which produces layers that cache the dependency layer separately from your application classes. Rebuild times for a code change drop from a full Docker build to rebuilding just the application layer — typically under ten seconds.

[HOST] [calm] The alternative worth knowing is Tilt. Tilt takes a similar approach but uses a Starlark-based configuration file called a Tiltfile that gives you more control over the inner loop. It has a browser-based dashboard that shows build logs, pod logs, and resource status in one place. Both Skaffold and Tilt have active communities; Skaffold tends to be more popular in teams that already have GKE or Artifact Registry infrastructure, while Tilt has a broader multi-cloud following.

[HOST] [curious] On the observability side, Micrometer is the standard metrics facade for Spring Boot. We covered OTel auto-instrumentation in the production episode, but Micrometer has a specific feature worth calling out in the Kubernetes context: the `k8s` tag set. If you configure `management.observations.key-values.k8s.namespace=${NAMESPACE}` and similar environment variable injections from the Downward API, your metrics carry namespace, pod name, and node name as dimensions. When those metrics land in Prometheus and Grafana, you can filter dashboards by pod instance or compare performance across nodes directly — without needing to correlate logs separately. (Source: Micrometer documentation, micrometer.io)

*[PAUSE]*

---

## SEGMENT 5 — Advanced Patterns

[HOST] [calm] Let's finish with two patterns that come up in more mature Spring Boot Kubernetes deployments: leader election and lightweight operator logic.

[HOST] Spring Cloud Kubernetes includes a leader election module backed by Kubernetes LeaseLock — the same primitive that the Kubernetes control plane itself uses to elect controller managers. The pattern is straightforward: you declare a `@ConditionalOnLeader` annotated component or implement the `LeaderEventPublisher` interface, and SCK handles the Lease renewal and failover. Only the elected instance runs the annotated code; if that pod dies, another candidate acquires the lease within the configured lease duration.

[HOST] [matter-of-fact] This is useful for any task that should run in exactly one instance across a deployment — periodic data exports, scheduled reconciliation jobs, or cache warming processes that are expensive to run in parallel. It's preferable to using a Kubernetes CronJob for these because you keep the logic inside your existing application and avoid cold-start latency.

[HOST] [calm] The second pattern is building lightweight operator or controller behavior in Spring Boot using the Fabric8 Informer API. A Kubernetes operator is just a controller that watches for custom or standard resources and reconciles the actual state of the cluster toward a desired state. Most operators are built with Go and controller-runtime, but for teams deeply invested in the Java ecosystem, Fabric8 provides the building blocks to do this in a Spring Boot application.

[HOST] [curious] The pattern: use a SharedInformerFactory to watch a Custom Resource or a standard resource like a ConfigMap with a specific annotation. Register a ResourceEventHandler that fires on add, update, and delete events. In the handler, run your reconciliation logic — perhaps creating child resources, updating status subresources, or calling an external API. Wrap the whole thing in a Spring component with proper lifecycle management so the informer starts and stops cleanly.

[HOST] [calm] This approach works well for internal operator logic that doesn't need to be independently deployed or shared across teams. If your operator grows in complexity, the recommendation is to graduate to a dedicated Go-based operator using operator-sdk or kubebuilder — the tooling ecosystem there is richer and the operational patterns are better documented. But for team-internal automation that lives alongside your application, a Spring Boot operator is a reasonable choice.

[HOST] [matter-of-fact] One honest trade-off to name: Spring Cloud Kubernetes adds complexity and RBAC surface area. For teams running a small number of services in a well-understood cluster, plain DNS-based service resolution and environment-variable based configuration is often simpler and easier to debug. The SCK integration shines when you need dynamic configuration reload, label-aware load balancing, or you're building platform tooling that needs to speak the Kubernetes API. Reach for it deliberately, not by default.

*[PAUSE]*

---

## OUTRO & CALL TO ACTION

*[MUSIC - OUTRO]*

[HOST] [calm] That covers the Spring Cloud Kubernetes layer: client backends, ConfigMap and Secret integration with hot reload, DiscoveryClient and LoadBalancer, the Java library ecosystem with Fabric8, Testcontainers k3s for integration testing, Skaffold for the inner loop, and the advanced patterns of leader election and lightweight operator logic.

[HOST] For homework: take an existing Spring Boot service that reads from a ConfigMap via volume mount and migrate it to use the SCK ConfigMap PropertySource with reload enabled. Observe what happens in the Actuator `/actuator/env` endpoint when you `kubectl edit` the ConfigMap. That hands-on test will cement the reload behavior better than any documentation.

[HOST] [calm] Next episode we'll be looking at Kubernetes RBAC in depth — Role and ClusterRole design, service account best practices, and how to audit what your running workloads can actually do in the cluster. Until then, thanks for listening to Kubernetes Mastery.

*[MUSIC - OUTRO FADE]*

---

## Episode Metadata

**Sources:**
- Spring Cloud 2025.0.2 (Northfields) release announcement — spring.io/blog, April 2, 2026
- Spring Cloud Kubernetes ConfigMap PropertySource docs — docs.spring.io/spring-cloud-kubernetes
- Spring Cloud Kubernetes PropertySource Reload docs — docs.spring.io/spring-cloud-kubernetes
- Spring Cloud Kubernetes DiscoveryClient docs — docs.spring.io/spring-cloud-kubernetes
- Fabric8 Kubernetes Client 7.4 release — blog.marcnuri.com
- Fabric8 Watch and Informer System — deepwiki.com/fabric8io/kubernetes-client
- Testcontainers K3s Module — java.testcontainers.org/modules/k3s
- Leveraging Spring Cloud Kubernetes — medium.com/@AlexanderObregon
- Spring Cloud Kubernetes Discovery Client — deepwiki.com/spring-cloud
- Micrometer documentation — micrometer.io
