import logging
import os
import shutil
import struct
from io import BufferedReader
from pathlib import Path
import tempfile


from typing import List, Optional, NoReturn, Tuple

from configparser import ConfigParser

from .common import mask, SngFileMetadata, SngMetadataInfo, calc_and_unpack, SngHeader, calc_and_read_buf
from struct import calcsize

logger = logging.getLogger(__package__)

def read_sng_header(buffer: BufferedReader) -> SngHeader:
    xor_mask: bytes
    version: int
    file_identifier: bytes
    file_identifier, version, xor_mask = calc_and_unpack("<6sI16s", buffer)
    return SngHeader(file_identifier, version, xor_mask)


def read_filedata(buffer: BufferedReader) -> Tuple[SngFileMetadata, int]:
    logger.debug("Retrieving file metadata")
    amt_read: int = 0
    
    logger.debug("Reading filename length")
    read_size, content = calc_and_read_buf("<B", buffer)
    amt_read += read_size
    filename_len: int = struct.unpack("<B", content)[0]
    logger.debug("Filename length: %d (bytes: %d)", filename_len, read_size)
    
    logger.debug("Reading filename string")
    read_size, content = calc_and_read_buf(f"<{filename_len}s", buffer)
    amt_read += read_size
    filename: str = struct.unpack(f"<{filename_len}s", content)[0].decode()
    logger.debug("Filename: %s (bytes: %d)", filename, read_size)

    contents_len: int
    contents_index: int

    logger.debug("Reading file content offset and file content size")
    read_size, content = calc_and_read_buf("<QQ", buffer)
    amt_read += read_size
    contents_len, contents_index = struct.unpack("<QQ", content)
    logger.debug("File content size: %d (offset %d)", contents_len, contents_index)

    metadata = SngFileMetadata(filename, contents_len, contents_index)

    logger.debug("Total bytes read: %d", amt_read)

    return metadata, amt_read


def decode_file_metadata(buffer: BufferedReader) -> List[SngFileMetadata]:
    logger.info("Decoding sng file content metadata")
    amt_read: int = 0
    
    logger.debug("Reading file metadata")
    file_meta_len: int = calc_and_unpack("<Q", buffer)[0]
    logger.debug("File metadata content length: %d", file_meta_len)
    
    logger.debug("Reading file count")
    bytes_read, content = calc_and_read_buf("<Q", buffer)
    amt_read += bytes_read
    file_count: int = struct.unpack("<Q", content)[0]
    logger.debug("File count: %d (bytes: %d)", file_count, bytes_read)

    file_meta_array: List[SngFileMetadata] = []
    for _ in range(file_count):
        file_meta, bytes_read = read_filedata(buffer)
        amt_read += bytes_read
        logger.info("Retrieved metadata of %s (offset: %d, content length: %d)", file_meta.filename, file_meta.content_idx, file_meta.content_len)
        file_meta_array.append(file_meta)
    if file_meta_len != amt_read:
        raise RuntimeError("File metadata read mismatch. Expected %d, read %d" % (file_meta_len, amt_read))
    return file_meta_array


