"""Brief §4c step 6: create one bank, retain one fact, recall it back. Run BEFORE anything else in LIVE MODE."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings  # noqa: E402

if not settings.hindsight_api_key:
    sys.exit("HINDSIGHT_API_KEY is not set in .env — nothing to smoke-test.")
from hindsight_client import Hindsight  # noqa: E402

bank = f"{settings.bank_prefix}smoke-test"
c = Hindsight(base_url=settings.hindsight_base_url, api_key=settings.hindsight_api_key)
print("create_bank:", c.create_bank(bank_id=bank, name="smoke test"))
print("retain:", c.retain(bank_id=bank, content="The smoke-test client prefers phased rollouts.", context="smoke test"))
time.sleep(2)
r = c.recall(bank_id=bank, query="What rollout style does the smoke-test client prefer?")
print("recall:", [x.text for x in r.results])
print("reflect:", c.reflect(bank_id=bank, query="Summarize what you know in one sentence.").text)
if settings.groq_api_key:
    from app import llm
    print("groq:", llm.chat([{"role": "user", "content": "Reply with exactly: SAFE"}], max_tokens=10))
c.delete_bank(bank)
print("OK - Hindsight round-trip works.")
