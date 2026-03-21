"""
Extract character data from SillyTavern-compatible PNG character cards.

Usage:
    python scripts/card_extract.py <input_png> <output_dir>

Produces:
    <output_dir>/legacy.json   — raw extracted JSON from the card
    <output_dir>/avatar.png    — PNG with tEXt metadata stripped (image only)
"""

import struct
import base64
import json
import sys
import os
import zlib


def read_png_chunks(path):
    """Read all chunks from a PNG file."""
    with open(path, "rb") as f:
        signature = f.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Not a valid PNG file: {path}")

        chunks = []
        while True:
            raw_length = f.read(4)
            if len(raw_length) < 4:
                break
            length = struct.unpack(">I", raw_length)[0]
            chunk_type = f.read(4)
            data = f.read(length)
            crc = f.read(4)
            chunks.append((chunk_type, data, crc, raw_length))
        return signature, chunks


def extract_chara_data(chunks):
    """Extract and decode the 'chara' tEXt chunk."""
    for chunk_type, data, crc, raw_length in chunks:
        if chunk_type == b"tEXt":
            null_idx = data.index(b"\x00")
            key = data[:null_idx].decode("latin-1")
            if key == "chara":
                value = data[null_idx + 1 :].decode("latin-1")
                decoded = base64.b64decode(value)
                parsed = json.loads(decoded)
                return parsed
    raise ValueError("No 'chara' tEXt chunk found in PNG")


def write_clean_png(signature, chunks, output_path):
    """Write PNG without tEXt chunks (strip metadata, keep image data)."""
    with open(output_path, "wb") as f:
        f.write(signature)
        for chunk_type, data, crc, raw_length in chunks:
            if chunk_type == b"tEXt":
                continue
            f.write(raw_length)
            f.write(chunk_type)
            f.write(data)
            f.write(crc)


def normalize_card_data(raw):
    """Normalize v1/v2 card formats to a consistent structure."""
    # v2 has spec/spec_version at top level, data nested
    if "spec" in raw and "data" in raw:
        return raw["data"], raw.get("spec_version", "unknown")
    # v1 or flat format — data is at top level or nested
    if "data" in raw:
        return raw["data"], "1.0"
    # Completely flat
    return raw, "unknown"


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input_png> <output_dir>")
        sys.exit(1)

    input_png = sys.argv[1]
    output_dir = sys.argv[2]

    if not os.path.exists(input_png):
        print(f"Error: Input file not found: {input_png}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    # Read and parse PNG
    signature, chunks = read_png_chunks(input_png)
    raw_data = extract_chara_data(chunks)

    # Normalize
    card_data, spec_version = normalize_card_data(raw_data)

    # Save legacy (full original extracted data)
    legacy = {
        "source_file": os.path.basename(input_png),
        "spec_version": spec_version,
        "raw": card_data,
    }
    legacy_path = os.path.join(output_dir, "legacy.json")
    with open(legacy_path, "w", encoding="utf-8") as f:
        json.dump(legacy, f, indent=2, ensure_ascii=False)
    print(f"Saved legacy data: {legacy_path}")

    # Save clean avatar PNG
    avatar_path = os.path.join(output_dir, "avatar.png")
    write_clean_png(signature, chunks, avatar_path)
    print(f"Saved clean avatar: {avatar_path}")

    # Print summary for Claude Code to read
    name = card_data.get("name", "Unknown")
    desc_len = len(card_data.get("description", ""))
    has_book = "character_book" in card_data
    greeting_count = len(card_data.get("alternate_greetings", []))
    print(f"\nCharacter: {name}")
    print(f"Description length: {desc_len} chars")
    print(f"Has lorebook: {has_book}")
    print(f"Alternate greetings: {greeting_count}")
    print(f"Output directory: {output_dir}")


if __name__ == "__main__":
    main()
