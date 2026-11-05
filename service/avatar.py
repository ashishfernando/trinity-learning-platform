"""Avatar adapters. The session service talks to this interface only, so swapping
vendors (or running text-only) does not touch the rest of the code.

TavusAdapter is a stub on purpose: verify the current Tavus API (conversation
creation, custom LLM / OpenAI-compatible endpoint settings, webhooks) against their
docs before filling it in. Do not copy endpoint shapes from memory.
"""

class AvatarAdapter:
    def start(self, persona: dict, system_prompt: str, session_id: int) -> str | None:
        """Start a video conversation; return the vendor conversation id (or None)."""
        raise NotImplementedError

    def stop(self, conversation_id: str) -> None:
        raise NotImplementedError


class TextOnlyAdapter(AvatarAdapter):
    def start(self, persona, system_prompt, session_id):
        return None

    def stop(self, conversation_id):
        return None


class TavusAdapter(AvatarAdapter):
    """TODO: needs TAVUS_API_KEY and persona.replica_id (with a consent record)."""
    def start(self, persona, system_prompt, session_id):
        if not persona.get("replica_id") or not persona.get("replica_consent_id"):
            raise ValueError("No replica without a stored consent record")
        raise NotImplementedError("Fill in after checking current Tavus docs")

    def stop(self, conversation_id):
        raise NotImplementedError


def get_adapter(name: str) -> AvatarAdapter:
    return {"text": TextOnlyAdapter, "tavus": TavusAdapter}[name]()
