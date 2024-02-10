import os
import struct
from io import BytesIO, BufferedReader
from pathlib import Path


from typing import List, Optional, NoReturn

from configparser import ConfigParser

from .common import mask, SngFileMetadata, ParsedSngData, SngMetadataInfo, calc_and_unpack


def read_filedata(buffer: BufferedReader) -> SngFileMetadata:
    filename_len: int = calc_and_unpack("<B", buffer)[0]
    filename: str = calc_and_unpack(f"<{filename_len}s", buffer)[0].decode()
    contents_len: int
    contents_index: int
    contents_len, contents_index = calc_and_unpack("<QQ", buffer)
    metadata = SngFileMetadata(filename, contents_len, contents_index)

    return metadata


def decode_file_metadata(buffer: BufferedReader) -> List[SngFileMetadata]:
    file_meta_len, file_count = calc_and_unpack("<QQ", buffer)
    file_meta_array: List[SngFileMetadata] = []
    for _ in range(file_count):
        file_meta= read_filedata(buffer)
        file_meta_array.append(file_meta)
    return file_meta_array

def decode_metadata(sng_buffer: BufferedReader) -> SngMetadataInfo:
    metadata_len: int
    metadata_count: int
    metadata_len, metadata_count = calc_and_unpack("<QQ", sng_buffer)
    metadata = {}
    for _ in range(metadata_count):
        key_len: int = calc_and_unpack("<I", sng_buffer)[0]
        key: str = calc_and_unpack(f"<{key_len}s", sng_buffer)[0].decode()
        value_len: int = calc_and_unpack("<I", sng_buffer)[0]
        value: str = calc_and_unpack(f"<{value_len}s", sng_buffer)[0].decode()
        metadata[key] = value
    return metadata

def _as_path_obj(path: str) -> Path:
    path = Path(path)
    _validate_path(path)
    return path

def _validate_path(path: os.PathLike) -> None | NoReturn:
    if not os.path.exists(path):
        raise RuntimeError("No file located at %s" % path)

def decode_sng(sng_file: os.PathLike | str | BufferedReader, outdir: Optional[os.PathLike|str] = None) -> None:
    path_passed = not isinstance(sng_file, BufferedReader)
    if outdir is None:
        outdir = os.curdir
    if isinstance(outdir, str):
        outdir = Path(outdir)
    if isinstance(sng_file, str):
        sng_file = Path(sng_file)
    
    buffer_passed = isinstance(sng_file, BytesIO)
    
    if isinstance(sng_file, os.PathLike):
        if not os.path.exists(sng_file):
            raise RuntimeError("No file located at %s" % sng_file)
        sng_file = open(sng_file, 'rb')
    
    _decode_sng(sng_file, outdir)
    if path_passed:
        sng_file.close()
    


def create_dirname(metadata: SngFileMetadata) -> str:
    artist = metadata.get("artist", "Unknown Artist")
    song = metadata.get("name", "Unknown Song")
    charter = metadata.get("charter", "Unknown Charter")
    return f"{artist} - {song} ({charter})"


def _decode_sng(sng_file: BytesIO, outdir: Optional[os.PathLike]=None) -> None:
    file_identifier, version, xor_mask = calc_and_unpack("<6sI16s", sng_file)
    assert file_identifier in bytes(
        [0x53, 0x4E, 0x47, 0x50, 0x4B, 0x47]
    ), "Not a sng file."

    if file_identifier.decode() != "SNGPKG":
        raise ValueError("Invalid file identifier")
    
    metadata = decode_metadata(sng_file)
    sng_dir = create_dirname(metadata)

    if outdir is None:
        outdir = os.curdir
    outdir = os.path.join(outdir, sng_dir)
    
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    write_metadata(metadata, outdir)

    file_meta_array: List[SngFileMetadata] = decode_file_metadata(sng_file)
    file_data_len: int = calc_and_unpack("<Q", sng_file)[0]

    for file_meta in file_meta_array:
        amt_read = 0
        file_path = os.path.join(outdir, file_meta.filename)
        with open(file_path, 'wb') as out:
            print('Writing to ', file_path)
            while file_meta.content_len > amt_read:
                chunk_size = 1024 if file_meta.content_len - amt_read > 1023 else file_meta.content_len - amt_read
                amt_read += chunk_size
                buf = sng_file.read(chunk_size)
                out.write(mask(buf, xor_mask))


def write_metadata(metadata: SngMetadataInfo, outdir: os.PathLike) -> None:
    cfg = ConfigParser()
    cfg.add_section("Song")
    cfg["Song"] = metadata
    with open(os.path.join(outdir, "song.ini"), "w") as f:
        cfg.write(f)
