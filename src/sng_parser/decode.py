import os
import struct

from typing import List, Optional

from configparser import ConfigParser

from .common import mask, SngFileMetadata, ParsedSngData


def read_filedata(buffer: bytes, offset: int) -> SngFileMetadata:
    filename_len: int = struct.unpack_from('<B', buffer, offset)[0]
    offset += 1
    filename: str = struct.unpack_from(f'<{filename_len}s', buffer, offset)[0].decode()
    offset += filename_len

    contents_len: int
    contents_index: int
    contents_len, contents_index = struct.unpack_from('<QQ', buffer, offset)

    offset += 16
    metadata = SngFileMetadata(filename, contents_len, contents_index)

    return metadata, offset


def parse_sng_file(sng_buffer: bytes) -> ParsedSngData:
    file_identifier: bytes
    version: int
    xor_mask: bytes 
    file_identifier, version, xor_mask = struct.unpack('<6sI16s', sng_buffer[:26])

    assert file_identifier in bytes([0x53, 0x4E, 0x47, 0x50, 0x4b, 0x47]), "Not a sng file."

    if file_identifier.decode() != "SNGPKG":
        raise ValueError("Invalid file identifier")

    metadata_len: int
    metadata_count: int
    metadata_len, metadata_count = struct.unpack_from('<QQ', sng_buffer, 26)

    offset = 26 + 16

    metadata = {}
    
    for _ in range(metadata_count):
        key_len: int = struct.unpack_from('<I', sng_buffer, offset)[0]
        offset += 4
        key: str = struct.unpack_from(f'<{key_len}s', sng_buffer, offset)[0].decode()
        offset += key_len
        value_len: int = struct.unpack_from('<I', sng_buffer, offset)[0]
        offset += 4
        value: str = struct.unpack_from(f'<{value_len}s', sng_buffer, offset)[0].decode()
        offset += value_len
        metadata[key] = value

    file_meta_len, file_count = struct.unpack_from('<QQ', sng_buffer, offset)
    offset += 16
    file_meta_array: List[SngFileMetadata] = []
    for _ in range(file_count):
        file_meta, new_offset = read_filedata(sng_buffer, offset)
        file_meta_array.append(file_meta)
        offset = new_offset

    file_data_len: int = struct.unpack_from('<Q', sng_buffer, offset)[0]
    offset += 8
    file_data_array: List[bytearray] = []
    for file_meta in file_meta_array:
        file_data = sng_buffer[offset:offset+file_meta.content_len]
        file_data = mask(file_data, xor_mask)
        file_data_array.append(file_data)
        offset += file_meta.content_len

    return {
        'file_identifier': file_identifier.decode(),
        'version': version,
        'xor_mask': xor_mask,
        'metadata': metadata,
        'file_meta_array': file_meta_array,
        'file_data_array': file_data_array
    }


def write_parsed_sng(parsed_data: ParsedSngData, outdir: os.PathLike) -> None:
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    cfg = ConfigParser()
    cfg.add_section('Song')
    cfg['Song'] = parsed_data['metadata']
    with open(os.path.join(outdir, 'song.ini'), 'w') as f:
        cfg.write(f)

    for index, file_meta in enumerate(parsed_data['file_meta_array']):
        file_data = parsed_data['file_data_array'][index]
        file_path = os.path.join(outdir, file_meta.filename)
        with open(file_path, 'wb') as file:
            file.write(file_data)


def convert_sng_file(sng_file: os.PathLike | bytes, outdir: Optional[os.PathLike]=None):
    if isinstance(sng_file, os.PathLike):
        with open(sng_file, 'rb') as f:
            sng_file = f.read()
    parsed_sng = parse_sng_file(sng_file)

    if outdir is None:
        artist = parsed_sng['metadata'].get("artist", "Unknown Artist")
        song = parsed_sng['metadata'].get("song", "Unknown Song")
        charter = parsed_sng['metadata'].get("charter", "Unknown Charter")
        outdir = f"{artist} - {song} ({charter})"
    write_parsed_sng(parsed_sng, outdir)