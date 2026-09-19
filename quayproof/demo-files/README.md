# Synthetic demonstration files

These files were authored for QuayProof. They contain fictional companies and are unrelated to organizer labels.

| File | Intended demonstration |
|---|---|
| instruction.txt | SI reference for the matching/mismatch examples |
| draft-matching.txt | All seven fields equal the SI |
| draft-mismatch.txt | Gross weight differs |
| draft-unresolved.txt | Gross weight is explicitly unresolved (`TBC`) |
| draft-corrected.txt | Readable new BL revision resolving the missing value |
| instruction-table.docx | SI fields in a Word table |
| instruction-table.xlsx | SI fields in an Excel worksheet |
| draft-native.pdf | Native text BL with page/coordinate evidence |
| draft-scanned.pdf | Image-only PDF; numeric OCR confirmation is intentionally required |
| unreadable.pdf | Deliberately damaged bytes for the unreadable-document path; **not a valid PDF** |

Use email body: `Please compare the attached draft BL against the SI and verify all seven fields.` Attach one SI and one BL. For a corrected revision, use the UI's **New revision** control beside the existing BL.

Regenerate these files with `python scripts/make_demo_files.py` after installing the development requirements.
