# Skills report assets

Copies of the frontend public assets used by the skills report, so that the backend renders the report with the same
fonts and images as the frontend:

- `fonts/Inter-{Regular,Bold,Italic}.ttf`: `frontend-new/public/fonts/Inter-4.0/ttf` (Inter 4.0, SIL Open Font License 1.1)
- `images/*`: `frontend-new/public` (icons and logos referenced by the report and by `SKILLS_REPORT_OUTPUT_CONFIG.logos`)

Logos of the report config are resolved by file name in `images/` (and in `$SKILLS_REPORT_EXTRA_IMAGES_DIR` if set).
Keep these files in sync with the frontend (see `backend/scripts/skills_report_parity/README.md`).
