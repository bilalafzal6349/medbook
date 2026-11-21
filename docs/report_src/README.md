# Final report sources

`docs/MedBook_Final_Report.docx` is generated, not hand-edited. To rebuild it after changing the text or the results:

```bash
pip install matplotlib
python docs/report_figures/make_figures.py      # charts from results/, data/ and loadtest/
node docs/report_src/build_report.js            # needs `npm install docx`
# page numbers for the contents and lists: render to PDF, measure, rebuild
soffice --headless --convert-to pdf --outdir /tmp docs/MedBook_Final_Report.docx
python docs/report_src/measure_pages.py /tmp/MedBook_Final_Report.pdf && node docs/report_src/build_report.js
```

- `content.js` holds all text and tables. `[[...]]` marks a value to fill in before submission (shown highlighted in yellow).
- Three yellow "TO COMPLETE BEFORE SUBMISSION" boxes in Chapter 7 list the measurements still to run:
  real typed messages (7.8), real voice recordings (7.9), and the v2 weights / XLM-R load test (7.10).
- You can also edit the .docx directly in Word for final touches; just remember that rebuilding overwrites it.
