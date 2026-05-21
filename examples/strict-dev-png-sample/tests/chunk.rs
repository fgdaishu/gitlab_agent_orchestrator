use strict_dev_png_sample::chunk::read_chunk;
use strict_dev_png_sample::PngError;

#[test]
fn reads_basic_chunk() {
    let input = [
        0, 0, 0, 3, b'a', b'B', b'c', b'D', b'x', b'y', b'z', 1, 2, 3, 4, b'n',
    ];
    let (chunk, rest) = read_chunk(&input, 16).expect("chunk should parse");
    assert_eq!(chunk.length, 3);
    assert_eq!(chunk.chunk_type, *b"aBcD");
    assert_eq!(chunk.data, b"xyz");
    assert_eq!(chunk.crc, 0x01020304);
    assert_eq!(rest, b"n");
}

#[test]
fn rejects_chunk_larger_than_limit() {
    let input = [0, 0, 0, 17, b'I', b'D', b'A', b'T', 0, 0, 0, 0];
    assert_eq!(read_chunk(&input, 16).unwrap_err(), PngError::ChunkTooLarge);
}

#[test]
fn rejects_truncated_chunk_data() {
    let input = [0, 0, 0, 4, b'I', b'D', b'A', b'T', b'x', b'y'];
    assert_eq!(read_chunk(&input, 16).unwrap_err(), PngError::TruncatedInput);
}

#[test]
fn rejects_invalid_chunk_type() {
    let input = [0, 0, 0, 0, b'I', b'D', b'4', b'T', 0, 0, 0, 0];
    assert_eq!(read_chunk(&input, 16).unwrap_err(), PngError::InvalidChunkType);
}
