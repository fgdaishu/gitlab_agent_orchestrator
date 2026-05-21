use strict_dev_png_sample::signature::{validate_png_signature, PNG_SIGNATURE};
use strict_dev_png_sample::PngError;

#[test]
fn accepts_valid_png_signature() {
    assert_eq!(validate_png_signature(&PNG_SIGNATURE), Ok(()));
}

#[test]
fn rejects_truncated_signature() {
    assert_eq!(validate_png_signature(&PNG_SIGNATURE[..4]), Err(PngError::TruncatedInput));
}

#[test]
fn rejects_invalid_signature() {
    let mut input = PNG_SIGNATURE;
    input[1] = b'X';
    assert_eq!(validate_png_signature(&input), Err(PngError::InvalidSignature));
}
