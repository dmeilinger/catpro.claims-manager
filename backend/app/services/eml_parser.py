"""EML email parsing — extracts body text and PDF attachments."""

import email


def parse_eml(eml_path: str) -> tuple[str, dict[str, bytes]]:
    """Returns (email_body_text, {doc_type: pdf_bytes})"""
    with open(eml_path, "rb") as f:
        msg = email.message_from_bytes(f.read())

    body = ""
    pdfs = {}

    for part in msg.walk():
        ct    = part.get_content_type()
        fname = part.get_filename() or ""

        if ct == "text/plain" and not fname:
            body += part.get_payload(decode=True).decode("utf-8", errors="replace")

        elif ct == "application/pdf":
            data = part.get_payload(decode=True)
            # Normalize whitespace in filename (some clients wrap long names)
            fname_flat = " ".join(fname.split())
            if "Claim Summary" in fname_flat:
                pdfs["claim_summary"] = data
            elif "Loss Notice" in fname_flat:
                pdfs["loss_notice"] = data
            elif "Policy Summary" in fname_flat:
                pdfs["policy_summary"] = data
            else:
                pdfs[fname_flat or "attachment"] = data

    return body, pdfs
