use crate::PngError;

pub const PNG_SIGNATURE: [u8; 8] = [137, 80, 78, 71, 13, 10, 26, 10];

pub fn validate_png_signature(input: &[u8]) -> Result<(), PngError> {
    if input.len() < PNG_SIGNATURE.len() {
        return Err(PngError::TruncatedInput);
    }
    if input[..PNG_SIGNATURE.len()] != PNG_SIGNATURE {
        return Err(PngError::InvalidSignature);
    }
    Ok(())
}

