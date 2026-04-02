# Kubernetes Mastery — Episode 3 of 5: Ingress Networking and Service Discovery

**Series:** Kubernetes Mastery (Episode 3 of 5)
**Target Audience:** Solution Architects and Lead Developers
**Estimated Runtime:** ~14 minutes (~1,850 words)
**Date:** April 2, 2026

---

*[MUSIC - INTRO]*

## INTRO

[HOST] [cheerfully] Welcome back to the Kubernetes Mastery series! I'm your host, and this is Episode 3 of 5 — today we are diving deep into Ingress Networking and Service Discovery. If you're a solution architect or a lead developer trying to figure out how traffic actually gets into your cluster and finds the right pods, this episode is going to be your roadmap.

[HOST] And let me tell you — the timing could not be better. [excited] The Kubernetes networking landscape just went through a massive earthquake. Ingress NGINX — the controller that powered roughly half of all cloud-native environments — was officially retired in March 2026. So we've got a lot of ground to cover: services, ingress controllers, the shiny new Gateway API, TLS, network policies, DNS, and how to route traffic to your Angular frontends and Spring Boot APIs. Let's get into it.

*[PAUSE]*

---

## SEGMENT 1 — The Big News: Ingress NGINX Is Gone, Long Live Gateway API

*[paper rustling]*

[HOST] [clears throat] Alright, let's start with the headline that shook the Kubernetes world. On January 29th, 2026, the Kubernetes Steering Committee and Security Response Committee issued a joint statement: Ingress NGINX would be retired in March 2026, with zero further bug fixes, security patches, or updates of any kind. (Source: Kubernetes Blog, January 29, 2026)

[HOST] [sighs] Now, this didn't come out of nowhere. The project had been maintained by just one or two people working in their spare time. For a piece of infrastructure that Datadog research says runs in about 50 percent of cloud-native environments, that's a terrifying bus factor. The steering committee put it bluntly: "Half of you will be affected. You have two months left to prepare." (Source: Kubernetes Blog, January 29, 2026)

[HOST] [excited] But here's the good news. The successor is already production-ready. The Kubernetes Gateway API — which hit GA back in October 2023 with version 1.0 and is now at v1.4 — is the official path forward. It's built on Custom Resource Definitions and it brings something Ingress never had natively: role-based ownership. Platform teams own the Gateway resource, application teams own their HTTPRoutes. That multi-tenancy model is a game-changer for organizations running dozens of microservices. (Source: Kubernetes Gateway API SIG Network)

[HOST] And the tooling is catching up fast. In March 2026, the Ingress2Gateway tool hit version 1.0, supporting over 30 common NGINX annotations — CORS, backend TLS, regex path matching, path rewrites, you name it. You can point it at your entire cluster and it'll spit out Gateway API manifests, warning you about anything it can't translate. (Source: Kubernetes Blog, March 20, 2026)

[HOST] [gasps] On the cloud provider front, AWS shipped GA support for Gateway API in its Load Balancer Controller — handling both L4 TCP/UDP via NLB and L7 HTTP/gRPC via ALB. And Microsoft announced Gateway API preview support in Azure AKS App Routing, with official NGINX Ingress support lasting through November 2026 for critical security patches only. (Source: InfoQ, March 2026; AKS Engineering Blog, March 2026)

[HOST] Meanwhile, Kubernetes 1.36 is launching April 22nd, 2026, and it's being called the first release where Gateway API is the default networking paradigm rather than Ingress. Big moment. (Source: Cloud Native Now, 2026)

*[PAUSE]*

---

[AD BREAK]
[VOICE:rachel] [excited] Hey there, cloud architects! Are your YAML files longer than your morning commute?
[VOICE:dave] [deadpan] Introducing YAMLShrink Pro — the world's first artisanal YAML compression service.
[VOICE:rachel] [laughs] We take your 500-line Ingress manifests and compress them into a single emoji!
[VOICE:dave] [whispers] Your entire production config? It's now a tiny little eggplant.
[VOICE:rachel] [cheerfully] YAMLShrink Pro — because nobody should have to scroll that much.
[VOICE:dave] [sarcastic] Side effects may include lost annotations and a sudden desire to rewrite everything in Pulumi.
[AD END]

---

## SEGMENT 2 — Services, Ingress, and Routing: The Architecture That Matters

*[paper rustling]*