def decode_metadata(sng_buffer: BufferedReader) -> SngMetadataInfo:
    logger.info("Decoding sng metadata")
    total_bytes: int = 0
    
    logger.debug("Reading metadata content length")
    metadata_len: int = calc_and_unpack("<Q", sng_buffer)[0]
    logger.debug("Metadata content length: %d", metadata_len)

    logger.debug("Reading song metadata count")
    bytes_read, content = calc_and_read_buf("<Q", sng_buffer)
    total_bytes += bytes_read
    metadata_count: int = struct.unpack("<Q", content)[0]
    logger.debug("Metadata entries: %d (bytes: %d)", metadata_count, bytes_read)

    metadata = {}

    for i in range(metadata_count):
        logger.debug("Retrieving metadata key size of entry %d", i+1)
        bytes_read, content = calc_and_read_buf("<I", sng_buffer)
        total_bytes += bytes_read
        key_len: int = struct.unpack("<I", content)[0]
        logger.debug("Metadata key size: %d (bytes: %d)", key_len, bytes_read)

        logger.debug("Retrieving metadata key %d", i+1)
        bytes_read, content = calc_and_read_buf(f"<{key_len}s", sng_buffer)
        total_bytes += bytes_read
        key: str = struct.unpack(f"<{key_len}s", content)[0].decode()
        logger.debug("Metadata key %d: '%s' (bytes: %d)",i+1, key, bytes_read)
        
        logger.debug("Retriveing metadata value size of '%s'", key)
        bytes_read, content = calc_and_read_buf(f"<I", sng_buffer)
        total_bytes += bytes_read
        value_len: int = struct.unpack("<I", content)[0]
        logger.debug("Metadata value size: %d (bytes: %d)", value_len, bytes_read)

        logger.debug("Retriveing metadata value of '%s'", key)
        bytes_read, content = calc_and_read_buf(f"<{value_len}s", sng_buffer)
        total_bytes += bytes_read
        value: str = struct.unpack(f"<{value_len}s", content)[0].decode()
        logger.debug("Metadata value for key '%s': '%s' (bytes: %d)", key, value, bytes_read)

        metadata[key] = value

    if total_bytes != metadata_len:
        raise RuntimeError("Metadata read mismatch. Expected %d, read %d" % (metadata_len, total_bytes))

    metadata_attrs_read = len(metadata)
    if metadata_attrs_read != metadata_count:
        raise RuntimeError("Metadata count mismatch. Expected %d, found %d" % (metadata_count, metadata_attrs_read))
    return metadata


def write_file_contents(file_meta_array: List[SngFileMetadata], buffer: BufferedReader, *, xor_mask: bytes, outdir: os.PathLike):
    logger.info("Writing decoded sng file to %s", outdir)

    file_data_len: int = calc_and_unpack("<Q", buffer)[0]
    file_meta_content_size: int = sum(map(lambda x: x.content_len, file_meta_array))
    print(file_data_len)
    print(file_meta_content_size)

    if file_meta_content_size != file_data_len:
        raise RuntimeError("File content size mismatch. Expected %d, got %d)" % ( file_data_len, file_meta_content_size))
    
    for file_meta in file_meta_array:
        buffer.seek(file_meta.content_idx)
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
    logger.debug("Writing file %s", file_metadata.filename)
    with open(file_path, 'wb') as out:
        while file_metadata.content_len > amt_read:
            chunk_size = 1024 if file_metadata.content_len - amt_read > 1023 else file_metadata.content_len - amt_read
            amt_read += chunk_size
            buf = buffer.read(chunk_size)
            out.write(mask(buf, xor_mask))
        if file_metadata.content_len != amt_read:
            raise RuntimeError("File write mismatch. Expected %d, wrote %d" % (file_metadata.content_len, amt_read))
    
    logger.debug('Wrote %s in %s', file_metadata.filename, outdir)


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
        outdir = _as_path_obj(outdir, validate=False)
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
    
    tmp_dir = tempfile.mkdtemp()
    write_metadata(metadata, tmp_dir)

    file_meta_array: List[SngFileMetadata] = decode_file_metadata(sng_file)
    write_file_contents(file_meta_array, sng_file, xor_mask=header.xor_mask, outdir=tmp_dir)

    if path_passed:
        sng_file.close()

    os.makedirs(outdir)
    files_to_move = list(map(lambda x: x.filename, file_meta_array))
    files_to_move.append("song.ini")
    for filename in files_to_move:
        shutil.move(os.path.join(tmp_dir, filename), outdir)

    logging.info("Wrote sng file output in %s", outdir)


def create_dirname(metadata: SngFileMetadata) -> str:
    artist = metadata.get("artist", "Unknown Artist")
    song = metadata.get("name", "Unknown Song")
    charter = metadata.get("charter", "Unknown Charter")
    return f"{artist} - {song} ({charter})"


def write_metadata(metadata: SngMetadataInfo, outdir: os.PathLike) -> None:
    print("Writing metadata to %s" % outdir)
    cfg = ConfigParser()
    cfg.add_section("Song")
    cfg["Song"] = metadata
    with open(os.path.join(outdir, "song.ini"), "w") as f:
        cfg.write(f)
    
    logger.debug('Wrote song.ini in %s', outdir)
