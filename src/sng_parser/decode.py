import os
import struct
from io import BytesIO


from typing import List, Optional, Tuple

from configparser import ConfigParser

from .common import mask, SngFileMetadata, ParsedSngData, SngMetadataInfo, calc_and_unpack


def read_filedata(buffer: BytesIO) -> SngFileMetadata:
    filename_len: int = calc_and_unpack("<B", buffer)[0]
    filename: str = calc_and_unpack(f"<{filename_len}s", buffer)[0].decode()
    contents_len: int
    contents_index: int
    contents_len, contents_index = calc_and_unpack("<QQ", buffer)
    metadata = SngFileMetadata(filename, contents_len, contents_index)

    return metadata


def decode_file_metadata(buffer: BytesIO):
    file_meta_len, file_count = calc_and_unpack("<QQ", buffer)
    file_meta_array: List[SngFileMetadata] = []
    for _ in range(file_count):
        file_meta= read_filedata(buffer)
        file_meta_array.append(file_meta)


def decode_metadata(sng_buffer: BytesIO, metadata_len: int, metadata_count: int) -> SngMetadataInfo:
    metadata = {}
    for _ in range(metadata_count):
        key_len: int = calc_and_unpack("<I", sng_buffer)
        key: str = calc_and_unpack(f"<{key_len}s", sng_buffer)[0].decode()
        value_len: int = calc_and_unpack("<I", sng_buffer)[0]
        value: str = calc_and_unpack(f"<{value_len}s", sng_buffer)[0].decode()
        metadata[key] = value
    return metadata


def decode_sng(sng_file: os.PathLike | BytesIO, outdir: Optional[os.PathLike] = None) -> None:
    if isinstance(sng_file, os.PathLike):
        with open(sng_file, "rb") as f:
            _decode_sng(f, outdir)
    else:
        _decode_sng(sng_file, outdir)


def _decode_sng(sng_file: BytesIO, outdir: Optional[os.PathLike]=None) -> None:
    file_identifier, version, xor_mask = struct.unpack_from("<6sI16s", sng_file, 26)
    assert file_identifier in bytes(
        [0x53, 0x4E, 0x47, 0x50, 0x4B, 0x47]
    ), "Not a sng file."

    if file_identifier.decode() != "SNGPKG":
        raise ValueError("Invalid file identifier")
    
    metadata_len: int
    metadata_count: int
    metadata_len, metadata_count = calc_and_unpack("<QQ", sng_file, 26)
    
    metadata = decode_metadata(sng_file, metadata_len, metadata_count)

    if outdir is None:
        artist = metadata.get("artist", "Unknown Artist")
        song = metadata.get("song", "Unknown Song")
        charter = metadata.get("charter", "Unknown Charter")
        outdir = f"{artist} - {song} ({charter})"
    
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    write_metadata(metadata, outdir)
    
    file_meta_len, file_count = calc_and_unpack("<QQ", sng_file, offset)

    file_meta_array: List[SngFileMetadata] = []
    for _ in range(file_count):
        file_meta, new_offset = read_filedata(sng_file, offset)
        file_meta_array.append(file_meta)
        offset = new_offset
    
    file_data_len: int = calc_and_unpack("<Q", sng_file)[0]

    for file_meta in file_meta_array:
        amt_read = 0
        with open(os.path.join(outdir, file_meta.filename), 'wb') as f:
            while file_meta.content_len < amt_read:
                chunk_size = 1024 if file_meta.content_len - amt_read > 1023 else file_meta.content_len - amt_read
                amt_read += chunk_size
                buf = f.read(chunk_size)
                f.write(mask(buf, xor_mask))


def write_metadata(metadata: SngMetadataInfo, outdir: os.PathLike) -> None:
    cfg = ConfigParser()
    cfg.add_section("Song")
    cfg["Song"] = metadata
    with open(os.path.join(outdir, "song.ini"), "w") as f:
        cfg.write(f)
