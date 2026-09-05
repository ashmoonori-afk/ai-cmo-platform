# Okara.ai vs AI CMO Platform — Feature Gap Analysis

> Date: 2026-09-01
> Sources: https://okara.ai/docs/introduction (official docs), makerstack.co/reviews/okara-review, aisofting.com/okara-ai-review-privacy-chat-cmo-agent, aiagentsquare.com/agents/okara-ai
> Scope: Okara **AI CMO** product only. Okara's second product (privacy-first multi-model chat) is a different category and out of scope.

## Status Legend

- **Present** — equivalent capability exists in this repo
- **Partial** — capability exists but generic/manual where Okara is dedicated/automated
- **Missing** — no equivalent; implemented by this gap plan
- **By design** — intentionally different platform principle, not a gap to close

## Feature Matrix

| # | Okara AI CMO feature | Repo equivalent (evidence) | Status | Gap action |
|---|----------------------|---------------------------|--------|------------|
| 1 | URL intake → strategy docs (marketing brief, competitor analysis, brand voice, growth playbook) | `playbooks/07-operations/client-onboarding.md`, `playbooks/01-strategy/gtm-motion-analysis.md`, `playbooks/01-strategy/positioning-map.md`, `clients/{client}/brand-guidelines.md` | Present | — |
| 2 | Competitor analysis | `playbooks/02-intelligence/competitor-monitoring.md`, `agents/competitor.md` | Present | — |
| 3 | SEO agent: audits, on-page fixes, keyword gaps | `playbooks/05-seo/seo-audit.md`, `playbooks/05-seo/keyword-research.md`, `agents/seo-specialist.md` | Present (on-demand, not continuous) | Covered by daily loop (#18) |
| 4 | GEO content optimization | `prompts/shared/geo-checklist.md`, GEO section in `agents/seo-specialist.md` | Present | — |
| 5 | GEO agent: brand-citation monitoring across ChatGPT / AI Overviews / Perplexity / Claude | — (checklist only, no visibility monitoring) | **Missing** | New `playbooks/05-seo/geo-visibility-monitor.md` |
| 6 | Reddit agent: thread discovery + reply drafts | — | **Missing** | New `agents/community-manager.md` + `playbooks/11-community/reddit-engagement.md` |
| 7 | Hacker News agent: Show HN drafts | — | **Missing** | `agents/community-manager.md` + `playbooks/11-community/hackernews-launch.md` |
| 8 | X (Twitter) agent: daily post drafts in brand voice | `playbooks/03-content/social-post.md` (generic multi-channel) | Partial | New dedicated `playbooks/03-content/x-twitter-daily.md` |
| 9 | LinkedIn agent: founder-voice ghostwriting | `playbooks/03-content/social-post.md` (generic) | Partial | New dedicated `playbooks/03-content/linkedin-founder-voice.md` |
| 10 | Articles writer agent: SEO articles | `playbooks/03-content/blog-article.md` | Present | — |
| 11 | Articles agent publishes directly to CMS | — (outputs are markdown files; publishing is approval-gated) | By design | Platform principle: publishing stays approval-gated (CLAUDE.md safety gate). No auto-publish. |
| 12 | UGC agent: video briefs + AI video clips | `playbooks/03-content/visual-content-guide.md` (photo shooting guide only) | **Missing** | New `playbooks/08-design/ugc-video-brief.md` |
| 13 | Coding agent: technical SEO fixes, GitHub PRs | — | **Missing** | New `agents/growth-engineer.md` + `playbooks/05-seo/technical-seo-fix.md` |
| 14 | Influencer agent: creator matching, outreach, payouts | — | **Missing** | New `playbooks/04-sales/influencer-campaign.md` (matching + outreach + briefs; payouts stay manual/approval-gated) |
| 15 | Link broker agent: backlink outreach | — | **Missing** | New `playbooks/05-seo/backlink-outreach.md` |
| 16 | Analytics: SEO health, backlinks, GEO visibility, traffic — auto-refreshed every 6h | `playbooks/06-analytics/ga-audit.md`, `playbooks/06-analytics/performance-report.md` (manual CSV input) | Partial | New daily digest step in daily loop (#18); live API refresh is By design (#17) |
| 17 | Native Google Search Console + GA API integrations | Manual file drop (CLAUDE.md §데이터 소스: "비공개 데이터는 사용자가 파일로 제공") | By design | Platform principle: private data enters via user-provided files. Not closing. |
| 18 | Autonomous daily operation: runs every day, no prompting, daily feed of opportunities + drafts | — (all workflows are user-invoked) | **Missing** | New `playbooks/00-chains/daily-cmo-loop.md` + `workflows/daily-cmo-loop.workflow.yaml` |
| 19 | Human-in-the-loop approval (drafts, not auto-publish) | `owner_gate` in workflows, approval-gated publishing (CLAUDE.md safety gate) | Present | — |
| 20 | Reviewer quality gate on all deliverables | `agents/reviewer.md`, `prompts/shared/gate-check.md` | Present | — |

## Summary

- Present: 8 / 20
- Partial: 4 / 20 (#8, #9, #10→CMS part by design, #16)
- Missing → implemented by `.omo/plans/okara-gap-plan.md`: 6 capabilities via 2 new agents, 10 new playbooks, 1 new workflow (#5, #6, #7, #12, #13, #14, #15, #18)
- By design (not closing): CMS auto-publish, live GSC/GA API, payout automation — all remain approval-gated per the platform's safety principles

## Design Notes

1. **Repo-native implementation**: this platform is markdown-driven (agents + playbooks + workflow YAML). Gap features are implemented as first-class platform citizens following existing conventions, not as external code.
2. **Okara's differentiator is autonomy** (#18): the daily-cmo-loop chain composes existing playbooks into a single daily runnable workflow with an owner approval gate — this closes the "runs every day, no prompting" gap within the platform's approval-gated philosophy.
3. **Community agents carry platform-risk warnings**: Reddit and HN punish AI-spam; the new playbooks bake in Okara's own documented caveat (human review, community-first tone, no link-dropping) as mandatory rules.
