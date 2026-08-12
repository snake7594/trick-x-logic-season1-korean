"""대사창 2줄을 넘는 조각의 번역을 짧게 바꾼다.

    python ../tools/shorten.py 고침표.json [--apply]

고침표는 `{파일이름: {조각번호: 새 한국어}}`. 빈 문자열은 넣지 않는다 —
길이 0 인 문자열이 해석기를 멈춘 전례가 있다(`ruby.py` 참고).
"""
import paths
import json
import os
import sys


def load_docs():
    idx = json.load(open(os.path.join(paths.TEXT, '_index.json'),
                         encoding='utf-8'))
    docs = {}
    for m in idx['files']:
        docs[m['file']] = json.load(
            open(os.path.join(paths.TEXT, m['file']), encoding='utf-8'))
    return docs


def apply(fixes, docs, do=False):
    by = {}
    for name, doc in docs.items():
        for r in doc['entries']:
            by.setdefault(r['file'].split('/')[-1], {})[r['index']] = (name, r)
    n, miss = 0, 0
    for fn, items in fixes.items():
        if fn.startswith('_'):
            continue
        rows = by.get(fn)
        if rows is None:
            print(f"  ! {fn} 없음")
            miss += len(items)
            continue
        for k, new in items.items():
            r = rows.get(int(k))
            if r is None:
                print(f"  ! {fn} {k} 없음")
                miss += 1
                continue
            if not new.strip():
                print(f"  ! {fn} {k} 빈 문자열은 넣지 않는다")
                miss += 1
                continue
            old = r[1].get('ko') or ''
            if old == new:
                continue
            print(f"  {fn} {k}")
            print(f"      - {old}")
            print(f"      + {new}")
            if do:
                r[1]['ko'] = new
            n += 1
    print(f"\n{'적용' if do else '미리보기'} {n}건 / 못 찾음 {miss}")
    return n, miss


if __name__ == '__main__':
    fixes = json.load(open(sys.argv[1], encoding='utf-8'))
    docs = load_docs()
    n, miss = apply(fixes, docs, '--apply' in sys.argv)
    if '--apply' in sys.argv and n:
        for name, doc in docs.items():
            json.dump(doc, open(os.path.join(paths.TEXT, name), 'w',
                                encoding='utf-8'), ensure_ascii=False, indent=1)
        print('-> text/*.json 갱신')
