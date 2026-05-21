use crate::PngError;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Chunk<'a> {
    pub length: u32,
    pub chunk_type: [u8; 4],
    pub data: &'a [u8],
    pub crc: u32,
}

pub fn read_chunk<'a>(input: &'a [u8], max_chunk_size: u32) -> Result<(Chunk<'a>, &'a [u8]), PngError> {
    if input.len() < 12 {
        return Err(PngError::TruncatedInput);
    }

    let length = u32::from_be_bytes([input[0], input[1], input[2], input[3]]);
    if length > max_chunk_size {
        return Err(PngError::ChunkTooLarge);
    }

    let chunk_type = [input[4], input[5], input[6], input[7]];
    if !chunk_type.iter().all(|byte| byte.is_ascii_alphabetic()) {
        return Err(PngError::InvalidChunkType);
    }

    let data_len = usize::try_from(length).map_err(|_| PngError::ChunkTooLarge)?;
    let data_start = 8usize;
    let data_end = data_start.checked_add(data_len).ok_or(PngError::ChunkTooLarge)?;
    let crc_end = data_end.checked_add(4).ok_or(PngError::ChunkTooLarge)?;
    if input.len() < crc_end {
        return Err(PngError::TruncatedInput);
    }

    let crc = u32::from_be_bytes([
        input[data_end],
        input[data_end + 1],
        input[data_end + 2],
        input[data_end + 3],
    ]);
    let chunk = Chunk {
        length,
        chunk_type,
        data: &input[data_start..data_end],
        crc,
    };
    Ok((chunk, &input[crc_end..]))
}