[HOST] [clears throat] Alright, let's get architectural. Before traffic even hits an Ingress controller or a Gateway, it has to go through a Kubernetes Service. And understanding the three service types is fundamental for every solution architect.

[HOST] First up: ClusterIP. This is the default. It gives your service a virtual IP that's only reachable from inside the cluster. Your Spring Boot API pods? They probably talk to your database service over a ClusterIP. No external exposure, nice and secure.

[HOST] Next: NodePort. This opens a specific port on every node in your cluster and forwards traffic to your service. It works, but you're now exposing ports in the 30000 to 32767 range. [sarcastic] Very elegant for production, right? It's useful for development and testing, but in production you almost always want something in front of it.

[HOST] And that brings us to LoadBalancer. This tells your cloud provider to spin up an external load balancer — an AWS NLB, a GCP load balancer, an Azure load balancer — that routes traffic to your service. Simple, but expensive. One load balancer per service adds up fast when you've got 40 microservices.

[HOST] [excited] And that's exactly why Ingress exists — or existed, I should say. An Ingress resource lets you define routing rules so that one single load balancer can route to many backend services based on hostnames and paths. So `myapp.com/api` goes to your Spring Boot REST API service, and `myapp.com` serves your Angular static assets from an Nginx container. One load balancer, multiple backends, path-based routing.

[HOST] Now for IngressClass — this was added to solve the "which controller handles this Ingress" problem. If you're running both NGINX and Traefik in the same cluster — maybe during a migration — you set `ingressClassName: nginx` or `ingressClassName: traefik` on each Ingress resource so the right controller picks it up.

[HOST] [curious] But how does this look concretely with Angular and Spring Boot? Picture this: your Angular app is built and the static assets are served by an Nginx container on port 80. Your Spring Boot API runs on port 8080. You create two Kubernetes services — `frontend-svc` and `api-svc` — both ClusterIP. Then your Ingress or HTTPRoute sends `/api/*` to `api-svc:8080` and everything else to `frontend-svc:80`. Clean, simple, and your Angular app's `environment.ts` just points API calls to `/api` — the routing layer handles the rest.

[HOST] With Gateway API, this pattern gets even cleaner. You define a Gateway resource with a listener on port 443 with TLS, then attach two HTTPRoutes: one matching `/api` with a `PathPrefix` rule pointing to your Spring Boot service, and a catch-all route pointing to your Angular frontend. The platform team owns the Gateway, the frontend team owns their HTTPRoute, the backend team owns theirs. Beautiful separation of concerns.

*[PAUSE]*

---

## SEGMENT 3 — TLS, DNS, Network Policies, and the Stuff That Keeps You Up at Night

*[paper rustling]*

[HOST] [clears throat] Let's talk about the things that make or break production readiness. Starting with TLS termination.

[HOST] In most setups, TLS terminates at the Ingress controller or Gateway. Your users hit HTTPS, the controller decrypts it, and forwards plain HTTP to your backend services inside the cluster. That's fine for most cases. But if you need end-to-end encryption — say, for compliance — Gateway API v1.4 brought BackendTLSPolicy to the standard channel, letting you configure TLS between the gateway and your backend pods. (Source: Kubernetes Gateway API v1.4, November 2025)

[HOST] [excited] And for certificate management, cert-manager is still the gold standard. It automates Let's Encrypt certificate issuance and renewal. You create a Certificate resource, cert-manager talks to Let's Encrypt via ACME, gets your cert, stores it as a Kubernetes Secret, and your Gateway or Ingress references that Secret. Certificates rotate automatically. Traefik actually has this built in natively, which is one reason it's become so popular in 2026.

[HOST] Now, DNS and service discovery inside the cluster. [curious] Here's a fun fact that trips up a lot of people: kube-proxy isn't actually a proxy in the traditional sense. It just manages iptables or IPVS rules. The name is a holdover from when it used to run a userspace proxy. The real magic is CoreDNS. When your Spring Boot service needs to call another service — say, an order service — it just calls `http://order-svc.default.svc.cluster.local:8080`. CoreDNS resolves that to the ClusterIP, and the iptables or IPVS rules route it to a healthy pod. No service registry, no Eureka, no Consul needed for basic intra-cluster communication.

