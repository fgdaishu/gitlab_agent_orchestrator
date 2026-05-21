# Context Pack: PNG-SIGNATURE-001

Project: Memory-safe PNG parser subset in Rust
Current module: PNG signature validation
Compatibility level: L1 behavior compatibility for a tiny parser subset

## Relevant Contract

- PNG signature is exactly 8 bytes: `89 50 4E 47 0D 0A 1A 0A`.
- Inputs shorter than 8 bytes return `PngError::TruncatedInput`.
- Inputs with 8 available bytes but wrong bytes return `PngError::InvalidSignature`.

## Security Constraints

- No unsafe code.
- No allocation.
- No panic on malformed input.

## Related Files

- `src/signature.rs`
- `src/error.rs`
- `src/lib.rs`
- `tests/signature.rs`

## Current Task

Keep the implementation narrow. Validate signature behavior, tests, and handoff. Do not implement chunk parsing here.

