"""Regression tests. Run: python -m unittest discover -s tests -v"""
import io
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'inventario_casa'))

from flask import Flask
from PIL import Image
from backup import create_database_backup, inspect_database_file
from backup_restore import restore_database_backup
from backup_routes import create_backup_blueprint
from database import db, init_db, read_schema_version
from inventory_routes import create_inventory_blueprint
from item_routes import create_item_blueprint
from maintenance import protect_database_requests
from media_routes import create_media_blueprint
from type_routes import create_type_blueprint


class InventorySafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='inventory-safety-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'
        self.media = self.root / 'media'
        self.backups = self.root / 'backups'
        self.path = self.data / 'inventory.db'
        self.lock = threading.RLock()
        self.error = None
        self.initialize()
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        protect_database_requests(self.app, self.lock, lambda: self.error)
        self.app.register_blueprint(create_item_blueprint(db=self.connect, media_dir=self.media))
        self.app.register_blueprint(create_media_blueprint(db=self.connect, media_dir=self.media))
        self.app.register_blueprint(create_inventory_blueprint(db=self.connect))
        self.app.register_blueprint(create_type_blueprint(db=self.connect))
        self.app.register_blueprint(create_backup_blueprint(
            db_path=self.path, backup_dir=self.backups, maintenance_lock=self.lock,
            backup_keep_manual=10, get_startup_error=lambda: self.error,
            restore_database_backup=self.restore, current_schema_version=1,
        ))
        self.client = self.app.test_client()

    def connect(self):
        return db(self.path, self.data, self.media)

    def initialize(self, path=None):
        path = self.path if path is None else path
        init_db(path, path.parent, self.media, self.backups, 1)

    def restore(self, name, prepare=None):
        return restore_database_backup(
            name, db_path=self.path, data_dir=self.data, backup_dir=self.backups,
            maintenance_lock=self.lock, backup_keep_pre_restore=5,
            init_db=self.initialize, set_startup_error=lambda value: setattr(self, 'error', value),
            current_schema_version=1, prepare_restore=prepare or self.initialize,
        )

    def add_item(self, name='Lampada'):
        response = self.client.post('/api/items', json={'name': name})
        self.assertEqual(response.status_code, 201)
        return response.json['id']

    def backup(self):
        response = self.client.post('/api/backups/create')
        self.assertEqual(response.status_code, 201)
        return response.json['filename']

    def test_connections_close_and_transactions_rollback(self):
        with self.connect() as conn:
            conn.execute('SELECT 1')
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute('SELECT 1')
        with self.assertRaisesRegex(RuntimeError, 'abort'):
            with self.connect() as conn:
                conn.execute("INSERT INTO item_types(name,created_at) VALUES('rollback','now')")
                raise RuntimeError('abort')
        with self.connect() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM item_types WHERE name='rollback'").fetchone())

    def test_unrelated_database_rejected_without_touching_current(self):
        self.add_item()
        self.backups.mkdir(exist_ok=True)
        with closing(sqlite3.connect(self.backups / 'foreign.db')) as conn:
            conn.execute('CREATE TABLE other(value TEXT)')
            conn.commit()
        self.assertFalse(inspect_database_file(self.backups / 'foreign.db')['valid'])
        before = self.path.read_bytes()
        response = self.client.post('/api/backups/restore', json={'filename': 'foreign.db'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['error_code'], 'backup_invalid_inventory')
        self.assertEqual(before, self.path.read_bytes())
        self.assertIsNone(self.error)

    def test_future_schema_is_not_downgraded(self):
        with self.connect() as conn:
            conn.execute("UPDATE app_meta SET value='99' WHERE key='schema_version'")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'backup_future_schema'):
            self.initialize()
        self.assertEqual(read_schema_version(self.path), 99)
        self.assertEqual(before, self.path.read_bytes())

    def test_future_and_malformed_backups_not_restorable(self):
        name = self.backup()
        for version, code in [('99', 'backup_future_schema'), ('broken', 'backup_invalid_schema'), ('-1', 'backup_invalid_schema')]:
            with closing(sqlite3.connect(self.backups / name)) as conn:
                conn.execute("UPDATE app_meta SET value=? WHERE key='schema_version'", (version,))
                conn.commit()
            listing = self.client.get('/api/backups').json['backups']
            selected = next(row for row in listing if row['filename'] == name)
            self.assertFalse(selected['valid'])
            self.assertEqual(selected['validation_error'], code)
            response = self.client.post('/api/backups/restore', json={'filename': name})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json['error_code'], code)

    def test_legacy_backup_without_metadata_migrates(self):
        item = self.add_item('Legacy')
        name = self.backup()
        with closing(sqlite3.connect(self.backups / name)) as conn:
            conn.execute('DROP TABLE app_meta')
            conn.execute('ALTER TABLE item_photos RENAME COLUMN label TO caption')
            conn.commit()
        self.assertTrue(inspect_database_file(self.backups / name, 1)['valid'])
        self.restore(name)
        self.assertEqual(read_schema_version(self.path), 1)
        self.assertEqual(self.client.get(f'/api/items/{item}').json['name'], 'Legacy')

    def test_foreign_key_damage_is_rejected(self):
        name = self.backup()
        with closing(sqlite3.connect(self.backups / name)) as conn:
            conn.execute("INSERT INTO item_custom_values VALUES(999,999,'orphan')")
            conn.commit()
        info = inspect_database_file(self.backups / name, 1)
        self.assertFalse(info['valid'])
        self.assertEqual(info['validation_error'], 'backup_foreign_keys')

    def test_safety_backup_failure_aborts_healthy_restore(self):
        self.add_item()
        name = self.backup()
        before = self.path.read_bytes()
        with patch('backup_restore.backup_create', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(RuntimeError, 'backup_safety_failed'):
                self.restore(name)
        self.assertEqual(before, self.path.read_bytes())
        self.assertIsNone(self.error)

    def test_failed_staged_migration_preserves_active_database(self):
        name = self.backup()
        self.add_item('Keep me')
        before = self.path.read_bytes()
        def fail(path):
            raise RuntimeError('migration failed')
        with self.assertRaisesRegex(RuntimeError, 'migration failed'):
            self.restore(name, prepare=fail)
        self.assertEqual(before, self.path.read_bytes())
        self.assertIsNone(self.error)

    def test_restore_recovers_corrupt_current_database(self):
        item = self.add_item('Recover me')
        name = self.backup()
        self.path.write_bytes(b'not a database')
        self.error = 'startup failed'
        self.restore(name)
        self.assertIsNone(self.error)
        self.assertEqual(self.client.get(f'/api/items/{item}').json['name'], 'Recover me')

    def test_restore_selected_pre_restore_backup_at_retention_limit(self):
        self.add_item('one')
        selected = create_database_backup(self.path, self.backups, prefix='inventory_pre_restore')
        self.add_item('two')
        for i in range(5):
            create_database_backup(self.path, self.backups, prefix='inventory_pre_restore')
        result = self.restore(selected.name)
        self.assertTrue(result['ok'])
        self.assertEqual(result['database']['items'], 1)
        self.assertTrue((self.backups / result['safety_backup']).exists())
        self.assertEqual(len(list(self.backups.glob('inventory_pre_restore_*.db'))), 5)

    def test_requests_wait_until_restore_finishes(self):
        name = self.backup()
        entered = threading.Event()
        release = threading.Event()
        attempted = threading.Event()
        completed = threading.Event()
        failures = []
        def prepare(path):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test timeout')
            self.initialize(path)
        def restorer():
            try:
                self.restore(name, prepare=prepare)
            except Exception as exc:
                failures.append(exc)
        def writer():
            attempted.set()
            try:
                with self.app.test_client() as client:
                    self.assertEqual(client.post('/api/items', json={'name': 'After restore'}).status_code, 201)
            except Exception as exc:
                failures.append(exc)
            finally:
                completed.set()
        a = threading.Thread(target=restorer)
        b = threading.Thread(target=writer)
        a.start()
        try:
            self.assertTrue(entered.wait(3))
            b.start()
            self.assertTrue(attempted.wait(3))
            self.assertFalse(completed.wait(.15))
        finally:
            release.set()
            a.join(6)
            if b.ident is not None:
                b.join(6)
        self.assertFalse(a.is_alive())
        self.assertFalse(b.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(inspect_database_file(self.path)['items'], 1)

    def test_recovery_blocks_edits_but_allows_backups(self):
        self.error = 'startup failed'
        self.assertEqual(self.client.post('/api/items', json={'name': 'Blocked'}).status_code, 503)
        self.assertEqual(self.client.get('/api/backups').status_code, 200)
        self.error = None
        self.add_item('Allowed again')

    def test_deleted_photo_and_item_can_be_restored_with_images(self):
        item = self.add_item()
        image = io.BytesIO()
        Image.new('RGB', (20, 20), 'blue').save(image, 'PNG')
        image.seek(0)
        response = self.client.post(f'/api/items/{item}/photos', data={'file': (image, 'image.png')})
        self.assertEqual(response.status_code, 201)
        photo = self.client.get(f'/api/items/{item}').json['photos'][0]
        name = self.backup()
        self.assertEqual(self.client.delete(f"/api/photos/{photo['id']}").status_code, 200)
        self.restore(name)
        self.assertEqual(self.client.delete(f'/api/items/{item}').status_code, 200)
        self.restore(name)
        restored = self.client.get(f'/api/items/{item}').json['photos'][0]
        self.assertEqual(restored['filename'], photo['filename'])
        for filename in (photo['filename'], photo['thumb_filename']):
            with self.client.get('/files/' + filename) as response:
                self.assertEqual(response.status_code, 200)

    def test_required_custom_field_rolls_back_item_creation(self):
        response = self.client.post('/api/types', json={'name': 'Required test', 'fields': [{'label': 'Code', 'required': True}]})
        type_id = response.json['id']
        response = self.client.post('/api/items', json={'name': 'Incomplete', 'item_type_id': type_id})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(inspect_database_file(self.path)['items'], 0)


if __name__ == '__main__':
    unittest.main()
