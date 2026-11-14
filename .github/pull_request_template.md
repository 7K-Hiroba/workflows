## Summary

## Security and admin impact

## Test evidence

- Exact candidate SHA:
- Run URLs:
- Unit/negative commands:
- Scaffold lanes:
- Registry/provenance/attestation evidence (only if separately authorized):

## Gates

- [ ] No mutable callers, classic Helm index, UI Release assets, or operator dependency.
- [ ] No GHCR/tag/Release/Pages/stage/prod action without explicit approval.
- [ ] CODEOWNERS review from workflows-maintainers and platform-security where required.
- [ ] Draft PR contains no fabricated run IDs, digests, or admin claims.
