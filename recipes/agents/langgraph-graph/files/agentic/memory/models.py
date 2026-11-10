from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryKey:
    """Identifies one conversation thread.

    All three ids are required: `conversation_id` is chosen by the client, so filtering by it
    alone would let a user read another tenant's thread. `tenant_id` and `user_id` must come
    from the auth token, never from the request body.
    """

    tenant_id: str
    user_id: str
    conversation_id: str
