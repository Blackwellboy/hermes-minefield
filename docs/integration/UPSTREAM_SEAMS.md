# Prepared upstream seam proposal — not submitted

The selected public register_command callback receives command text, without a
documented authenticated actor/event object. Typing a slash command, possessing a
nonce or having a TTY is not proof of owner action. Existing register_tool approval
gates concern host tool dispatch; they do not by themselves authorize an arbitrary
plugin job/consent transaction. Desktop ctx.rest provides a profile-aware backend
namespace, but a caller-supplied scope or `approved` JSON field is not authority.

Proposed independently useful public contract: host-owned plugin action request
with immutable review digest, authenticated connection/profile/session/actor,
explicit owner decision, expiry, one-use consumption, and invalidation on scope
change. The backend should verify the decision without trusting renderer flags.
Expose host lifecycle cancellation and approved provider identity separately from
credentials. For diagnostic calls, preserve raw request/response and SSE semantics
under a passed all-HTTP budget context rather than normalizing through an agent.

Until verified, native surfaces expose local catalogue/preview/privacy information
only. Jobs and contributions have injectable authority contracts exercised with
synthetic event sources; those tests are not proof of a production host bridge.

No upstream issue, Nous contact, catalogue submission or third-party PR has been
made. This proposal is prepared for owner review after implementation gaps close.
