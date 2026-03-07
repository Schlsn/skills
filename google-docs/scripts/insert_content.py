#!/usr/bin/env python3
"""
Vloží obsah do Google Dokumentu přes gws CLI.
Správně vypočítá indexy a aplikuje named styles ze šablony.

Použití:
  python3 insert_content.py --doc-id "DOC_ID" --content '[{"style": "TITLE", "text": "Název"}]'
  python3 insert_content.py --doc-id "DOC_ID" --content-file obsah.json
"""

import argparse
import json
import subprocess
import sys


def gws(*args, params=None, body=None):
    cmd = ['gws'] + list(args)
    if params:
        cmd += ['--params', json.dumps(params)]
    if body:
        cmd += ['--json', json.dumps(body)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gws error: {r.stdout}\n{r.stderr}")
    return json.loads(r.stdout)


LIST_STYLES = {
    'LIST_BULLET': 'BULLET_DISC_CIRCLE_SQUARE',
    'LIST_NUMBERED': 'NUMBERED_DECIMAL_ALPHA_ROMAN',
}


def insert_content(doc_id: str, content: list[dict]) -> str:
    """
    Vloží obsah do dokumentu a aplikuje named styles.

    content: seznam dict s klíči:
      - style: TITLE | SUBTITLE | HEADING_1 | HEADING_2 | HEADING_3 | HEADING_4 | NORMAL_TEXT
               | LIST_BULLET | LIST_NUMBERED
      - text: text odstavce
      - bold_parts: [(start_char, end_char), ...] — části textu které mají být tučně (volitelné)
      - links: [(start_char, end_char, url), ...] — hypertextové odkazy (volitelné)

    Vrátí URL dokumentu.
    """
    requests = []
    pos = 1  # Za počátečním prázdným odstavcem
    paragraph_ranges = []

    for item in content:
        text = item['text']
        style = item.get('style', 'NORMAL_TEXT')
        full_text = text + '\n'
        text_len = len(full_text)

        start = pos
        end = pos + text_len
        paragraph_ranges.append((start, end, style, item))

        requests.append({
            "insertText": {
                "location": {"index": pos},
                "text": full_text
            }
        })
        pos += text_len

    # Aplikuj named styles a listy
    for (start, end, style, item) in paragraph_ranges:
        if style in LIST_STYLES:
            # List položky: použij NORMAL_TEXT jako základ, pak přidej bullet
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    "fields": "namedStyleType"
                }
            })
            requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": start, "endIndex": end},
                    "bulletPreset": LIST_STYLES[style]
                }
            })
        else:
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "paragraphStyle": {"namedStyleType": style},
                    "fields": "namedStyleType"
                }
            })

        # Volitelné bold_parts (tučné části)
        bold_parts = item.get('bold_parts', [])
        for (char_start, char_end) in bold_parts:
            requests.append({
                "updateTextStyle": {
                    "range": {
                        "startIndex": start + char_start,
                        "endIndex": start + char_end
                    },
                    "textStyle": {"bold": True},
                    "fields": "bold"
                }
            })

        # Volitelné links
        links = item.get('links', [])  # [(char_start, char_end, url), ...]
        for (char_start, char_end, url) in links:
            requests.append({
                "updateTextStyle": {
                    "range": {
                        "startIndex": start + char_start,
                        "endIndex": start + char_end
                    },
                    "textStyle": {
                        "link": {"url": url},
                        "underline": True
                    },
                    "fields": "link,underline"
                }
            })

    # Odeslat batchUpdate
    gws('docs', 'documents', 'batchUpdate',
        params={"documentId": doc_id},
        body={"requests": requests}
    )

    return f"https://docs.google.com/document/d/{doc_id}/edit"


def main():
    parser = argparse.ArgumentParser(description='Vloží obsah do Google Dokumentu')
    parser.add_argument('--doc-id', required=True, help='ID Google Dokumentu')
    parser.add_argument('--content', help='JSON string s obsahem')
    parser.add_argument('--content-file', help='Cesta k JSON souboru s obsahem')
    args = parser.parse_args()

    if args.content:
        content = json.loads(args.content)
    elif args.content_file:
        with open(args.content_file) as f:
            content = json.load(f)
    else:
        print("Chyba: musíš zadat --content nebo --content-file", file=sys.stderr)
        sys.exit(1)

    url = insert_content(args.doc_id, content)
    print(f"✅ Dokument vytvořen: {url}")


if __name__ == '__main__':
    main()
