'''
Render NOVA's long-form documents to self-contained HTML files.

Uses documentProcessor, which embeds every figure as a data URI so the output is one file with
nothing beside it. The source markdown stays readable in the repository and on GitHub; the HTML is
what gets sent to anyone who is not going to clone it.

    python featureShowcase/buildReport.py                           # every document
    python featureShowcase/buildReport.py NozzleDesignOverview.md   # one document, by file name
    python featureShowcase/buildReport.py --pdf                     # with a paginated light PDF
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

# (markdown source relative to the NOVA root, wordmark, eyebrow, masthead meta)
documents = [
    (os.path.join('docs', 'reports', 'nozzleContourEffort_2026-09-06.md'), 'NOVA',
     'Contour verification and assessment', ['Sean Bowman', '06 September 2026']),
    (os.path.join('docs', 'reports', 'coolingCircuitsEffort_2026-11-05.md'), 'NOVA',
     'Cooling circuits and example engines', ['Sean Bowman', '05 November 2026']),
    (os.path.join('docs', 'NozzleDesignOverview.md'), 'NOVA', 'Rocket Propulsion · Nozzle Design',
     ['Sean Bowman', 'Isabella Duprey-Churn', 'Compiled 07/20/2026']),
]

def readMarkdown(source: str) -> str:
    '''The document's markdown without the breadcrumb line that links it into the repository.'''
    with open(source, encoding = 'utf-8') as handle:
        lines = handle.read().split('\n')
    # A leading '[Home](...) > ...' line navigates the repository on GitHub and leads nowhere in a
    # file sent on its own
    while lines and not lines[0].strip():
        lines = lines[1:]
    if lines and lines[0].startswith('[Home]('):
        lines = lines[1:]
    return '\n'.join(lines)

def main():
    wantPdf = '--pdf' in sys.argv
    wanted = [argument for argument in sys.argv[1:] if not argument.startswith('--')]

    for relative, wordmark, eyebrow, meta in documents:
        name = os.path.basename(relative)
        if wanted and name not in wanted:
            continue
        source = os.path.join(root, relative)
        if not os.path.isfile(source):
            print(f'  missing {name}')
            continue

        text = readMarkdown(source)
        processor = DocumentProcessor(theme = 'dark', wordmark = wordmark, eyebrow = eyebrow,
                                      meta = meta)
        processor.fromMarkdown(text, baseDir = os.path.dirname(source))

        target = source.replace('.md', '.html')
        # documentProcessor writes the report style's own dark palette; the report takes NOVA's
        with open(target, 'w', encoding = 'utf-8', newline = '\n') as handle:
            handle.write(showcasePalette.restyleHtml(processor.toHtml()))
        print(f'  wrote {os.path.basename(target)}   '
              f'{os.path.getsize(target) / 1024 / 1024:.1f} MB')

        if wantPdf:
            # Light for paper, and paginated, because a report of this length as one continuous
            # sheet is unreadable on anything but a screen.
            printable = DocumentProcessor(theme = 'light', singlePage = False, wordmark = wordmark,
                                          eyebrow = eyebrow, meta = meta)
            printable.fromMarkdown(text, baseDir = os.path.dirname(source))
            pdfPath = source.replace('.md', '.pdf')
            printable.toPdf(pdfPath)
            print(f'  wrote {os.path.basename(pdfPath)}    '
                  f'{os.path.getsize(pdfPath) / 1024 / 1024:.1f} MB')

if __name__ == '__main__':
    main()
