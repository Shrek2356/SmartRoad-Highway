import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from payload_manifest import assert_release_file, inno_escape, installer_flags, prepare, safe_relative


class PayloadTests(unittest.TestCase):
    def test_windows_path_validation(self):
        for path in ("../file", "a/../b", "/abs", "E:/x", "a//b", "a/CON.txt", "x. /y", "a\x00b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_relative(path)
        self.assertEqual(safe_relative("测试目录\\a.txt"), "测试目录/a.txt")

    def test_private_payloads_are_rejected(self):
        for path in ("runtime/desktop/log.json", "detectmodel/Site_Safety_OpenRisk/app_data/x", "model.gguf", ".env", "node_modules/a",
                     "detectmodel/Site_Safety_OpenRisk/road_app_data/db.sqlite3",
                     "detectmodel/Site_Safety_OpenRisk/road_knowledge_base/private.md",
                     "detectmodel/Site_Safety_OpenRisk/knowledge_base/old.md",
                     "desktop/build-road/local/cache", "desktop/build/frozen/code", "saved.sqlite3"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                assert_release_file(path)

    def test_user_seeds_survive_reinstall_and_uninstall(self):
        for path in ("desktop-settings.json", "detectmodel/Site_Safety_OpenRisk/configs/runtime_initial_settings.json",
                     "detectmodel/Site_Safety_OpenRisk/knowledge_base/示例.md"):
            self.assertEqual(installer_flags(path), "onlyifdoesntexist uninsneveruninstall")
        self.assertEqual(installer_flags("pc-admin/dist/index.html"), "ignoreversion")

    def test_road_templates_update_but_user_settings_survive(self):
        prefix = "detectmodel/Site_Safety_OpenRisk/configs/"
        for name in ("road_demo.yaml", "road_offline.yaml", "road_standard.yaml", "road_risk_operators.yaml"):
            self.assertEqual(installer_flags(prefix + name), "ignoreversion")
        for name in ("road_runtime_initial_settings.json", "road_threshold_overrides.json", "road_notify_targets.json"):
            self.assertEqual(installer_flags(prefix + name), "onlyifdoesntexist uninsneveruninstall")
        assert_release_file("detectmodel/Site_Safety_OpenRisk/examples/road_knowledge/sources.json")

    def test_inno_constant_escaping(self):
        self.assertEqual(inno_escape('x/{name}/y'), 'x/{{name}/y')

    def make_archive(self, folder, *, extra=False, corrupt=False):
        path = folder / 'release.zip'
        data = b'{"version":"1.4.1"}'
        manifest = [{"path": "pc-admin/package.json", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}]
        with ZipFile(path, "w") as archive:
            archive.writestr('release/release-manifest.json', json.dumps(manifest))
            archive.writestr('release/pc-admin/package.json', b"wrong" if corrupt else data)
            if extra:
                archive.writestr('release/private.txt', 'private')
        return path

    def test_manifest_whitelist_and_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            info = prepare(self.make_archive(folder), folder / 'stage')
            self.assertEqual(info['verified_manifest_files'], 1)
            self.assertEqual(info['version'], '1.4.1')
            self.assertIn('ignoreversion', Path(info['include']).read_text(encoding='utf-8-sig'))

    def test_undeclared_file_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'exactly match'):
                prepare(self.make_archive(folder, extra=True), folder / 'stage')

    def test_corrupted_file_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'integrity'):
                prepare(self.make_archive(folder, corrupt=True), folder / 'stage')

    def test_existing_stage_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'already exists'):
                prepare(Path('unused.zip'), Path(temporary))


if __name__ == '__main__':
    unittest.main()
