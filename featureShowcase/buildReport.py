'''
Render the nozzle contour report to a self-contained HTML file.

Uses documentProcessor, which embeds every figure as a data URI so the output is one file with
nothing beside it. The source markdown stays readable in the repository and on GitHub; the HTML is
what gets sent to anyone who is not going to clone it.

    python featureShowcase/buildReport.py
    python featureShowcase/buildReport.py --pdf
'''
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)

# documentProcessor is a sibling repository rather than a dependency of this one, so it is located
# relative to the projects directory. Installing it into the environment removes the need for this.
sys.path.insert(0, os.path.join(os.path.dirname(root), 'documentProcessor'))

from documentProcessor import DocumentProcessor

import showcasePalette

reports = os.path.join(root, 'docs', 'reports')
documents = [
    ('nozzleContourEffort_2026-09-06.md', 'NOVA', 'Contour verification and assessment'),
]

def main():
    wantPdf = '--pdf' in sys.argv

    for name, wordmark, eyebrow in documents:
        source = os.path.join(reports, name)
        if not os.path.isfile(source):
            print(f'  missing {name}')
            continue

        processor = DocumentProcessor(theme = 'dark', wordmark = wordmark, eyebrow = eyebrow,
                                      meta = ['Sean Bowman', '06 September 2026'])
        processor.fromMarkdownFile(source)

        target = os.path.join(reports, name.replace('.md', '.html'))
        # documentProcessor writes the report style's own dark palette; the report takes NOVA's
        with open(target, 'w', encoding = 'utf-8') as handle:
            handle.write(showcasePalette.restyleHtml(processor.toHtml()))
        print(f'  wrote {os.path.basename(target)}   '
              f'{os.path.getsize(target) / 1024 / 1024:.1f} MB')

        if wantPdf:
            # Light for paper, and paginated, because a report of this length as one continuous
            # sheet is unreadable on anything but a screen.
            printable = DocumentProcessor(theme = 'light', singlePage = False, wordmark = wordmark,
                                          eyebrow = eyebrow,
                                          meta = ['Sean Bowman', '06 September 2026'])
            printable.fromMarkdownFile(source)
            pdfPath = os.path.join(reports, name.replace('.md', '.pdf'))
            printable.toPdf(pdfPath)
            print(f'  wrote {os.path.basename(pdfPath)}    '
                  f'{os.path.getsize(pdfPath) / 1024 / 1024:.1f} MB')

if __name__ == '__main__':
    main()