[HOST] [sighs] And finally, network policies. This is the microsegmentation piece that too many teams skip. By default, every pod in Kubernetes can talk to every other pod. That's terrifying from a security perspective. NetworkPolicy resources let you define allow rules — for example, only your API pods can talk to your database pods on port 5432, and only your frontend pods can talk to your API pods on port 8080. You need a CNI that supports network policies — Calico, Cilium, or Weave Net. Without one, your NetworkPolicy resources are just decorative YAML. [laughs]

*[PAUSE]*

---

[AD BREAK]
[VOICE:george] [nervous] I used to stay up all night manually rotating TLS certificates...
[VOICE:lily] [excited] Not anymore! Introducing CertPillow — the certificate manager that literally tucks your certs into bed!
[VOICE:george] [curious] Does it... does it actually renew them?
[VOICE:lily] [whispers] No. But it plays soothing whale sounds while your certificates expire.
[VOICE:george] [laughs] I'll take ten!
[VOICE:lily] [cheerfully] CertPillow — because sleep is more important than security! Just kidding. Please use cert-manager.
[AD END]

---

## SEGMENT 4 — Opinion Corner: Should You Migrate Right Now?

*[paper rustling]*

[HOST] [clears throat] Alright, opinion time. The community is buzzing with hot takes on the Ingress-to-Gateway-API migration, and I want to give you the balanced view.

[HOST] The strongest voice in the "migrate now" camp comes from the Kubernetes steering committee itself. Their message was unambiguous: "Choosing to remain with Ingress NGINX after its retirement leaves you and your users vulnerable to attack." (Source: Kubernetes Blog, January 2026)

[HOST] [playfully] But not everyone's hitting the panic button. One dev.to author put it perfectly: "Do not big bang this. I've seen that movie and it ends with a rollback and a postmortem full of screenshots." The practical advice? Run Ingress and Gateway API simultaneously. Start with one platform-owned Gateway. Migrate services one at a time with DNS or weight-based cutover. (Source: DEV Community, February 2026)

[HOST] NGINX's own blog offered a counterpoint worth hearing: if your use case is straightforward routing to a handful of services, switching to Gateway API might feel like overcomplicating a successful setup. But they acknowledged that for advanced needs — traffic splitting, multi-tenancy, cross-namespace routing — Gateway API is the better model. (Source: NGINX Community Blog)

[HOST] [calm] My take? If you're building anything new in 2026, use Gateway API from day one. If you have stable Ingress configs, start planning your migration now — use Ingress2Gateway to assess the gap — but don't rush it into production on a Friday afternoon. And watch out for what one commenter called "policy CRD sprawl" — Gateway API's extensibility model can recreate the annotation mess if you don't govern it.

*[PAUSE]*

---

## OUTRO & CALL TO ACTION

*[paper rustling]*

[HOST] [cheerfully] That's a wrap on Episode 3 of the Kubernetes Mastery series! Today we covered the three service types, the Ingress NGINX retirement, the rise of Gateway API, path-based routing for Angular and Spring Boot, TLS termination with cert-manager, DNS and service discovery with CoreDNS, and network policies for microsegmentation.

[HOST] [excited] Your homework: run `kubectl get pods --all-namespaces --selector app.kubernetes.io/name=ingress-nginx` on your clusters. If anything comes back, start planning your migration this week.

[HOST] Next episode — Episode 4 — we'll tackle Persistent Storage and StatefulSets. Until then, keep your clusters healthy and your YAML indentation consistent. [laughs]

[HOST] If you found this episode useful, share it with your team, drop us a review, and subscribe so you don't miss the rest of the series. See you next time!

*[MUSIC - OUTRO]*

---

## Sources

1. Kubernetes Blog — Ingress NGINX Statement (January 29, 2026)
2. Kubernetes Blog — Ingress2Gateway 1.0 Release (March 20, 2026)
3. Cloud Native Now — What to Expect From Kubernetes 1.36 (2026)
4. InfoQ — AWS Load Balancer Controller GA with Gateway API (March 2026)
5. AKS Engineering Blog — Gateway API Support for App Routing (March 2026)
6. DEV Community — Gateway API vs Ingress vs LoadBalancer: What to Use in 2026
7. Kubernetes Gateway API — v1.4 Release Notes (November 2025)
8. NGINX Community Blog — Ingress Controller to Gateway API
9. The New Stack — CNCF Retires the Ingress Nginx Controller
10. SiliconANGLE — Kubernetes Ingress Transition (March 2026)
11. Plural.sh — Kubernetes Service Discovery Guide
12. Nigel Poulton — Demystifying Kubernetes Service Discovery
