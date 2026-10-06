"""Personal OS 0.3.1. Markdown and managed sources are authoritative; SQLite is disposable."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from zoneinfo import ZoneInfo
import yaml
import numpy as np

BASE = Path(__file__).resolve().parent
PROJECT_ROOT = BASE.parent
PERSONAL_OS_VERSION = '0.6.1'
REFLECT_VERSION = '0.2.0'
FOLDERS = ['00_System', '01_Experiences', '02_Decisions', '03_Projects',
           '04_Knowledge/Books', '04_Knowledge/Articles', '04_Knowledge/Papers',
           '04_Knowledge/Cases', '04_Knowledge/Frameworks', '05_Models', '90_Inbox']
KINDS = {'experience', 'decision', 'model', 'profile', 'goal', 'constraint',
         'principle', 'project', 'knowledge', 'system', 'history'}
PROVENANCE = {'user_explicit', 'behavior_inferred', 'ai_observation', 'system_record', 'external_source'}
EVENT_DATE_PRECISIONS = {'exact', 'approximate', 'unknown'}
SOURCE_TYPES = {'current_conversation', 'chat_history', 'diary', 'document',
                'project_record', 'user_recollection', 'system_record',
                'external_source', 'other'}
RETRIEVAL_PROFILES = {
    'v0_1': frozenset(),
    'system_index_only': frozenset(),
    'diversity_only': frozenset({'diversity'}),
    'authority_only': frozenset({'authority'}),
    'relations_only': frozenset({'relations'}),
    'authority_diversity': frozenset({'authority', 'diversity'}),
    'relations_diversity': frozenset({'relations', 'diversity'}),
    'authority_relations': frozenset({'authority', 'relations'}),
    # Final round-1 profile keeps only the dev-positive feature. System notes are
    # indexed for non-v0_1 profiles; authority/diversity remain available as ablations.
    'optimized_v1': frozenset({'relations'}),
}

# Query-intent signals are deliberately small and type-based. They never name a note ID.
TYPE_INTENT_SIGNALS = {
    'system': ('架构', '技术组合', '技术流程', '向量模型', 'embedding', '维度', '索引', '检索',
               '排序', 'rrf', 'fts', '权威副本', '真实数据源', 'source of truth', '重建', 'rebuild'),
    'history': ('历史状态', '过去状态', '变化历史', '后来不再', '原来', '曾经', '变化轨迹', '修订'),
    'decision': ('决定', '决策', '选择', '权衡', '为什么选', '最终选', '方案'),
    'experience': ('经历', '事件', '复盘', '发生了什么', '第一次', '首次'),
    'profile': ('个人特征', '个人偏好', '当前偏好', '习惯', '工作方式', '个人状态'),
    'model': ('ai observation', 'ai观察', '观察出', '行为模式', '个人模式', '推断'),
    'goal': ('目标', '为了什么', '想实现', '长期方向'),
    'constraint': ('约束', '限制', '边界条件'),
    'project': ('project', '项目负责人', '项目状态', '正式项目'),
    'knowledge': ('外部知识', '书籍', '论文', '文章', '案例', '资料来源'),
}

def query_type_boosts(query):
    q = query.casefold()
    boosts = {}
    for kind, signals in TYPE_INTENT_SIGNALS.items():
        hits = sum(signal.casefold() in q for signal in signals)
        if hits:
            boosts[kind] = min(0.018, 0.010 + 0.002 * (hits - 1))
    # Relationship wording commonly asks for both sides, not just the named target type.
    if any(signal in q for signal in ('关联', '相关记录', '同时找到', '对应的')):
        boosts['decision'] = max(boosts.get('decision', 0), 0.012)
        boosts['experience'] = max(boosts.get('experience', 0), 0.012)
    return boosts

def relationship_intent(query):
    q = query.casefold()
    return any(signal in q for signal in ('关联', '相关记录', '同时找到', '对应的', '哪一个决定', '哪项决定'))

def source_evidence_intent(query):
    q = query.casefold()
    if re.search(r'(?:第\s*)?\d+\s*页|p\.\s*\d+', q):
        return True
    # Generic words such as “来源/出处” also occur in Personal OS provenance
    # questions.  Enter the much larger evidence corpus only when the query also
    # identifies an external document or its author.
    evidence_signal = any(signal in q for signal in
                          ('原文', '页码', '引用位置', '出处', '如何说', '怎么说'))
    document_signal = any(signal in q for signal in
                          ('这本书', '书中', '这篇论文', '论文中', '这篇文章', '文章中',
                           '这份文档', '文档中', '作者', '原作者'))
    return evidence_signal and document_signal

def requested_page(query):
    match = re.search(r'(?:第\s*)?(\d+)\s*页|p\.\s*(\d+)', query.casefold())
    return 'p.' + next(group for group in match.groups() if group) if match else None

def knowledge_overview_intent(query):
    q = query.casefold()
    return any(signal in q for signal in ('这本书', '这篇论文', '这篇文章', '主要主题',
                                           '内容概览', '章节结构', '文档结构', '外部知识'))

def now():
    # UTC+8 is explicit and does not require Windows tzdata installation.
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')

def digest(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()

def file_digest(path):
    path = Path(path)
    return digest(path.read_bytes()) if path.exists() else None

def infer_reflect_mode(text):
    """Conservative natural-language router; an explicit packet mode always wins."""
    text = (text or '').casefold()
    update_signals = ('补充之前', '补充那条', '修正之前', '更新之前', '更新 dec-',
                      '更新 exp-', '更新 mod-', '追加 outcome', '补充 outcome',
                      '补充结果', '已有记录', '那条记录')
    backfill_signals = ('这是以前', '过去发生', '旧聊天', '旧日记', '历史资料',
                        '旧项目记录', '回忆起', '历史回填', '以前的事情', '当年的')
    if any(signal in text for signal in update_signals) or re.search(r'(?:更新|修正|补充)\s*(?:dec|exp|mod)-', text):
        return 'update'
    if any(signal in text for signal in backfill_signals):
        return 'backfill'
    return 'current'

class WriteConflict(RuntimeError):
    def __init__(self, message, artifact=None):
        super().__init__(message)
        self.artifact = artifact

def atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)

def dump(meta, body):
    return '---\n' + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + '---\n\n' + body.strip() + '\n'

def parse(text):
    m = re.match(r'\A\ufeff?---\r?\n(.*?)\r?\n---\r?\n', text, re.S)
    if not m:
        raise ValueError('缺少 YAML frontmatter')
    meta = yaml.safe_load(m[1])
    if not isinstance(meta, dict):
        raise ValueError('YAML 必须是对象')
    return meta, text[m.end():].strip()

def check_note(meta, body):
    for key in ['schema_version', 'type', 'id', 'title', 'created_at', 'updated_at']:
        if key not in meta or meta[key] is None:
            raise ValueError('缺少字段: ' + key)
    if meta['schema_version'] != 1 or meta['type'] not in KINDS:
        raise ValueError('未知 schema_version/type')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', str(meta['id'])):
        raise ValueError('非法 note ID')
    if meta.get('confidence') is not None and not 0 <= float(meta['confidence']) <= 1:
        raise ValueError('confidence 必须位于 0..1')
    for field in ['tags','domains','people','projects','evidence','related_experiences','related_decisions','related_models','related_projects']:
        if field in meta and (not isinstance(meta[field],list) or not all(isinstance(x,str) for x in meta[field])):
            raise ValueError(field+' 必须是字符串列表')
    if meta['type'] in {'experience', 'decision', 'model'}:
        for field in ['date', 'source', 'provenance']:
            if not meta.get(field) and not (field == 'date' and
                    (meta.get('event_date_precision') in {'approximate','unknown'} or meta.get('date_precision') == 'unknown')):
                raise ValueError('缺少字段: ' + field)
        if meta['provenance'] not in PROVENANCE:
            raise ValueError('未知 provenance')
        if meta.get('date') is not None:
            datetime.strptime(str(meta['date']),'%Y-%m-%d')
        if 'event_date' in meta:
            if meta.get('event_date') is not None:
                datetime.strptime(str(meta['event_date']), '%Y-%m-%d')
            precision = meta.get('event_date_precision')
            if precision not in EVENT_DATE_PRECISIONS:
                raise ValueError('event_date_precision 无效')
            if precision == 'exact' and meta.get('event_date') is None:
                raise ValueError('exact event_date 不能为空')
            if precision == 'approximate' and not meta.get('event_date_raw'):
                raise ValueError('approximate 必须保留 event_date_raw')
            if not meta.get('recorded_at'):
                raise ValueError('V0.2 记录必须有 recorded_at')
        for item in meta.get('source_materials', []):
            if not isinstance(item, dict) or not item.get('material_id') or item.get('source_type') not in SOURCE_TYPES:
                raise ValueError('source_materials 无效')
        for item in meta.get('reflection_imports', []):
            if not isinstance(item, dict) or not item.get('import_id') or not item.get('material_id'):
                raise ValueError('reflection_imports 无效')
    if meta['type']=='decision' and meta.get('status') not in {'proposed','decided','reviewed','obsolete'}:
        raise ValueError('Decision status 无效')
    if meta['type'] == 'model':
        if meta.get('confidence') is None:
            raise ValueError('Model 必须明确提供 confidence')
        if meta.get('provenance') not in {'ai_observation', 'user_explicit', 'behavior_inferred'}:
            raise ValueError('Model 的来源类型不正确')
        if not meta.get('evidence') or meta.get('status') not in {'observing', 'confirmed', 'refuted', 'obsolete'}:
            raise ValueError('Model 缺少证据或有效状态')
    if meta['type'] == 'knowledge':
        for field in ['knowledge_type', 'source_type', 'quality', 'completeness', 'verified_against_original', 'date_added']:
            if field not in meta:
                raise ValueError('Knowledge 缺少字段: ' + field)
        if meta['source_type'] not in {'original_book','original_paper','third_party_summary','article','case','personal_reflection','AI_summary'}:
            raise ValueError('Knowledge source_type 无效')
        if not isinstance(meta['verified_against_original'],bool):
            raise ValueError('verified_against_original 必须是布尔值')
        if meta.get('schema_revision') == 'knowledge-v0.3':
            required = ['content_origin','source_id','source_format','source_hash','source_path',
                        'source_scope','derived_from','citation_mode','extractor','extractor_version',
                        'retrieved_at','import_ids']
            for field in required:
                if field not in meta or meta[field] is None:
                    raise ValueError('Knowledge V0.3 缺少字段: ' + field)
            if meta['content_origin'] not in {'original','third_party_summary','ai_summary','personal_reflection'}:
                raise ValueError('Knowledge content_origin 无效')
            if not re.fullmatch(r'SRC-[A-Z0-9_-]+', str(meta['source_id'])):
                raise ValueError('Knowledge source_id 无效')
            if not re.fullmatch(r'[0-9a-f]{64}', str(meta['source_hash'])):
                raise ValueError('Knowledge source_hash 必须是 SHA-256')
            if not isinstance(meta['derived_from'], list) or not all(isinstance(x,str) for x in meta['derived_from']):
                raise ValueError('Knowledge derived_from 必须是字符串列表')
            if meta['citation_mode'] not in {'page','chapter','section','none'}:
                raise ValueError('Knowledge citation_mode 无效')
    if not body.startswith('# '):
        raise ValueError('正文必须以一级标题开头')

class Store:
    def __init__(self, config, read_only=False):
        self.read_only = bool(read_only)
        self.config_path = Path(config).resolve()
        self.cfg = yaml.safe_load(self.config_path.read_text(encoding='utf-8'))
        self.root = (self.config_path.parent / self.cfg['personal_os_root']).resolve()
        self.private = self.root / '.personal-os'
        self.db_path = self.resolve(self.cfg['database_path'])
        self.model_path = self.resolve(self.cfg['embedding']['local_path'])
        self._embed = None
        if not self.read_only:
            self.private.mkdir(parents=True, exist_ok=True)
        logs = self.private / 'logs'
        if not self.read_only:
            logs.mkdir(exist_ok=True)
        self.log = logging.getLogger(str(self.root) + (':readonly' if self.read_only else ''))
        if not self.log.handlers:
            handler = (logging.NullHandler() if self.read_only else
                       RotatingFileHandler(logs / 'operations.log', maxBytes=1024*1024, backupCount=3, encoding='utf-8'))
            handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
            self.log.addHandler(handler)
            self.log.setLevel(logging.INFO)

    def resolve(self, path):
        p = Path(path)
        return p.resolve() if p.is_absolute() else (self.root / p).resolve()

    def safe(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or '.personal-os' in path.relative_to(self.root).parts:
            raise ValueError('笔记路径超出数据区')
        return path

    @contextmanager
    def lock(self):
        # OS advisory lock is released automatically on process exit/crash.
        lock_path = self.private / 'write.lock'
        with open(lock_path, 'a+b') as f:
            if f.tell() == 0:
                f.write(b'0'); f.flush()
            f.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError('另一个写入/索引正在运行，请稍后重试') from exc
            try:
                yield
            finally:
                f.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def notes(self):
        for folder in FOLDERS:
            # Knowledge children are listed explicitly, no overlap.
            for path in sorted((self.root / folder).rglob('*.md')):
                if path.resolve().is_relative_to(self.root) and not path.is_symlink():
                    yield path

    def source_evidence(self):
        """Yield managed extraction evidence linked by original Knowledge notes."""
        seen_sources = set()
        for note in self.notes():
            try:
                meta, _ = parse(note.read_text(encoding='utf-8-sig'))
            except (OSError, ValueError):
                continue
            if meta.get('type') != 'knowledge' or meta.get('content_origin') != 'original':
                continue
            source_id = meta.get('source_id')
            evidence_rel = meta.get('source_evidence_path')
            if not source_id or not evidence_rel or source_id in seen_sources:
                continue
            evidence = self.safe(evidence_rel)
            if not evidence.is_file() or not evidence.is_relative_to(self.root/'04_Knowledge/_Sources'):
                continue
            citation = evidence.parent/'citation-index.json'
            citations = []
            if citation.is_file():
                try:
                    value = json.loads(citation.read_text(encoding='utf-8-sig'))
                    if isinstance(value, list): citations = value
                except (OSError, json.JSONDecodeError):
                    citations = []
            seen_sources.add(source_id)
            yield {
                'path': evidence, 'relative': evidence.relative_to(self.root).as_posix(),
                'source_id': source_id, 'title': meta.get('title') or source_id,
                'tags': meta.get('tags') or [], 'date': meta.get('published_at') or '',
                'citations': citations, 'citation_path': citation,
            }

    @contextmanager
    def db(self):
        if self.read_only:
            db = sqlite3.connect(self.db_path.as_uri() + '?mode=ro', uri=True)
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        if not self.read_only:
            db.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, mtime INTEGER, content_hash TEXT,
          type TEXT, title TEXT, date TEXT, tags TEXT, note_id TEXT, indexed_at TEXT);
        CREATE TABLE IF NOT EXISTS chunks(chunk_id TEXT PRIMARY KEY, path TEXT REFERENCES files(path) ON DELETE CASCADE,
          heading TEXT, text TEXT, note_id TEXT, type TEXT, date TEXT, layer TEXT, vector BLOB, indexed_at TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(chunk_id UNINDEXED, terms, tokenize='unicode61');
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_personal USING fts5(chunk_id UNINDEXED, terms, tokenize='unicode61');
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_knowledge USING fts5(chunk_id UNINDEXED, terms, tokenize='unicode61');
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_source_evidence USING fts5(chunk_id UNINDEXED, terms, tokenize='unicode61');
        CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
        CREATE INDEX IF NOT EXISTS chunks_layer ON chunks(layer);
            ''')
        try:
            with db:
                yield db
        finally:
            db.close()

    def embedding(self):
        if self._embed is None:
            self._embed = Embedder(self.model_path)
        return self._embed

    def signature(self):
        manifest = self.model_path / 'manifest.json'
        if not manifest.exists():
            raise RuntimeError('本地模型缺失。安装阶段显式运行 download_model.py；检索不会自动联网')
        return digest(manifest.read_bytes() + b'|chunk-v3-layered-fts|mean-norm|128')

    def index(self, rebuild=False):
        with self.lock(), self.db() as db:
            if (self.root/'90_Inbox/Pending_Recovery.md').exists():
                raise RuntimeError('发现未完成写入，请先运行 recover')
            sig = self.signature()
            old = db.execute("SELECT value FROM settings WHERE key='signature'").fetchone()
            if old and old[0] != sig and not rebuild:
                raise RuntimeError('模型/分块配置变更，请运行 rebuild')
            if rebuild:
                for table in ('fts', 'fts_personal', 'fts_knowledge', 'fts_source_evidence'):
                    db.execute(f'DELETE FROM {table}')
                db.execute('DELETE FROM files')
            counts = dict(added=0, updated=0, deleted=0, skipped=0, chunks_added=0, chunks_removed=0)
            known = {r['path']: dict(r) for r in db.execute('SELECT * FROM files')}
            seen = set()
            ids = set()
            for path in self.notes():
                rel = path.relative_to(self.root).as_posix()
                seen.add(rel)
                raw = path.read_bytes()
                sha = digest(raw)
                if rel in known and sha == known[rel]['content_hash']:
                    counts['skipped'] += 1
                    nid = known[rel]['note_id']
                    if nid in ids: raise ValueError('重复 ID: ' + nid)
                    ids.add(nid)
                    continue
                meta, body = parse(raw.decode('utf-8-sig'))
                check_note(meta, body)
                if meta['id'] in ids: raise ValueError('重复 ID: ' + meta['id'])
                ids.add(meta['id'])
                pieces = chunks(body, self.embedding().tokenizer)
                vectors = self.embedding().encode([p[1] for p in pieces])
                counts['chunks_removed'] += self.remove_index(db, rel)
                db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?)',
                    (rel, path.stat().st_mtime_ns, sha, meta['type'], meta['title'], str(meta.get('date','')),
                     json.dumps(meta.get('tags',[]), ensure_ascii=False), meta['id'], now()))
                layer = 'core' if path.parent.name == '00_System' and meta['type'] in {'profile','goal','constraint','principle','system'} else ('knowledge' if meta['type']=='knowledge' else 'personal')
                for i, ((heading, text), vec) in enumerate(zip(pieces, vectors)):
                    cid = digest(rel + ':' + str(i) + ':' + text)[:24]
                    db.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (cid, rel, heading, text, meta['id'], meta['type'], str(meta.get('date','')), layer, vec.astype('<f4').tobytes(), now()))
                    searchable = ' '.join([meta['title'], meta['id'], str(meta.get('date','')), ' '.join(meta.get('tags',[])), heading, text])
                    fts_table = 'fts_knowledge' if layer == 'knowledge' else 'fts_personal'
                    db.execute(f'INSERT INTO {fts_table} VALUES(?,?)', (cid, terms(searchable)))
                counts['chunks_added'] += len(pieces)
                counts['updated' if rel in known else 'added'] += 1
            for evidence in self.source_evidence():
                path, rel = evidence['path'], evidence['relative']
                seen.add(rel)
                citation_bytes = evidence['citation_path'].read_bytes() if evidence['citation_path'].is_file() else b''
                sha = digest(path.read_bytes() + b'|citations|' + citation_bytes)
                if rel in known and sha == known[rel]['content_hash']:
                    counts['skipped'] += 1
                    continue
                raw_pieces = chunks(path.read_text(encoding='utf-8-sig'), self.embedding().tokenizer)
                locator_records = []
                for item in evidence['citations']:
                    locator = str(item.get('locator') or '').strip()
                    text = str(item.get('text') or '').strip()
                    normalized = re.sub(r'\s+', '', text)
                    if locator and len(normalized) >= 8:
                        locator_records.append((locator, text, normalized))
                used_citations, pieces = set(), []
                for heading, text in raw_pieces:
                    normalized_piece = re.sub(r'\s+', '', text)
                    matched = None
                    for index, (locator, citation_text, normalized_citation) in enumerate(locator_records):
                        probe = normalized_citation[:120]
                        if probe in normalized_piece or normalized_piece[:120] in normalized_citation:
                            matched = locator; used_citations.add(index); break
                    pieces.append((matched or heading or 'source', text))
                # Locator snippets that Docling could not align to a Markdown chunk remain
                # searchable as small provenance records; the full extraction itself is indexed once.
                for index, (locator, citation_text, _) in enumerate(locator_records):
                    if index not in used_citations:
                        pieces.append((locator, citation_text))
                deduplicated = {}
                for heading, text in pieces:
                    deduplicated.setdefault(text, []).append(heading)
                pieces = []
                for text, headings in deduplicated.items():
                    pages = list(dict.fromkeys(h for h in headings if str(h).startswith('p.')))
                    for heading in (pages or [headings[0]]):
                        pieces.append((heading, text))
                vectors = self.embedding().encode([p[1] for p in pieces])
                counts['chunks_removed'] += self.remove_index(db, rel)
                db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?)',
                    (rel, path.stat().st_mtime_ns, sha, 'source_evidence', evidence['title'], evidence['date'],
                     json.dumps(evidence['tags'], ensure_ascii=False), evidence['source_id'], now()))
                for i, ((heading, text), vec) in enumerate(zip(pieces, vectors)):
                    cid = digest(rel + ':source-evidence:' + str(i) + ':' + heading + ':' + text)[:24]
                    db.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (cid, rel, heading, text, evidence['source_id'], 'source_evidence', evidence['date'],
                         'source_evidence', vec.astype('<f4').tobytes(), now()))
                    searchable = ' '.join([evidence['title'], evidence['source_id'], heading, text])
                    db.execute('INSERT INTO fts_source_evidence VALUES(?,?)', (cid, terms(searchable)))
                counts['chunks_added'] += len(pieces)
                counts['updated' if rel in known else 'added'] += 1
            for rel in set(known) - seen:
                counts['chunks_removed'] += self.remove_index(db, rel)
                counts['deleted'] += 1
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('signature',sig))
            self.log.info('index %s', counts)
            return counts

    @staticmethod
    def remove_index(db, rel):
        n = db.execute('SELECT count(*) FROM chunks WHERE path=?',(rel,)).fetchone()[0]
        for table in ('fts', 'fts_personal', 'fts_knowledge', 'fts_source_evidence'):
            db.execute(f'DELETE FROM {table} WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE path=?)',(rel,))
        db.execute('DELETE FROM files WHERE path=?',(rel,))
        return n

    def explicit_relations(self, db, note_id):
        row = db.execute('SELECT path FROM files WHERE note_id=?', (note_id,)).fetchone()
        if not row:
            return set()
        try:
            meta, body = parse(self.safe(row['path']).read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            return set()
        raw = set()
        for field in ['related_experiences', 'related_decisions', 'related_models', 'related_projects', 'projects']:
            raw.update(meta.get(field) or [])
        for link in re.findall(r'\[\[([^\]]+)\]\]', body):
            raw.add(link.split('|', 1)[0].split('#', 1)[0].strip())
        known = {r['note_id']: r['note_id'] for r in db.execute('SELECT note_id FROM files')}
        known.update({Path(r['path']).stem: r['note_id'] for r in db.execute('SELECT path,note_id FROM files')})
        return {known[target] for target in raw if target in known and known[target] != note_id}

    def search(self, query, mode='hybrid', top_k=None, layer='all', kind=None, retrieval_profile=None):
        top_k = min(max(int(top_k or self.cfg['search']['final_top_k']),1),50)
        profile = retrieval_profile or self.cfg.get('search', {}).get('ranking_profile', 'v0_1')
        if profile not in RETRIEVAL_PROFILES:
            raise ValueError('未知 retrieval profile: ' + str(profile))
        features = RETRIEVAL_PROFILES[profile]
        with self.db() as db:
            sig = db.execute("SELECT value FROM settings WHERE key='signature'").fetchone()
            if not sig: raise RuntimeError('索引未建立，请运行 index')
            if sig[0] != self.signature(): raise RuntimeError('模型配置已变化，请 rebuild')
            where, params = [], []
            if profile == 'v0_1': where.append("c.type!='system'")
            effective_layer = layer
            if layer == 'all':
                if source_evidence_intent(query):
                    effective_layer = 'source_evidence'
                    where.append('c.layer=?'); params.append('source_evidence')
                    page = requested_page(query)
                    if page:
                        where.append('c.heading=?'); params.append(page)
                elif knowledge_overview_intent(query):
                    effective_layer = 'knowledge'
                    where.append('c.layer=?'); params.append('knowledge')
                else:
                    # Keep ordinary personal-memory retrieval invariant as large
                    # books arrive. External Knowledge is entered by document
                    # intent or by an explicit --layer selection.
                    effective_layer = 'personal_context'
                    where.append("c.layer IN ('core','personal')")
            else:
                where.append('c.layer=?'); params.append(layer)
            if kind: where.append('c.type=?'); params.append(kind)
            clause = (' AND ' + ' AND '.join(where)) if where else ''
            fts_table = {
                'source_evidence': 'fts_source_evidence',
                'knowledge': 'fts_knowledge',
                'personal_context': 'fts_personal',
                'core': 'fts_personal',
                'personal': 'fts_personal',
            }.get(effective_layer, 'fts_personal')
            rankings = []
            rows_by_id = {}
            keyword_ids, semantic_ids = set(), set()
            q = None
            if mode in {'keyword','hybrid'}:
                tokens = list(dict.fromkeys(terms(query).split()))[:80]
                if tokens:
                    match = ' OR '.join('"'+t.replace('"','""')+'"' for t in tokens)
                    rows = db.execute(f'SELECT c.*,bm25({fts_table}) AS bm FROM {fts_table} JOIN chunks c ON c.chunk_id={fts_table}.chunk_id WHERE {fts_table} MATCH ?' + clause + ' ORDER BY bm LIMIT ?',
                        [match,*params,self.cfg['search']['keyword_top_k']]).fetchall()
                    keyword_ids = {r['chunk_id'] for r in rows}
                    rankings.append([r['chunk_id'] for r in rows]); rows_by_id.update({r['chunk_id']:dict(r) for r in rows})
            if mode in {'semantic','hybrid'}:
                q = self.embedding().encode([query])[0]
                cursor = db.execute('SELECT c.* FROM chunks c WHERE 1=1'+clause, params)
                best = []
                while batch := cursor.fetchmany(1024):
                    mat = np.stack([np.frombuffer(r['vector'], dtype='<f4') for r in batch])
                    similarities = mat @ q
                    best.extend((float(s),dict(r)) for s,r in zip(similarities,batch))
                    best = sorted(best,key=lambda x:x[0],reverse=True)[:self.cfg['search']['semantic_top_k']]
                semantic_ids = {r['chunk_id'] for _,r in best}
                rankings.append([r['chunk_id'] for _,r in best])
                for score,r in best:
                    r['semantic_score'] = score; rows_by_id[r['chunk_id']] = r
            scores = {}
            for ranking in rankings:
                for rank,cid in enumerate(ranking,1): scores[cid] = scores.get(cid,0) + 1/(60+rank)
            base_scores = dict(scores)
            authority_boosts, relation_boosts = {}, {}
            if 'authority' in features:
                type_boosts = query_type_boosts(query)
                for cid, row in rows_by_id.items():
                    boost = type_boosts.get(row['type'], 0)
                    if boost:
                        scores[cid] = scores.get(cid, 0) + boost
                        authority_boosts[cid] = boost
            if 'relations' in features and relationship_intent(query) and scores:
                seeds = []
                for cid in sorted(scores, key=scores.get, reverse=True):
                    note_id = rows_by_id[cid]['note_id']
                    if note_id not in seeds:
                        seeds.append(note_id)
                    if len(seeds) == 2:
                        break
                targets = set()
                for note_id in seeds:
                    targets.update(self.explicit_relations(db, note_id))
                for target in targets - set(seeds):
                    candidates = [cid for cid, row in rows_by_id.items() if row['note_id'] == target]
                    if candidates:
                        cid = max(candidates, key=lambda value: (scores.get(value, 0), rows_by_id[value].get('semantic_score', -1)))
                        boost = 0.020
                        scores[cid] = scores.get(cid, 0) + boost
                        relation_boosts[cid] = boost
            ordered = sorted(scores, key=scores.get, reverse=True)
            if 'diversity' in features:
                cap = int(self.cfg.get('search', {}).get('max_chunks_per_note', 2))
                selected, per_note = [], {}
                for cid in ordered:
                    note_id = rows_by_id[cid]['note_id']
                    if per_note.get(note_id, 0) >= cap:
                        continue
                    selected.append(cid)
                    per_note[note_id] = per_note.get(note_id, 0) + 1
                    if len(selected) == top_k:
                        break
            else:
                selected = ordered[:top_k]
            result = []
            for cid in selected:
                r = rows_by_id[cid]
                item = {k:r[k] for k in ['chunk_id','path','heading','note_id','type','date','layer','text']} | {
                    'text': r['text'][:1000], 'score':round(scores[cid],6),
                    'semantic_score':round(r['semantic_score'],4) if 'semantic_score' in r else None,
                    'wikilink': '[['+Path(r['path']).stem+']]'}
                item['retrieval_scope'] = effective_layer
                if profile != 'v0_1':
                    item['ranking'] = {'profile': profile, 'base_score': round(base_scores.get(cid, 0), 6),
                                       'authority_boost': round(authority_boosts.get(cid, 0), 6),
                                       'relationship_boost': round(relation_boosts.get(cid, 0), 6),
                                       'keyword_candidate': cid in keyword_ids,
                                       'semantic_candidate': cid in semantic_ids}
                result.append(item)
            return result

    def search_diagnostic(self, query, mode='hybrid', top_k=None, layer='all', kind=None, retrieval_profile=None):
        candidates = self.search(query, mode, top_k, layer, kind, retrieval_profile)
        query_terms = set(terms(query).split())
        coverages = []
        for row in candidates:
            candidate_terms = set(terms(' '.join([row.get('heading') or '', row.get('text') or ''])).split())
            coverages.append(len(query_terms & candidate_terms) / max(1, len(query_terms)))
        max_lexical = max(coverages, default=0)
        max_semantic = max((row.get('semantic_score') if row.get('semantic_score') is not None else -1 for row in candidates), default=-1)
        search_cfg = self.cfg.get('search', {})
        no_sem = float(search_cfg.get('no_evidence_semantic_max', 0.35))
        no_lex = float(search_cfg.get('no_evidence_lexical_max', 0.12))
        weak_sem = float(search_cfg.get('weak_evidence_semantic_max', 0.50))
        weak_lex = float(search_cfg.get('weak_evidence_lexical_max', 0.15))
        if not candidates or (max_semantic < no_sem and max_lexical < no_lex):
            status = 'no_relevant_evidence'
        elif max_semantic < weak_sem and max_lexical < weak_lex:
            status = 'weak'
        else:
            status = 'supported'
        return {'status': status,
                'signals': {'max_semantic_score': round(max_semantic, 4),
                            'max_lexical_query_coverage': round(max_lexical, 4),
                            'thresholds': {'no_evidence_semantic_max': no_sem,
                                           'no_evidence_lexical_max': no_lex,
                                           'weak_evidence_semantic_max': weak_sem,
                                           'weak_evidence_lexical_max': weak_lex}},
                'candidates': candidates}

    def validate(self):
        errors, notes = [], {}
        for p in self.notes():
            try:
                meta,body = parse(p.read_text(encoding='utf-8-sig')); check_note(meta,body)
                if meta['id'] in notes: raise ValueError('重复 ID')
                if meta.get('type') == 'knowledge' and meta.get('schema_revision') in {'knowledge-v0.3', 'knowledge-v0.3.1'}:
                    source = self.safe(meta['source_path'])
                    if not source.is_file():
                        raise ValueError('managed source 不存在: ' + meta['source_path'])
                    manifest = source.parent / 'source-manifest.yaml'
                    if not manifest.exists():
                        raise ValueError('managed source manifest 不存在')
                    source_meta = yaml.safe_load(manifest.read_text(encoding='utf-8')) or {}
                    if source_meta.get('source_hash') != meta.get('source_hash'):
                        raise ValueError('managed source manifest hash 不匹配')
                    if meta.get('schema_revision') == 'knowledge-v0.3.1' and meta.get('content_origin') == 'original':
                        evidence = self.safe(meta.get('source_evidence_path', ''))
                        if not evidence.is_file():
                            raise ValueError('source evidence 不存在: ' + str(meta.get('source_evidence_path')))
                        if meta.get('content_storage') != 'managed_source':
                            raise ValueError('original Knowledge 必须使用 content_storage: managed_source')
                notes[meta['id']] = (p,meta,body)
            except Exception as exc: errors.append(f'{p.name}: {exc}')
        targets = set(notes) | {p.stem for p,_,_ in notes.values()}
        for p,meta,body in notes.values():
            for field in ['evidence','projects','related_experiences','related_decisions','related_models','related_projects']:
                for target in meta.get(field,[]):
                    if target not in targets: errors.append(f'{p.name}: {field} 不存在的 ID {target}')
            prose=re.sub(r'```.*?```|`[^`\n]*`','',body,flags=re.S)
            for link in re.findall(r'\[\[([^]|#]+)(?:[^]]*)\]\]', yaml.safe_dump(meta,allow_unicode=True)+'\n'+prose):
                if link not in targets: errors.append(f'{p.name}: 无法解析链接 [[{link}]]')
        return {'notes':len(notes), 'errors':errors, 'valid':not errors}

    def _before_reflect_commit(self, staged):
        """Test hook. Real callers do nothing between staging and CAS preflight."""
        return None

    def _save_conflict(self, import_id, staged, expected, conflicts):
        folder = self.private / 'conflicts'
        folder.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r'[^A-Za-z0-9_-]', '_', import_id)[:100]
        path = folder / f'{safe_id}-{now().replace(":", "-")}.json'
        payload = {
            'type': 'optimistic_write_conflict',
            'import_id': import_id,
            'detected_at': now(),
            'conflicts': conflicts,
            'pending_changes': {
                p.relative_to(self.root).as_posix(): {
                    'expected_hash': expected[p], 'proposed_hash': digest(text),
                    'proposed_content': text,
                } for p, text in staged.items()
            },
        }
        atomic(path, json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        return path

    def migrate_v0_2(self):
        """Add V0.2 time/source identities without changing note bodies or legacy fields."""
        with self.lock():
            staged = {}
            expected = {}
            for path in self.notes():
                raw = path.read_text(encoding='utf-8-sig')
                meta, body = parse(raw)
                if meta.get('type') not in {'experience', 'decision', 'model'}:
                    continue
                changed = False
                if 'event_date' not in meta:
                    meta['event_date'] = meta.get('date')
                    legacy_precision = meta.get('date_precision')
                    meta['event_date_precision'] = ('exact' if meta.get('date') else
                                                    ('approximate' if legacy_precision == 'approximate' else 'unknown'))
                    if meta.get('date_text'):
                        meta['event_date_raw'] = meta['date_text']
                    changed = True
                if 'recorded_at' not in meta:
                    meta['recorded_at'] = meta.get('created_at')
                    changed = True
                if 'source_materials' not in meta:
                    source_ref = meta.get('source', 'legacy record')
                    material_id = 'MAT-' + digest(str(source_ref))[:16]
                    meta['source_materials'] = [{
                        'material_id': material_id,
                        'source_type': 'chat_history' if '聊天' in str(source_ref) else 'other',
                        'source_ref': source_ref,
                    }]
                    changed = True
                if 'reflection_imports' not in meta:
                    material_id = meta['source_materials'][0]['material_id']
                    source_key = meta.get('source_key')
                    import_id = source_key or 'IMP-legacy-' + digest(meta['id'] + str(meta.get('created_at')))[:16]
                    meta['reflection_imports'] = [{
                        'import_id': import_id, 'material_id': material_id, 'mode': 'current',
                        'event_date': meta.get('event_date'),
                        'event_date_precision': meta.get('event_date_precision', 'unknown'),
                        'event_date_raw': meta.get('event_date_raw'),
                        'imported_at': meta.get('recorded_at'),
                    }]
                    changed = True
                if meta.get('schema_revision') != 'reflect-v0.2':
                    meta['schema_revision'] = 'reflect-v0.2'
                    changed = True
                if changed:
                    check_note(meta, body)
                    staged[path] = dump(meta, body)
                    expected[path] = digest(raw)
            conflicts = []
            for path, wanted in expected.items():
                actual = file_digest(path)
                if actual != wanted:
                    conflicts.append({'path': str(path), 'expected_hash': wanted, 'current_hash': actual})
            if conflicts:
                artifact = self._save_conflict('IMP-migrate-v0.2', staged, expected, conflicts)
                raise WriteConflict(f'迁移前文件已变化；未覆盖。待处理修改：{artifact}', artifact)
            for path, text in staged.items():
                atomic(path, text)
            config_before = file_digest(self.config_path)
            cfg = dict(self.cfg)
            cfg['version'] = 2
            cfg['personal_os_version'] = PERSONAL_OS_VERSION
            cfg['reflect_version'] = REFLECT_VERSION
            cfg['retrieval_baseline'] = 'Retrieval Evaluation v1.1 / Golden Set 18 cases'
            if file_digest(self.config_path) != config_before:
                raise WriteConflict('config.yaml 在迁移期间发生变化；笔记已完成兼容字段迁移，配置未覆盖')
            atomic(self.config_path, yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
            self.cfg = cfg
            return {'version': PERSONAL_OS_VERSION, 'migrated': len(staged),
                    'files': [p.relative_to(self.root).as_posix() for p in staged]}

    def migrate_v0_3(self):
        """Enable Knowledge Ingest without rewriting existing Markdown notes."""
        with self.lock():
            before = file_digest(self.config_path)
            cfg = dict(self.cfg)
            cfg['personal_os_version'] = PERSONAL_OS_VERSION
            cfg['reflect_version'] = REFLECT_VERSION
            cfg['knowledge_ingest_version'] = '0.3.0'
            cfg.setdefault('managed_sources', {})['path'] = '04_Knowledge/_Sources'
            cfg['managed_sources']['indexed'] = False
            if file_digest(self.config_path) != before:
                raise WriteConflict('config.yaml 在 V0.3 迁移期间发生变化；未覆盖')
            (self.root/'04_Knowledge/_Sources').mkdir(parents=True, exist_ok=True)
            atomic(self.config_path, yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
            self.cfg = cfg
            return {'version': PERSONAL_OS_VERSION, 'notes_changed': 0,
                    'managed_sources': str(self.root/'04_Knowledge/_Sources')}

    def reflect(self, packet):
        """Codex supplies source-separated candidates; deterministic writer enforces invariants."""
        mode = packet.get('mode') or infer_reflect_mode(packet.get('request_text', ''))
        if mode not in {'current','backfill','update'}:
            raise ValueError('mode 必须为 current/backfill/update')
        if packet.get('test_only') or not any(packet.get(k) for k in ['experience','decision','core_updates','models']):
            return {'skipped':True, 'reason':'测试或没有可沉淀经历'}
        with self.lock():
            if (self.root/'90_Inbox/Pending_Recovery.md').exists():
                raise RuntimeError('发现未完成写入，请先运行 recover')
            current = {}
            snapshots = {}
            for p in self.notes():
                raw = p.read_text(encoding='utf-8-sig')
                meta,body = parse(raw)
                current[meta['id']] = (p,meta,body)
                snapshots[p] = digest(raw)
            key = packet.get('import_id') or packet.get('source_key')
            if not key or not isinstance(key,str): raise ValueError('import_id 是重试去重的必填稳定标识（兼容 source_key）')
            matches = [v for v in current.values() if v[1].get('source_key') == key or
                       any(s.get('source_key') == key or s.get('import_id') == key for s in v[1].get('reflection_sources',[])) or
                       any(s.get('import_id') == key for s in v[1].get('reflection_imports',[]))]
            if matches:
                return {'duplicate':True,'experience':matches[0][1]['id'], 'index': '请运行 index 同步'}
            exp = packet.get('experience') or {}
            imported_at = now()
            source = packet.get('source') or exp.get('source')
            if mode in {'backfill','update'} and not source:
                raise ValueError('backfill/update 必须保留 source 来源说明')
            source = source or '用户本次对话自述'
            date = packet.get('event_date', packet.get('occurred_on', exp.get('event_date', exp.get('date'))))
            date_text = packet.get('event_date_raw', packet.get('date_text', exp.get('event_date_raw', exp.get('date_text',''))))
            date_precision = packet.get('event_date_precision', exp.get('event_date_precision'))
            if date is not None:
                date_precision = date_precision or 'exact'
            elif date_text:
                date_precision = date_precision or 'approximate'
            elif mode == 'current':
                date = imported_at[:10]; date_precision = 'exact'
            elif mode == 'backfill' and date_precision != 'unknown':
                raise ValueError('backfill 必须提供 event_date、模糊原文，或显式 event_date_precision: unknown；不能默认今天')
            else:
                date_precision = date_precision or 'unknown'
            if date_precision not in EVENT_DATE_PRECISIONS:
                raise ValueError('event_date_precision 必须为 exact/approximate/unknown')
            if date_precision == 'approximate' and not date_text:
                raise ValueError('模糊日期必须保留 event_date_raw')
            if date is not None:
                date = str(date); datetime.strptime(date,'%Y-%m-%d')
            material = packet.get('material') or {}
            source_type = material.get('source_type') or packet.get('source_type') or (
                'current_conversation' if mode == 'current' else ('user_recollection' if source == '用户回忆' else 'other'))
            if source_type not in SOURCE_TYPES:
                raise ValueError('source_type 无效')
            source_ref = material.get('source_ref') or packet.get('source_ref') or source
            material_id = material.get('material_id') or packet.get('source_material_id') or ('MAT-' + digest(source_type+'|'+source_ref)[:16])
            material_hash = material.get('content_hash') or packet.get('source_content_hash')
            event_key = packet.get('event_key')
            exp_id = exp.get('id')
            if event_key:
                existing = [nid for nid,(_,m,_) in current.items() if m.get('event_key') == event_key and m['type']=='experience']
                if len(existing)>1: raise ValueError('event_key 对应多个经历，请先核对')
                if existing:
                    if exp_id and exp_id != existing[0]: raise ValueError('event_key 与指定 Experience 冲突')
                    exp_id = existing[0]
            if exp_id and (exp_id not in current or current[exp_id][1]['type']!='experience'):
                raise ValueError('指定 Experience 不存在或类型不符')
            if mode == 'update' and exp and not exp_id:
                raise ValueError('update 必须指定已有 Experience id；不自动新建')
            if mode == 'current' and not exp:
                raise ValueError('current 需要 Experience；仅更新已有记录请用 update')
            def allocate(prefix):
                stem = prefix+'-'+(date or imported_at)[:4]+'-'
                numbers = [int(i[len(stem):]) for i in current if i.startswith(stem) and i[len(stem):].isdigit()]
                return stem+f'{max(numbers,default=0)+1:04d}'
            if exp and not exp_id: exp_id = allocate('EXP')
            dec = packet.get('decision')
            if dec and dec.get('id') and (dec['id'] not in current or current[dec['id']][1]['type']!='decision'):
                raise ValueError('指定 Decision 不存在或类型不符')
            if mode == 'update' and dec and not dec.get('id'):
                raise ValueError('update 必须指定已有 Decision id')
            dec_id = dec.get('id') or allocate('DEC') if dec else None
            exp_ids = {exp_id} if exp_id else set()
            anchors = exp_ids | set(packet.get('evidence',[]))
            if not anchors and dec_id in current: anchors.add(dec_id)
            if not anchors:
                anchors.update(m['id'] for m in packet.get('models',[]) if m.get('id') in current)
            if not anchors and packet.get('core_updates'):
                anchors.add('SYS-Profile')
            evidence_text = ', '.join('[['+e+']]' for e in sorted(anchors))
            audit = dict(import_id=key,source_key=key,material_id=material_id,mode=mode,
                         source=source,source_type=source_type,source_ref=source_ref,
                         event_date=date,event_date_precision=date_precision,
                         event_date_raw=date_text or None,occurred_on=date,date_text=date_text,
                         imported_at=imported_at)
            material_record = dict(material_id=material_id, source_type=source_type, source_ref=source_ref)
            if material_hash:
                material_record['content_hash'] = material_hash
            audit_text = f'\n\n来源：{source}\n发生时间：{date or date_text or "未提供（未改动原发生日期）"}\n导入时间：{imported_at}'
            staged = {}
            expected = {}
            report = {'mode':mode,'created':[], 'updated':[]}
            def stage(path,meta,body):
                meta = dict(meta)
                if meta.get('type') in {'experience', 'decision', 'model'}:
                    if 'event_date' not in meta:
                        meta['event_date'] = meta.get('date')
                        meta['event_date_precision'] = 'exact' if meta.get('date') else 'unknown'
                        if meta.get('date_text'):
                            meta['event_date_raw'] = meta['date_text']
                    meta.setdefault('recorded_at', meta.get('created_at'))
                sources = list(meta.get('reflection_sources',[]))
                if not any(s.get('source_key')==key or s.get('import_id')==key for s in sources): sources.append(audit)
                meta['reflection_sources'] = sources
                imports = list(meta.get('reflection_imports', []))
                if not any(s.get('import_id') == key for s in imports): imports.append(audit)
                meta['reflection_imports'] = imports
                materials = list(meta.get('source_materials', []))
                if not any(s.get('material_id') == material_id for s in materials): materials.append(material_record)
                meta['source_materials'] = materials
                meta['schema_revision'] = 'reflect-v0.2'
                check_note(meta,body)
                staged[path] = dump(meta,body)
                expected[path] = snapshots.get(path)
            def metadata(kind,nid,title,provenance='user_explicit'):
                return dict(schema_version=1,type=kind,id=nid,date=date,title=title,
                    importance=exp.get('importance','normal'),confidence=exp.get('confidence',1.0),
                    source=source,provenance=provenance,tags=[],created_at=imported_at,updated_at=imported_at,
                    event_date=date,event_date_precision=date_precision,event_date_raw=date_text or None,
                    recorded_at=imported_at,date_precision='day' if date_precision=='exact' else date_precision,
                    date_text=date_text)
            # Core entries: stable key, explicit change status, history is permanent Markdown.
            history = []
            for item in packet.get('core_updates',[]):
                if item.get('provenance') != 'user_explicit':
                    raise ValueError('Core 快照只接受 user_explicit；推断必须进入 Model')
                category = item.get('target','profile')
                names = {'profile':'Profile','goal':'Current_Goals','constraint':'Constraints','principle':'Principles'}
                if category not in names: raise ValueError('不支持的 core target')
                target = self.safe('00_System/'+names[category]+'.md')
                text = staged.get(target) or target.read_text(encoding='utf-8')
                meta,body = parse(text)
                item_key = item['key']
                if not re.fullmatch('[a-z0-9_-]{1,80}',item_key): raise ValueError('core key 应为稳定英文短键')
                pattern = re.compile(r'<!-- item:'+re.escape(item_key)+r' -->\n(.*?)\n<!-- /item -->', re.S)
                found = pattern.search(body)
                if mode=='update' and not found: raise ValueError('update 的 core key 不存在，请先检索确认')
                evidence = set(item.get('evidence',[])) | anchors
                value = item['value'].strip()
                if not value or '<!--' in value: raise ValueError('非法 core value')
                if mode=='backfill' or item.get('state')=='historical':
                    history.append(f'## 历史材料回填 / {imported_at}\n\n{names[category]} / {item_key}\n历史状态：{value}\n依据：{evidence_text}'+audit_text)
                    continue
                if found:
                    old = found[1]
                    old_value = old.splitlines()[0].removeprefix('- ')
                    evidence.update(re.findall(r'\[\[([^]]+)\]\]',old))
                    if old_value != value:
                        if item.get('change') not in {'refine','changed'}:
                            raise ValueError('值变化必须显式指定 change: refine 或 changed')
                        history.append(f'## {now()} — {names[category]} / {item_key}\n\n{old}\n\n变为：{value}\n依据：{evidence_text}\n性质：{item["change"]}'+audit_text)
                confirmed_on = item.get('confirmed_on') or (imported_at[:10] if mode=='update' else date)
                datetime.strptime(confirmed_on,'%Y-%m-%d')
                block = f'<!-- item:{item_key} -->\n- {value}\n  - provenance: user_explicit\n  - evidence: '+', '.join('[['+e+']]' for e in sorted(evidence))+f'\n  - last_confirmed: {confirmed_on}\n<!-- /item -->'
                body = pattern.sub(lambda _:block,body) if found else body+'\n\n'+block
                body = body.replace('尚无已沉淀条目。后续仅根据主动触发的反思更新；历史依据保留在经历和决策中。','').strip()
                meta['updated_at'] = now(); stage(target,meta,body)
                report['updated'].append(names[category])
            if history:
                p = self.safe('00_System/Profile_History.md')
                meta,body = parse(p.read_text(encoding='utf-8'))
                meta['updated_at']=now(); stage(p,meta,body+'\n\n'+'\n\n'.join(history))
                report['updated'].append('Profile_History')
            model_ids = []
            for model in packet.get('models',[]):
                if model.get('id') and (model['id'] not in current or current[model['id']][1]['type']!='model'):
                    raise ValueError('指定 Model 不存在或类型不符')
                if mode=='update' and not model.get('id'): raise ValueError('update 必须指定已有 Model id')
                mid = model.get('id') or allocate('MOD')
                prov = model.get('provenance','ai_observation')
                if prov not in {'ai_observation','behavior_inferred','user_explicit'}: raise ValueError('Model provenance 无效')
                if mid in current:
                    path,meta,body = current[mid]
                    if meta['type']!='model': raise ValueError('目标不是 Model')
                    if meta['provenance'] != prov:
                        raise ValueError('不能将既有 Model 的推断来源改成用户事实；请另建有明确来源的记录')
                    body += '\n\n## 历史观察 / '+now()+'\n\n此前状态：'+str(meta.get('status'))+'；此前置信度：'+str(meta.get('confidence'))
                    meta = dict(meta); meta['updated_at']=now()
                    report['updated'].append(mid)
                else:
                    meta=metadata('model',mid,model['title'],prov)
                    path=self.safe('05_Models/'+mid+'.md'); body='# '+model['title']
                    report['created'].append(mid)
                meta.update(provenance=prov,confidence=model['confidence'],status=model.get('status','observing'),
                    evidence=sorted(set(meta.get('evidence',[]))|set(model.get('evidence',[]))|anchors))
                body+='\n\n## '+('AI Observation' if prov=='ai_observation' else ('行为推导' if prov=='behavior_inferred' else '用户明确表达'))+' / '+(date or '时间未知')+'\n\n'+model['observation']+'\n\n依据：'+', '.join('[['+e+']]' for e in meta['evidence'])+audit_text
                stage(path,meta,body); current[mid]=(path,meta,body); model_ids.append(mid)
            if dec:
                if dec_id in current:
                    path,meta,body=current[dec_id]
                    if meta['type']!='decision': raise ValueError('目标不是 Decision')
                    meta=dict(meta); meta['updated_at']=now()
                    body+='\n\n## 补充 / 修正 / '+imported_at+'\n\n'+dec.get('review','补充已有决策材料')+'\n\n依据：'+evidence_text+audit_text
                    for field,label in {'background':'当时背景补充','considerations':'考虑补充','tradeoffs':'权衡补充','choice':'最终决策修正（此前记录保留）','reason':'理由补充 / 修正','assumptions':'假设补充','outcome':'Outcome'}.items():
                        if dec.get(field): body+='\n\n### '+label+'\n\n'+dec[field]
                    report['updated'].append(dec_id)
                else:
                    for field in ['title','question','options','choice','reason']:
                        if not dec.get(field): raise ValueError('Decision 缺少 '+field)
                    if len(dec['options'])<2: raise ValueError('Decision 至少两个选项')
                    meta=metadata('decision',dec_id,dec['title']); meta.update(status=dec.get('status','decided'),domain=dec.get('domain',''),
                        confidence=dec.get('confidence'),related_experiences=sorted(exp_ids),related_projects=[],related_models=model_ids)
                    body='# '+dec['title']+'\n\n## 问题\n\n'+dec['question']+'\n\n## 可选方案\n\n'+'\n'.join('- '+o for o in dec['options'])
                    labels={'background':'当时背景','considerations':'我的核心考虑','tradeoffs':'权衡','choice':'最终决策','reason':'为什么','assumptions':'当时关键假设','outcome':'Outcome'}
                    for field,label in labels.items():
                        if dec.get(field): body+='\n\n## '+label+'\n\n'+dec[field]
                    if not dec.get('outcome'): body+='\n\n## Outcome\n\n尚未观察到结果；以后追加。'
                    body+='\n\n## 关联\n\n'+evidence_text
                    path=self.safe('02_Decisions/'+dec_id+'.md');report['created'].append(dec_id)
                meta['related_experiences']=sorted(set(meta.get('related_experiences',[]))|exp_ids)
                stage(path,meta,body)
            if exp:
                if exp_id in current:
                    ep,old_meta,body=current[exp_id]
                    meta=dict(old_meta);meta['updated_at']=imported_at
                    body+='\n\n## 补充 / 修正 / '+imported_at+audit_text
                    if exp.get('date') and str(exp['date']) != str(meta.get('date')):
                        if not exp.get('date_correction_reason'):
                            raise ValueError('修正原经历日期须提供 date_correction_reason')
                        body+='\n\n发生日期修正：'+str(meta.get('date'))+' → '+str(exp['date'])+'\n理由：'+exp['date_correction_reason']
                        meta['date']=str(exp['date']);meta['event_date']=str(exp['date'])
                        meta['date_precision']='day';meta['event_date_precision']='exact'
                        meta['event_date_raw']=exp.get('event_date_raw') or exp.get('date_text')
                    report['updated'].append(exp_id)
                else:
                    if not exp.get('facts'): raise ValueError('Experience 必须有用户明确表达的事实')
                    meta=metadata('experience',exp_id,exp['title'])
                    meta.update(source_key=key,domains=[],projects=[],people=[],related_decisions=[],related_models=[],tags=[])
                    body='# '+exp['title']+audit_text
                    ep=self.safe('01_Experiences/'+exp_id+'.md'); report['created'].insert(0,exp_id)
                if event_key: meta['event_key']=event_key
                for field in ['domains','projects','people','tags']:
                    meta[field]=sorted(set(meta.get(field,[]))|set(exp.get(field,[])))
                meta['related_decisions']=sorted(set(meta.get('related_decisions',[]))|({dec_id} if dec_id else set()))
                meta['related_models']=sorted(set(meta.get('related_models',[]))|set(model_ids))
                labels={'background':'事件背景','facts':'用户明确表达的事实（补充 / 修正以此为准）' if exp_id in current else '用户明确表达的事实',
                        'thoughts':'用户明确表达的想法','tradeoffs':'我的考虑与权衡',
                        'action':'最终行为 / 决策','outcome':'当前结果','questions':'尚未解决的问题','reflection':'本次复盘',
                        'behavior_inferred':'从行为推导出的信息','ai_observation':'AI观察','external_source':'外部资料提供的信息'}
                for field,label in labels.items():
                    if exp.get(field): body+='\n\n## '+label+'\n\n'+exp[field]
                links=set(exp.get('links',[]))|set(model_ids)|({dec_id} if dec_id else set())|set(exp.get('projects',[]))
                if links: body+='\n\n## 关联\n\n'+'\n'.join('- [['+i+']]' for i in sorted(links))
                stage(ep,meta,body)
            # Validate all links before any write. Entire batch is staged, source-key marker written last.
            valid_ids=set(current)|exp_ids|({dec_id} if dec_id else set())
            valid_ids |= {p.stem for p,_,_ in current.values()}
            for path,text in staged.items():
                m,b=parse(text)
                for field in ['evidence','related_experiences','related_models','related_projects','projects']:
                    for target in m.get(field,[]):
                        if target not in valid_ids: raise ValueError('未知证据/关联 ID: '+target)
                for target in re.findall(r'\[\[([^]|#]+)(?:[^]]*)\]\]',text):
                    if target not in valid_ids: raise ValueError('未知 Wikilink: '+target)
            # Obsidian does not honor our process lock.  Compare every file with the
            # exact version read before staging; preserve proposed content on conflict.
            self._before_reflect_commit(staged)
            conflicts=[]
            for path,wanted in expected.items():
                actual=file_digest(path)
                if actual != wanted:
                    conflicts.append({'path':path.relative_to(self.root).as_posix(),
                                      'expected_hash':wanted,'current_hash':actual})
            if conflicts:
                artifact=self._save_conflict(key,staged,expected,conflicts)
                raise WriteConflict('检测到 Obsidian 并发修改；未覆盖用户内容。待写修改保存在 '+str(artifact),artifact)
            # Recovery record is Markdown, outside disposable cache, removed after successful batch.
            journal=self.safe('90_Inbox/Pending_Recovery.md')
            if journal.exists(): raise RuntimeError('发现未完成写入，请先运行 recover')
            backups={p.relative_to(self.root).as_posix():p.read_text(encoding='utf-8') if p.exists() else None for p in staged}
            jm=metadata('system','SYS-PENDING','未完成写入的恢复记录')
            atomic(journal,dump(jm,'# 未完成写入的恢复记录\n\n恢复命令：recover。不要删除此文件。\n\n```json\n'+json.dumps(backups,ensure_ascii=False)+'\n```'))
            written=[]
            try:
                for p,text in staged.items():
                    actual=file_digest(p)
                    if actual != expected[p]:
                        conflicts=[{'path':p.relative_to(self.root).as_posix(),
                                    'expected_hash':expected[p],'current_hash':actual}]
                        artifact=self._save_conflict(key,staged,expected,conflicts)
                        # Roll back only files that still equal our own staged write.
                        for done in reversed(written):
                            if file_digest(done) == digest(staged[done]):
                                previous=backups[done.relative_to(self.root).as_posix()]
                                if previous is None: done.unlink(missing_ok=True)
                                else: atomic(done,previous)
                        journal.unlink(missing_ok=True)
                        raise WriteConflict('提交期间检测到并发修改；已回滚本批写入。待写修改保存在 '+str(artifact),artifact)
                    atomic(p,text); self.log.info('write %s',p.relative_to(self.root))
                    written.append(p)
                journal.unlink()
            except WriteConflict:
                raise
            except BaseException:
                # Leave journal for explicit deterministic recovery, including process crashes.
                self.log.exception('write interrupted; recover required')
                raise
        report['index']=self.index()
        return report

    def recover(self):
        with self.lock():
            p=self.safe('90_Inbox/Pending_Recovery.md')
            if not p.exists(): return {'recovered':False}
            _,body=parse(p.read_text(encoding='utf-8'))
            backups=json.loads(re.search(r'```json\n(.*?)\n```',body,re.S)[1])
            for rel,text in backups.items():
                target=self.safe(rel)
                if text is None: target.unlink(missing_ok=True)
                else: atomic(target,text)
            p.unlink()
        return {'recovered':True,'index':self.index()}

class Embedder:
    def __init__(self, folder):
        from tokenizers import Tokenizer
        import onnxruntime as ort
        self.tokenizer=Tokenizer.from_file(str(folder/'tokenizer.json'))
        opts=ort.SessionOptions();opts.intra_op_num_threads=4
        self.session=ort.InferenceSession(str(folder/'onnx/model_quint8_avx2.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')

    def encode(self,texts):
        result=[]
        for start in range(0,len(texts),16):
            tokens=self.tokenizer.encode_batch(texts[start:start+16])
            ids=np.array([t.ids for t in tokens],dtype=np.int64)
            mask=np.array([t.attention_mask for t in tokens],dtype=np.int64)
            data={'input_ids':ids,'attention_mask':mask,'token_type_ids':np.array([t.type_ids for t in tokens],dtype=np.int64)}
            out=self.session.run(None,{i.name:data[i.name] for i in self.session.get_inputs()})[0]
            vec=(out*mask[:,:,None]).sum(1)/np.maximum(mask.sum(1)[:,None],1)
            vec=vec/np.maximum(np.linalg.norm(vec,axis=1,keepdims=True),1e-12)
            result.extend(vec.astype(np.float32))
        return result

def terms(text):
    # Chinese single characters + overlapping bigrams support substrings without a dictionary.
    tokens=[]
    for part in re.findall(r'[\u3400-\u9fff]+|[a-zA-Z0-9_]+',text.lower()):
        if re.match(r'[\u3400-\u9fff]',part):
            tokens.extend(part[i:i+2] for i in range(max(1,len(part)-1)))
            if len(part)==1: tokens.append(part)
        else: tokens.append(part)
    return ' '.join(tokens)

def chunks(body, tokenizer):
    # Heading/paragraph boundaries first; split oversized sentences by tokenizer offsets.
    pieces=[]; heading=''; buffer=''
    tokenizer.no_truncation(); tokenizer.no_padding()
    def size(s): return len(tokenizer.encode(s).ids)
    def flush():
        nonlocal buffer
        if buffer.strip(): pieces.append((heading,buffer.strip()));buffer=''
    try:
        for block in re.split(r'\n\s*\n',body):
            if re.match(r'^#{1,6} ',block):
                flush()
                first,*rest=block.split('\n',1);heading=first.lstrip('# ').strip()
                block=rest[0] if rest else ''
            if not block.strip(): continue
            units=re.split(r'(?<=[。！？])\s*|(?<=[.!?])\s+|\n',block)
            for unit in units:
                unit=unit.strip()
                if not unit: continue
                if size(buffer+'\n'+unit)>120: flush()
                while size(unit)>120:
                    offsets=tokenizer.encode(unit,add_special_tokens=False).offsets
                    end=offsets[109][1]
                    pieces.append((heading,unit[:end]));unit=unit[end:]
                buffer += ('\n' if buffer else '')+unit
            flush()
        flush()
        return pieces or [(heading,body)]
    finally:
        tokenizer.enable_truncation(max_length=128)
        tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')

def initialize(vault,model=None,register=True):
    vault=Path(vault).resolve();root=vault/'PersonalOS'
    if not (vault/'.obsidian').is_dir(): raise ValueError('目标不是已确认 Obsidian Vault（缺少 .obsidian）')
    root.mkdir(parents=True,exist_ok=True)
    config=root/'.personal-os/config.yaml'
    for name in FOLDERS+['.personal-os/index','.personal-os/cache','.personal-os/logs','.personal-os/conflicts']:
        (root/name).mkdir(parents=True,exist_ok=True)
    (root/'04_Knowledge/_Sources').mkdir(parents=True, exist_ok=True)
    if not config.exists():
        cfg=dict(version=2,personal_os_version=PERSONAL_OS_VERSION,reflect_version=REFLECT_VERSION,
            retrieval_baseline='Retrieval Evaluation v1.1 / Golden Set 18 cases',
            vault_path=str(vault),personal_os_root='..',database_path='.personal-os/index/memory.sqlite3',
            embedding=dict(provider='local',model='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
                local_path=str(Path(model or PROJECT_ROOT/'models/multilingual-minilm').resolve()),backend='onnx-cpu-quint8',dimensions=384),
            search=dict(keyword_top_k=30,semantic_top_k=30,final_top_k=6))
        atomic(config,yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False))
    core={'Profile':('profile','当前个人状态快照'),'Current_Goals':('goal','当前目标'),
          'Principles':('principle','当前原则'),'Constraints':('constraint','当前约束'),
          'Profile_History':('history','个人状态变化历史')}
    for name,(kind,title) in core.items():
        p=root/'00_System'/f'{name}.md'
        if not p.exists():
            atomic(p,dump(dict(schema_version=1,type=kind,id='SYS-'+name,title=title,created_at=now(),updated_at=now()),
                '# '+title+'\n\n尚无已沉淀条目。后续仅根据主动触发的反思更新；历史依据保留在经历和决策中。'))
    for name in ['README','System_Architecture','Schemas']:
        p=root/'00_System'/f'{name}.md'
        if not p.exists():
            body=(PROJECT_ROOT/'docs'/f'{name}.md').read_text(encoding='utf-8')
            atomic(p,dump(dict(schema_version=1,type='system',id='SYS-'+name,title=name,created_at=now(),updated_at=now()),body))
    if register: atomic(PROJECT_ROOT/'settings.json',json.dumps({'config':str(config)},ensure_ascii=False,indent=2))
    return {'root':str(root),'config':str(config)}

def main():
    parser=argparse.ArgumentParser(description='Personal OS：本地 Markdown 记忆与检索')
    parser.add_argument('--config',help='覆盖默认 Vault 配置路径')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('init');p.add_argument('--vault',required=True);p.add_argument('--model')
    for name in ['index','rebuild','validate','recover','core','migrate-v0.2','migrate-v0.3','version']: sub.add_parser(name)
    p=sub.add_parser('search');p.add_argument('query');p.add_argument('--mode',choices=['keyword','semantic','hybrid'],default='hybrid');p.add_argument('--top-k',type=int);p.add_argument('--layer',choices=['all','core','personal','knowledge','source_evidence'],default='all');p.add_argument('--type',dest='kind');p.add_argument('--retrieval-profile',choices=sorted(RETRIEVAL_PROFILES),default=None);p.add_argument('--diagnostics',action='store_true')
    p=sub.add_parser('set-retrieval-profile');p.add_argument('profile',choices=['v0_1','optimized_v1'])
    p=sub.add_parser('reflect');p.add_argument('--input',required=True)
    p=sub.add_parser('classify-reflect-mode');p.add_argument('text')
    args=parser.parse_args()
    if args.command=='init': output=initialize(args.vault,args.model)
    elif args.command=='version':
        version_file=(PROJECT_ROOT/'VERSION')
        output={'personal_os':PERSONAL_OS_VERSION,'reflect':REFLECT_VERSION,
                'release':version_file.read_text(encoding='utf-8').strip() if version_file.exists() else 'development',
                'code':str(Path(__file__).resolve())}
    elif args.command=='classify-reflect-mode': output={'mode':infer_reflect_mode(args.text)}
    else:
        config=args.config
        if not config:
            settings=PROJECT_ROOT/'settings.json'
            if not settings.exists(): raise ValueError('请先 init --vault 路径，或传入 --config')
            config=json.loads(settings.read_text(encoding='utf-8'))['config']
        store=Store(config)
        if args.command in {'index','rebuild'}: output=store.index(args.command=='rebuild')
        elif args.command=='search':
            output=(store.search_diagnostic(args.query,args.mode,args.top_k,args.layer,args.kind,args.retrieval_profile)
                    if args.diagnostics else store.search(args.query,args.mode,args.top_k,args.layer,args.kind,args.retrieval_profile))
        elif args.command=='set-retrieval-profile':
            search_cfg = store.cfg.setdefault('search', {})
            search_cfg['ranking_profile'] = args.profile
            if args.profile == 'optimized_v1':
                search_cfg.setdefault('no_evidence_semantic_max', 0.35)
                search_cfg.setdefault('no_evidence_lexical_max', 0.12)
                search_cfg.setdefault('weak_evidence_semantic_max', 0.50)
                search_cfg.setdefault('weak_evidence_lexical_max', 0.15)
            atomic(store.config_path, yaml.safe_dump(store.cfg, allow_unicode=True, sort_keys=False))
            output={'retrieval_profile':args.profile,
                    'next_step':'运行 index 以同步可检索 note type' if args.profile=='optimized_v1' else '已立即回到 V0.1 排名与可见类型'}
        elif args.command=='validate':
            output=store.validate()
            print(json.dumps(output,ensure_ascii=False,indent=2)); return 0 if output['valid'] else 1
        elif args.command=='reflect': output=store.reflect(json.loads(Path(args.input).read_text(encoding='utf-8-sig')))
        elif args.command=='recover': output=store.recover()
        elif args.command=='migrate-v0.2': output=store.migrate_v0_2()
        elif args.command=='migrate-v0.3': output=store.migrate_v0_3()
        elif args.command=='core':
            output={name:(store.root/'00_System'/f'{name}.md').read_text(encoding='utf-8')[:12000] for name in ['Profile','Current_Goals','Principles','Constraints']}
    print(json.dumps(output,ensure_ascii=False,indent=2));return 0

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    try: sys.exit(main())
    except Exception as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
