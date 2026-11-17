"""Copy and verify Archivist Trials before production resources are removed."""
import hashlib
import json
from pathlib import Path
import shutil


def digest(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()


def main():
    source = Path(__file__).resolve().parents[1]
    target = (source.parent / 'SADM Autorouter Sandbox').resolve()
    if source.name != 'SADM Autorouter' or target.name != 'SADM Autorouter Sandbox' or target.parent != source.parent:
        raise SystemExit('Unexpected project paths; refusing to transfer.')
    if not (target / 'frontend/pyqt_dialogs.py').is_file():
        raise SystemExit('The sandbox project is missing.')
    paths = [Path('frontend/rpg'), Path('assets/rpg'), Path('assets/icons/archivebound.ico'),
             Path('tests/test_archivebound.py'), Path('tools/preview_rpg_level.py')]
    paths.extend(path.relative_to(source) for path in (source / 'docs').glob('OUT_OF_SPEC_*.md'))
    files = []
    for relative in paths:
        entry = source / relative
        files.extend(path for path in entry.rglob('*') if path.is_file() and '__pycache__' not in path.parts
                     and path.suffix != '.pyc') if entry.is_dir() else files.append(entry)
    backup = target / 'output/archivist-transfer-backup'
    manifest = []
    copied = 0
    for path in files:
        relative = path.relative_to(source)
        destination = target / relative
        checksum = digest(path)
        if not destination.is_file() or digest(destination) != checksum:
            if destination.is_file():
                previous = backup / relative
                previous.parent.mkdir(parents=True, exist_ok=True)
                if not previous.exists():
                    shutil.copy2(destination, previous)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            copied += 1
        if digest(destination) != checksum:
            raise RuntimeError(f'Transfer verification failed: {relative}')
        manifest.append({'path': relative.as_posix(), 'bytes': path.stat().st_size, 'sha256': checksum})

    # Sandbox games must not grant currency into production's rewards file.
    rewards = target / 'utils/rewards.py'
    text = rewards.read_text(encoding='utf-8')
    old = 'PUBLIC_ACH_DIR = Path(os.environ.get("PUBLIC", r"C:\\Users\\Public")) / "ach"'
    new = old + ' / "Sandbox"'
    if old + '\n' in text:
        previous = backup / 'utils/rewards.py'
        previous.parent.mkdir(parents=True, exist_ok=True)
        if not previous.exists():
            shutil.copy2(rewards, previous)
        text = text.replace(old + '\n', new + '\n', 1)
        anchor = '    seen = set()\n    for base_dir in base_dirs:'
        text = text.replace(anchor, '    # Seed an independent sandbox profile once; never overwrite production.\n'
                            '    yield PUBLIC_ACH_DIR.parent / "user_rewards.json"\n\n' + anchor, 1)
        rewards.write_text(text, encoding='utf-8')

    persistence = target / 'frontend/rpg/persistence.py'
    text = persistence.read_text(encoding='utf-8')
    anchor = '    target = path or SAVE_PATH\n    try:\n'
    replacement = ('    target = path or SAVE_PATH\n    try:\n'
                   '        if path is None and not target.exists():\n'
                   '            legacy = PUBLIC_ACH_DIR.parent / "archivebound_save.json"\n'
                   '            if legacy.is_file():\n'
                   '                with legacy.open("r", encoding="utf-8") as handle:\n'
                   '                    state = ArchiveboundState.from_dict(json.load(handle))\n'
                   '                save_game(state, target)\n'
                   '                return state\n')
    if anchor not in text:
        raise RuntimeError('The game persistence code changed; review the migration hook.')
    persistence.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
    readme = target / 'frontend/rpg/README.md'
    text = readme.read_text(encoding='utf-8').replace(r'C:\Users\Public\ach\archivebound_save.json',
                                                   r'C:\Users\Public\ach\Sandbox\archivebound_save.json')
    readme.write_text(text, encoding='utf-8')
    result = {'source': str(source), 'sandbox': str(target), 'copied_files': copied,
              'verified_files': manifest, 'total_bytes': sum(item['bytes'] for item in manifest),
              'sandbox_game_storage': r'C:\Users\Public\ach\Sandbox',
              'adapted_files': ['utils/rewards.py', 'frontend/rpg/persistence.py', 'frontend/rpg/README.md']}
    output = source / 'output/archivist-transfer-manifest.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'Verified {len(manifest)} transferred files ({result["total_bytes"]:,} bytes); updated {copied} sandbox files.')
    print('Sandbox game saves and rewards now use their own storage; production originals are preserved.')


if __name__ == '__main__':
    main()
