"""The common raw audit for one episode.

One writer owns the episode's raw evidence: the acquisitions the cameras actually produced, the
controller references the run actually accepted or revoked, the physics observations the run actually
made, the run events, and the binding of each training row to the acquisitions and reference sequence
it consumed. The recorder writes its rows through the same boundary, so a row cannot exist without its
raw binding, and nothing may rewrite the audit after it is sealed.

Every append is a new line; there is no update path. Each source kind has a closed schema, so an
unknown field is refused rather than silently retained, and `seal()` writes the manifest of the raw
audit last, fsyncing every file and the directory before returning. `verify_audit_manifest()` re-reads
the files and recomputes their digests, so a rewritten reference or a missing binding is detected
instead of trusted.
"""
