# Skills Report

Brand the skills report users download, and choose its formats and content.

`skillsReport` (`FRONTEND_SKILLS_REPORT_OUTPUT_CONFIG`) is an object with:

| Key | What it is |
|---|---|
| `logos` | logos at the top of the report: a list of `url`, with `docxStyles` (`width`, `height`) and `pdfStyles` (`height`) |
| `downloadFormats` | formats offered: `"PDF"`, `"DOCX"` or both |
| `report.summary.show` | show the summary section |
| `report.experienceDetails.title` | show the title of each experience |
| `report.experienceDetails.summary` | show the summary of each experience |
| `report.experienceDetails.companyName` | show the company name |
| `report.experienceDetails.dateRange` | show the date range |
| `report.experienceDetails.location` | show the location |

```bash
FRONTEND_SKILLS_REPORT_OUTPUT_CONFIG={"logos":[{"url":"/logo.png","docxStyles":{"width":250,"height":62},"pdfStyles":{"height":46}}],"downloadFormats":["PDF"]}
```

Keys you leave out keep their default. See [`config/default.json`](../../config/default.json) for a complete example.

Apply the changes as described in [Applying Changes](applying-changes.md).
