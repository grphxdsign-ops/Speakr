# Apple Developer ID intermediate certificates

Apple's public intermediate CA certificates, vendored so the release
runner's ephemeral build keychain can chain the imported Developer ID
Application identity to the trusted Apple Root CA. Without an
intermediate present, `security find-identity -v -p codesigning` lists
no valid identity and the macOS release job fails with "Certificate
does not contain a Developer ID Application identity" even when the
signing certificate is correct.

These are public certificates published by Apple at
<https://www.apple.com/certificateauthority/> — they contain no secret
material.

| File | Subject | Valid until | SHA-256 fingerprint |
| --- | --- | --- | --- |
| `DeveloperIDG2CA.cer` | Developer ID Certification Authority (OU=G2) | 2031-09-17 | `F1:6C:D3:C5:4C:7F:83:CE:A4:BF:1A:3E:6A:08:19:C8:AA:A8:E4:A1:52:8F:D1:44:71:5F:35:06:43:D2:DF:3A` |
| `DeveloperIDCA.cer` | Developer ID Certification Authority | 2027-02-01 | `7A:FC:9D:01:A6:2F:03:A2:DE:96:37:93:6D:4A:FE:68:09:0D:2D:E1:8D:03:F2:9C:88:CF:B0:B1:BA:63:58:7F` |

Re-verify a file against this table with:

```sh
openssl x509 -inform der -in <file>.cer -noout -subject -fingerprint -sha256
```
