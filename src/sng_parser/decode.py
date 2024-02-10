import os
import struct
from io import BytesIO, BufferedReader
from pathlib import Path


from typing import List, Optional, NoReturn

from configparser import ConfigParser

from .common import mask, SngFileMetadata, SngMetadataInfo, calc_and_unpack, SngHeader


def read_sng_header(buffer: BufferedReader) -> SngHeader:
    xor_mask: bytes
    version: int
    file_identifier: bytes
    file_identifier, version, xor_mask = calc_and_unpack("<6sI16s", buffer)
    return SngHeader(file_identifier, version, xor_mask)


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

def write_file_contents(file_meta_array: List[SngFileMetadata], buffer: BufferedReader, *, xor_mask: bytes, outdir: os.PathLike):
    file_data_len: int = calc_and_unpack("<Q", buffer)[0]
    file_meta_content_size: int = sum(map(lambda x: x.content_len, file_meta_array))
    if file_meta_content_size != file_data_len:
        raise RuntimeError("Length mismatch, %d != %d" % (file_meta_content_size, file_data_len))
    for file_meta in file_meta_array:
        _write_file_contents(file_meta, buffer, xor_mask=xor_mask, outdir=outdir)


def _write_file_contents(
    file_metadata: SngFileMetadata,
    buffer: BufferedReader,
    *,
    xor_mask: bytes,
    outdir: os.PathLike
    ) -> None:
    amt_read = 0
    file_path = os.path.join(outdir, file_metadata.filename)
    with open(file_path, 'wb') as out:
        while file_metadata.content_len > amt_read:
            chunk_size = 1024 if file_metadata.content_len - amt_read > 1023 else file_metadata.content_len - amt_read
            amt_read += chunk_size
            buf = buffer.read(chunk_size)
            out.write(mask(buf, xor_mask))


def _as_path_obj(path: str, *, validate: bool=True) -> Path | NoReturn:
    path = Path(path)
    if validate:
        _validate_path(path)
    return path


def _validate_path(path: os.PathLike) -> None | NoReturn:
    if not os.path.exists(path):
        raise RuntimeError("No file located at %s" % path)


def decode_sng(
        sng_file: os.PathLike | str | BufferedReader,
        *,
        outdir: Optional[os.PathLike | str] = None,
        sng_dir: Optional[os.PathLike | str] = None
        ) -> None | NoReturn:
    path_passed = not isinstance(sng_file, BufferedReader)
    if outdir is None:
        outdir = os.curdir
    if isinstance(outdir, str):
        outdir = _as_path_obj(outdir)
    if isinstance(sng_file, str):
        sng_file = _as_path_obj(sng_file)
    
    if isinstance(sng_file, os.PathLike):
        _validate_path(sng_file)
        sng_file = open(sng_file, 'rb')

    header= read_sng_header(sng_file)

    if header.file_identifier.decode() != "SNGPKG":
        raise ValueError("Invalid file identifier")
    
    metadata = decode_metadata(sng_file)
    if sng_dir is None:
        sng_dir = create_dirname(metadata)

    outdir = os.path.join(outdir, sng_dir)
    if os.path.exists(outdir):
        raise RuntimeError("Song already exists at %s" % outdir)
    os.makedirs(outdir)

    write_metadata(metadata, outdir)

    file_meta_array: List[SngFileMetadata] = decode_file_metadata(sng_file)
    write_file_contents(file_meta_array, sng_file, xor_mask=header.xor_mask, outdir=outdir)
    # file_data_len: int = calc_and_unpack("<Q", sng_file)[0]

    # for file_meta in file_meta_array:
        # _write_file_contents(file_meta, sng_file, xor_mask=header.xor_mask, outdir=outdir)

    if path_passed:
        sng_file.close()


def create_dirname(metadata: SngFileMetadata) -> str:
    artist = metadata.get("artist", "Unknown Artist")
    song = metadata.get("name", "Unknown Song")
    charter = metadata.get("charter", "Unknown Charter")
    return f"{artist} - {song} ({charter})"


def write_metadata(metadata: SngMetadataInfo, outdir: os.PathLike) -> None:
    cfg = ConfigParser()
    cfg.add_section("Song")
    cfg["Song"] = metadata
    with open(os.path.join(outdir, "song.ini"), "w") as f:
        cfg.write(f)
