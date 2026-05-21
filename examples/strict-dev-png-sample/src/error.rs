use core::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PngError {
    InvalidSignature,
    TruncatedInput,
    ChunkTooLarge,
    InvalidChunkType,
}

impl fmt::Display for PngError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidSignature => write!(f, "invalid PNG signature"),
            Self::TruncatedInput => write!(f, "truncated input"),
            Self::ChunkTooLarge => write!(f, "chunk too large"),
            Self::InvalidChunkType => write!(f, "invalid chunk type"),
        }
    }
}

impl std::error::Error for PngError {}

