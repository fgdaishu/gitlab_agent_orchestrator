# Context Pack: PNG-CHUNK-001

Project: Memory-safe PNG parser subset in Rust
Current module: safe PNG chunk reader
Compatibility level: L1 behavior compatibility for chunk field parsing

## Relevant Contract

- Read 4-byte big-endian chunk length.
- Read 4-byte ASCII alphabetic chunk type.
- Validate `length <= max_chunk_size` before data access.
- Return borrowed chunk data slice and remaining input.
- Read 4-byte big-endian CRC after data.
- Do not validate semantic chunk ordering here.

## Security Constraints

- No unsafe code.
- No unchecked indexing beyond validated bounds.
- Use checked offset arithmetic.
- Do not allocate for chunk field parsing.
- Return structured errors and never panic on malformed input.

## Related Files

- `src/chunk.rs`
- `src/error.rs`
- `src/lib.rs`
- `tests/chunk.rs`

## Current Task

Keep this task scoped to chunk field parsing. Do not implement IDAT decompression, CRC verification, or full PNG decoding.

