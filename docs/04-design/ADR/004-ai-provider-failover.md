# ADR-004: Multi-provider AI Failover Chain

## Status: Accepted

## Context

The application requires AI-powered health insights (FR-022 to FR-029):
- Generate insights from health records
- Explain lab results in plain language
- Multi-turn conversational Q&A
- Trend detection across records
- Drug interaction checking

Key requirements:
- Default provider: Google Gemini 2.5 Flash
- Ordered fallback chain: Groq → OpenRouter → Ollama Cloud → Ollama Local
- Use free tiers only
- Switch on rate-limit or quota exhaustion (FR-029)
- Transparent failover to user
- Append medical disclaimer to every response (FR-028)

Constraints:
- Self-hosted deployment (no guaranteed internet reliability)
- Personal use (budget-conscious, free tiers preferred)
- Health data sensitivity (provider selection affects data privacy)

## Decision

Implement **ordered multi-provider failover chain** with automatic retry logic.

**Provider order:**
1. **Google Gemini 2.5 Flash** (default) — Best quality/speed balance, generous free tier
2. **Groq** — Fast inference, free tier available
3. **OpenRouter** — Aggregator with multiple models, fallback option
4. **Ollama Cloud** — Hosted open-source models
5. **Ollama Local** — Self-hosted, last resort (requires local setup)

**Failover logic:**
```python
# app/services/ai_service.py
PROVIDERS = [
    GoogleGeminiProvider(),
    GroqProvider(),
    OpenRouterProvider(),
    OllamaCloudProvider(),
    OllamaLocalProvider(),
]

async def generate_insight(self, prompt: str, context: str) -> AIInsight:
    last_error = None
    
    for provider in PROVIDERS:
        try:
            response = await provider.generate(
                prompt=prompt,
                context=context,
                max_tokens=2048
            )
            # Success — log provider and return
            return AIInsight(
                response=response,
                provider_used=provider.name,
                disclaimer=self.DISCLAIMER
            )
        
        except RateLimitError as e:
            last_error = e
            logger.warning(f"Provider {provider.name} rate limited, trying next")
            continue
        
        except ServiceUnavailableError as e:
            last_error = e
            logger.warning(f"Provider {provider.name} unavailable, trying next")
            continue
        
        except APIError as e:
            # Non-retryable error — fail immediately
            logger.error(f"Provider {provider.name} error: {e}")
            raise
    
    # All providers exhausted
    raise AIServiceError(f"All AI providers failed. Last error: {last_error}")
```

**Retry policy:**
- Retry on: `429 Too Many Requests`, `503 Service Unavailable`, `504 Gateway Timeout`
- Do NOT retry on: `400 Bad Request`, `401 Unauthorized`, `500 Internal Error`
- Maximum retries: 3 per provider (then move to next provider)
- No backoff delay (immediate failover for responsiveness)

**Context building:**
```python
async def _build_member_context(self, member_id: UUID) -> str:
    """Build medical history context for AI prompt."""
    member = await self._get_member(member_id)
    records = await self._get_recent_records(member_id, limit=10)
    
    context = f"""
Patient: {member.first_name} {member.last_name}
Date of Birth: {member.date_of_birth}
Medical History: {member.medical_history_summary}

Recent Health Records:
"""
    for record in records:
        context += f"- {record.record_date}: {record.record_type} - {record.diagnosis or record.clinical_data[:100]}...\n"
    
    return context
```

## Consequences

**Positive:**
- **High availability** — Service continues even if primary provider fails
- **Cost optimization** — Free tiers used first, paid tiers only if needed
- **Transparency** — User doesn't know which provider responded (logged internally)
- **Privacy option** — Ollama Local keeps data on-premises (last resort)
- **Provider flexibility** — Easy to add/remove providers without code changes

**Negative:**
- **Variable response quality** — Different providers may give different quality answers
- **Inconsistent latency** — Ollama Local slower than cloud providers
- **Complex error handling** — Must handle each provider's error format
- **Debugging difficulty** — Harder to reproduce issues (provider-dependent)
- **Token limit variance** — Each provider has different context windows

**Mitigations:**
- Response quality: Log `provider_used` for each insight, monitor quality patterns
- Latency: Set per-provider timeouts (10s cloud, 30s local)
- Error handling: Abstract provider interface with unified exception types
- Debugging: Include `provider_used` in AIInsight record for traceability
- Token limits: Truncate context to lowest common denominator (32K tokens)

**Cost implications:**
| Provider | Free Tier | Paid Tier |
|----------|-----------|-----------|
| Google Gemini | 60 requests/min | $0.075 / 1M input tokens |
| Groq | 30 requests/min | $0.19 / 1M input tokens |
| OpenRouter | Varies by model | Pass-through pricing |
| Ollama Cloud | Limited | Subscription |
| Ollama Local | Unlimited | Hardware cost only |

**Expected cost:** $0/month for typical household usage (under 100 AI calls/day)

## Alternatives Considered

### Single provider (Google Gemini only)
- **Pros:** Simplest implementation, consistent quality
- **Cons:** Single point of failure, rate limiting affects all users
- **Verdict:** Rejected — availability requirement (FR-029) mandates failover

### User-configurable provider selection
- **Pros:** User controls which providers to use, can bring own API keys
- **Cons:** Complex UX, users may misconfigure
- **Verdict:** Deferred to v2 — v1 uses system-managed failover

### Load balancing across providers
- **Pros:** Distributes cost, reduces rate limit risk
- **Cons:** Complex implementation, inconsistent response quality
- **Verdict:** Rejected — failover simpler than load balancing for v1

### Cache AI responses
- **Pros:** Reduces API calls, faster response for repeated queries
- **Cons:** Stale insights, cache invalidation complexity
- **Verdict:** Deferred to v2 — can add semantic caching layer later

### Local-only AI (Ollama)
- **Pros:** Complete privacy, no API costs, no rate limits
- **Cons:** Requires powerful hardware, slower, lower quality models
- **Verdict:** Rejected as default — kept as last-resort fallback

---

**Date:** 2026-04-02  
**Author:** Principal Engineer (AI)  
**Reviewers:** Specification Review Gate
