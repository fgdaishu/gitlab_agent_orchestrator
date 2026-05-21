# Compatibility Levels

MVP target: L1 behavior compatibility for a tiny PNG parser subset.

Included:
- PNG signature validation
- PNG chunk length/type/data/CRC field parsing
- structured errors on malformed input

Excluded:
- full PNG API
- ABI compatibility
- IDAT decompression
- scanline filtering
- image output
