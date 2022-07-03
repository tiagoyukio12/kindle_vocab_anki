#!/usr/bin/env python

import sys
import sqlite3
import argparse
import itertools
from datetime import datetime
from operator import itemgetter
from operator import attrgetter
from collections import namedtuple
from jamdict import Jamdict

AnkiNote = namedtuple('AnkiNote', 'word usage definition timestamp')


def get_vocab(vocab_db, _since=0):
    if isinstance(_since, datetime):
        since = int(_since.timestamp()) * 1000
    else:
        since = _since * 1000

    db = sqlite3.connect(vocab_db)
    db.row_factory = sqlite3.Row
    cur = db.cursor()
    sql = '''
        select WORDS.stem, WORDS.word, LOOKUPS.usage, BOOK_INFO.title, LOOKUPS.timestamp
        from LOOKUPS left join WORDS
        on WORDS.id = LOOKUPS.word_key
        left join BOOK_INFO
        on BOOK_INFO.id = LOOKUPS.book_key
        where LOOKUPS.timestamp > ?
        and BOOK_INFO.title = '大きな帽子の女'
        order by WORDS.stem, LOOKUPS.timestamp
    '''
    rows = cur.execute(sql, (since,)).fetchall()
    return rows


def make_notes(vocab, include_nodef=False):
    # OALD is ~38 MiB for each stem and ~110 MiB for each iform,
    # read it all into a Python dict does not hurt on mordern PCs.
    jam = Jamdict()

    stems_no_def = set()
    notes = []
    # vocab is a list of db rows order by (stem, timestamp)
    for stem, entries in itertools.groupby(vocab, itemgetter('stem')):
        if stem is None:
            continue
        # Merge multiple usages into one.
        usage_all = ''
        usage_timestamp = None
        for entry in entries:
            word = entry['word']
            _usage = entry['usage'].replace(word, f'<strong>{word}</strong>').strip()
            usage = f'<blockquote>{_usage}<small>{entry["title"]}</small></blockquote>'
            usage_all += usage
            usage_timestamp = entry['timestamp']

        # Look up definition in dictionary
        try:
            result = jam.lookup(stem)
            definition = ''
            for entry in result.entries:
                definition += f'<b>{str(entry.kana_forms[0])}'
                if len(entry.kanji_forms) > 0 and len(result.entries) > 1:
                    definition += f' ({str(entry.kanji_forms[0])})'
                definition += '</b>:<br>'
                for i, sense in enumerate(entry.senses):
                    definition += f'{i + 1}. {str(sense)}<br>'
        except KeyError:
            stems_no_def.add(stem)
            if include_nodef:
                definition = None
            else:
                continue

        note = AnkiNote(stem, usage_all, definition, usage_timestamp)
        notes.append(note)

    if stems_no_def:
        print(f'WARNING: Some words cannot be found in dictionary:\n{stems_no_def}', file=sys.stderr)

    return notes


def output_anki_tsv(notes, output, sort=True):
    if sort:
        notes.sort(key=attrgetter('timestamp'), reverse=True)

    with output as f:
        for note in notes:
            line = f'{note.word}\t{note.usage}\t{note.definition}\n'
            f.write(line)


if __name__ == '__main__':
    argp = argparse.ArgumentParser()
    argp.add_argument('--since', type=lambda s: datetime.strptime(s, '%Y-%m-%d'),
                      default=datetime.utcfromtimestamp(86400 * 2))  # Windows workaround
    argp.add_argument('--include-nodef', action='store_true',
                      help='include words that have no definitions in dictionary')
    argp.add_argument('vocab_db')
    argp.add_argument('anki_tsv', type=argparse.FileType('w', encoding='utf-8'))
    args = argp.parse_args()
    vocab = get_vocab(args.vocab_db, _since=args.since)
    notes = make_notes(vocab, include_nodef=args.include_nodef)
    output_anki_tsv(notes, args.anki_tsv)
