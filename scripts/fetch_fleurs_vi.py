"""Fetch a fixed-prefix human speech sample and references, before ASR scoring.

Google FLEURS, CC BY 4.0: https://huggingface.co/datasets/google/fleurs
Writes audio/transcripts to an explicitly selected private directory. Does not
extract arbitrary archive paths or generate/alter reference transcripts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

REVISION = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"
SOURCE = f"https://huggingface.co/datasets/google/fleurs/resolve/{REVISION}/"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, choices=range(10, 101), default=12)
    args = parser.parse_args()
    target = args.output_dir.resolve()
    target.mkdir(parents=True, exist_ok=True)
    if (target / "audio").is_symlink():
        raise ValueError("Audio directory must not be a symlink")
    (target / "audio").mkdir(exist_ok=True)
    with urlopen(SOURCE + "data/vi_vn/test.tsv", timeout=60) as response:
        tsv = response.read()
    rows = [line.split("\t") for line in tsv.decode("utf-8").splitlines()][:args.count]
    for row in rows:
        if len(row) < 7 or Path(row[1]).name != row[1] or not row[1].endswith(".wav"):
            raise ValueError("Unexpected dataset row or audio filename")
    cached = {}
    receipt = target / "manifest.json"
    if receipt.exists():
        previous = json.loads(receipt.read_text(encoding="utf-8"))
        if previous.get("revision") == REVISION and previous.get("tsv_sha256") == hashlib.sha256(tsv).hexdigest():
            cached = {Path(clip["audio_file"]).name: clip["audio_sha256"] for clip in previous.get("clips", [])}
    wanted = set()
    for row in rows:
        path = target / "audio" / row[1]
        if path.is_symlink():
            raise ValueError("Audio sample must not be a symlink")
        if not path.is_file() or cached.get(row[1]) != hashlib.sha256(path.read_bytes()).hexdigest():
            wanted.add(row[1])
    if wanted:
        with urlopen(SOURCE + "data/vi_vn/audio/test.tar.gz", timeout=60) as response:
            with tarfile.open(fileobj=response, mode="r|gz") as archive:
                for member in archive:
                    name = Path(member.name).name
                    if member.isfile() and name in wanted:
                        if member.size > 16000000:
                            raise ValueError("Oversized sample")
                        (target / "audio" / name).write_bytes(archive.extractfile(member).read())
                        wanted.remove(name)
                        print(f"Fetched {name}", flush=True)
                    if not wanted:
                        break
    if wanted:
        raise RuntimeError("Selected samples not found in archive")
    (target / "test.tsv").write_bytes(tsv)
    manifest = {"dataset": "google/fleurs", "revision": REVISION, "language": "vi_vn", "split": "test",
        "license": "CC BY 4.0", "source": SOURCE,
        "selection": f"first {args.count} TSV rows, before recognition; not a representative meeting sample",
        "tsv_sha256": hashlib.sha256(tsv).hexdigest(),
        "clips": [{"id": row[0], "audio_file": "audio/" + row[1], "reference": row[3], "gender": row[6],
            "audio_sha256": hashlib.sha256((target / "audio" / row[1]).read_bytes()).hexdigest()} for row in rows]}
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} samples; references are private, not copied into a public report.")


if __name__ == "__main__":
    main()
