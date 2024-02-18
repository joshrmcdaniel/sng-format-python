import logging
import os
import re
import struct

import functools
from io import BufferedReader
from pathlib import Path
from typing import List, Optional, NoReturn, Tuple

from configparser import ConfigParser

from .common import (
    _with_endian,
    SngFileMetadata,
    SngMetadataInfo,
    calc_and_unpack,
    SngHeader,
    StructTypes,
    calc_and_read_buf,
    _valid_sng_file,
    _fail_on_invalid_sng_ver,
    _illegal_filename,
    _filter_illegal_chars,
    write_and_mask,
)

s = StructTypes
logger = logging.getLogger(__package__)


def read_sng_header(buffer: BufferedReader) -> SngHeader:
    """
    Reads the header from an SNG file buffer and returns an SngHeader object.

    The header includes the file identifier, version, and an XOR mask used for decryption.

    Args:
        buffer (BufferedReader): The input buffer from which to read the SNG header.

    Returns:
        SngHeader: An object containing the header information.
    """
    xor_mask: bytes
    version: int
    file_identifier: bytes
    file_identifier, version, xor_mask = calc_and_unpack(
        _with_endian(6, s.CHAR, s.UINT, 16, s.CHAR), buffer
    )
    _fail_on_invalid_sng_ver(version)
    return SngHeader(file_identifier, version, xor_mask)


def decode_filedata(buffer: BufferedReader) -> Tuple[SngFileMetadata, int]:
    """
    Reads the metadata for a single file from the buffer and returns the metadata along with the amount of data read.

    The file metadata includes the filename, its content length, and its offset within the SNG file.

    Args:
        buffer (BufferedReader): The input buffer from which to read the file metadata.

    Returns:
        Tuple[SngFileMetadata, int]: A tuple containing the file metadata and the total bytes read from the buffer.
    """
    logger.debug("Retrieving file metadata")
    amt_read: int = 0

    logger.debug("Reading filename length")
    fmt = _with_endian(s.UBYTE)
    read_size, content = calc_and_read_buf(fmt, buffer)
    amt_read += read_size
    filename_len: int = struct.unpack(fmt, content)[0]
    logger.debug("Filename length: %d (bytes: %d)", filename_len, read_size)

    logger.debug("Reading filename string")
    fmt = _with_endian(filename_len, s.CHAR)
    read_size, content = calc_and_read_buf(fmt, buffer)
    amt_read += read_size
    filename: str = struct.unpack(fmt, content)[0].decode()
    logger.debug("Filename: %s (bytes: %d)", filename, read_size)

    contents_len: int
    contents_index: int

    logger.debug("Reading file content offset and file content size")
    fmt = _with_endian(s.ULONGLONG, s.ULONGLONG)
    read_size, content = calc_and_read_buf(fmt, buffer)
    amt_read += read_size
    contents_len, contents_index = struct.unpack(fmt, content)
    logger.debug("File content size: %d (offset %d)", contents_len, contents_index)

    metadata = SngFileMetadata(filename, contents_len, contents_index)

    logger.debug("Total bytes read: %d", amt_read)

    return metadata, amt_read


def decode_file_metadata(buffer: BufferedReader) -> List[SngFileMetadata]:
    """
    Decodes and returns a list of SngFileMetadata objects from the given buffer.

    Reads the overall length of the file metadata section, the count of files, and then iterates to read each file's metadata.

    Args:
        buffer (BufferedReader): The input buffer from which to decode the file metadata.

    Returns:
        List[SngFileMetadata]: A list of file metadata objects.
    """
    logger.info("Decoding sng file content metadata")
    amt_read: int = 0

    logger.debug("Reading file metadata")
    file_meta_len: int = calc_and_unpack(_with_endian(s.ULONGLONG), buffer)[0]
    logger.debug("File metadata content length: %d", file_meta_len)

    logger.debug("Reading file count")
    bytes_read, content = calc_and_read_buf(_with_endian(s.ULONGLONG), buffer)
    amt_read += bytes_read
    file_count: int = struct.unpack(_with_endian(s.ULONGLONG), content)[0]
    logger.debug("File count: %d (bytes: %d)", file_count, bytes_read)

    file_meta_array: List[SngFileMetadata] = []
    for _ in range(file_count):
        file_meta, bytes_read = decode_filedata(buffer)
        amt_read += bytes_read
        logger.debug(
            "Retrieved metadata of %s (offset: %d, content length: %d)",
            file_meta.filename,
            file_meta.content_idx,
            file_meta.content_len,
        )
        file_meta_array.append(file_meta)
    if file_meta_len != amt_read:
        raise RuntimeError(
            "File metadata read mismatch. Expected %d, read %d"
            % (file_meta_len, amt_read)
        )

    logger.info("Decoded file metadata for %d files", len(file_meta_array))

    return file_meta_array


def decode_metadata(sng_buffer: BufferedReader) -> SngMetadataInfo:
    """
    Decodes the key-value pairs of metadata from the SNG buffer and returns them as a dictionary.

    Reads the total length of the metadata section and the number of metadata entries, then decodes each key-value pair.

    Args:
        sng_buffer (BufferedReader): The input buffer from which to decode the metadata.

    Returns:
        SngMetadataInfo: A dictionary containing the metadata key-value pairs.
    """
    logger.info("Decoding sng metadata")
    total_bytes: int = 0

    logger.debug("Reading metadata content length")
    metadata_len: int = calc_and_unpack(_with_endian(s.ULONGLONG), sng_buffer)[0]
    logger.debug("Metadata content length: %d", metadata_len)

    logger.debug("Reading song metadata count")
    bytes_read, content = calc_and_read_buf(_with_endian(s.ULONGLONG), sng_buffer)
    total_bytes += bytes_read
    metadata_count: int = struct.unpack(_with_endian(s.ULONGLONG), content)[0]
    logger.debug("Metadata entries: %d (bytes: %d)", metadata_count, bytes_read)

    metadata = {}

    for i in range(metadata_count):
        logger.debug("Retrieving metadata key size of entry %d", i + 1)
        fmt = _with_endian(s.UINT)
        bytes_read, content = calc_and_read_buf(fmt, sng_buffer)
        total_bytes += bytes_read
        key_len: int = struct.unpack(fmt, content)[0]
        logger.debug("Metadata key size: %d (bytes: %d)", key_len, bytes_read)

        logger.debug("Retrieving metadata key %d", i + 1)
        fmt = _with_endian(key_len, s.CHAR)
        bytes_read, content = calc_and_read_buf(fmt, sng_buffer)
        total_bytes += bytes_read
        key: str = struct.unpack(fmt, content)[0].decode()
        logger.debug("Metadata key %d: '%s' (bytes: %d)", i + 1, key, bytes_read)

        logger.debug("Retriveing metadata value size of '%s'", key)
        fmt = _with_endian(s.UINT)
        bytes_read, content = calc_and_read_buf(fmt, sng_buffer)
        total_bytes += bytes_read
        value_len: int = struct.unpack(fmt, content)[0]
        logger.debug("Metadata value size: %d (bytes: %d)", value_len, bytes_read)

        logger.debug("Retriveing metadata value of '%s'", key)
        fmt = _with_endian(value_len, s.CHAR)
        bytes_read, content = calc_and_read_buf(fmt, sng_buffer)
        total_bytes += bytes_read
        value: str = struct.unpack(fmt, content)[0].decode()
        logger.debug(
            "Metadata value for key '%s': '%s' (bytes: %d)", key, value, bytes_read
        )

        metadata[key] = value

    if total_bytes != metadata_len:
        raise RuntimeError(
            "Metadata read mismatch. Expected %d, read %d" % (metadata_len, total_bytes)
        )

    metadata_attrs_read = len(metadata)
    if metadata_attrs_read != metadata_count:
        raise RuntimeError(
            "Metadata count mismatch. Expected %d, found %d"
            % (metadata_count, metadata_attrs_read)
        )
    return metadata


def write_file_contents(
    file_meta_array: List[SngFileMetadata],
    buffer: BufferedReader,
    *,
    allow_nonsng_files: bool,
    xor_mask: bytes,
    outdir: os.PathLike,
):
    """
    Writes the actual file contents for each file metadata in the list to the specified output directory.

    Applies the XOR mask if provided to decrypt the data before writing.

    Args:
        file_meta_array (List[SngFileMetadata]): List of file metadata objects.
        buffer (BufferedReader): The input buffer from which to read the file contents.
        allow_nonsng_files (bool): Allow decoding of files not allowed by the sng standard.
        xor_mask (bytes): The XOR mask to apply for decryption.
        outdir (os.PathLike): The output directory where files will be written.

    Returns:
        None
    """
    logger.info("Writing decoded sng file to %s", outdir)

    file_data_len: int = calc_and_unpack(_with_endian(s.ULONGLONG), buffer)[0]
    logger.debug("Content size of the files: %d", file_data_len)
    logger.debug(
        "Verifying file section content size matches file metadata content size"
    )
    file_meta_content_size: int = sum(map(lambda x: x.content_len, file_meta_array))
    logger.debug("File metadata content size total: %d", file_meta_content_size)

    if file_meta_content_size != file_data_len:
        raise RuntimeError(
            "File content size mismatch. Expected %d, got %d)"
            % (file_data_len, file_meta_content_size)
        )

    for file_meta in file_meta_array:
        if _illegal_filename(file_meta.filename):
            logger.warn("Illegal filename: %s. Skipping", file_meta.filename)
            continue
        if not _valid_sng_file(file_meta.filename):
            logger.warning(
                "Found encoded file not set by the sng standard: %s", file_meta.filename
            )
            if not allow_nonsng_files:
                logger.warning(
                    "Allowing non-sng files is set to False, skipping file %s.",
                    file_meta.filename,
                )
                continue
            logger.warning(
                "Allowing non-sng files is set to True, decoding file %s.",
                file_meta.filename,
            )

        buffer.seek(file_meta.content_idx)
        _write_file_contents(file_meta, buffer, xor_mask=xor_mask, outdir=outdir)


def _write_file_contents(
    file_metadata: SngFileMetadata,
    buffer: BufferedReader,
    *,
    xor_mask: bytes,
    outdir: os.PathLike,
) -> None:
    """
    Internal function.
    Writes the contents of a single file based on the provided metadata and XOR mask
    to the specified output directory.

    Args:
        file_metadata (SngFileMetadata): The metadata for the file to write.
        buffer (BufferedReader): The input buffer from which to read the file contents.
        xor_mask (bytes): The XOR mask to apply for decryption.
        outdir (os.PathLike): The output directory where the file will be written.

    Returns:
        None
    """
    file_path = os.path.join(outdir, file_metadata.filename)
    logger.debug("Writing file %s", file_metadata.filename)
    bytes_written = write_and_mask(
        read_from=buffer,
        write_to=file_path,
        xor_mask=xor_mask,
        filesize=file_metadata.content_len,
    )
    if file_metadata.content_len != bytes_written:
        raise RuntimeError(
            "File write mismatch. Expected %d, wrote %d"
            % (file_metadata.content_len, bytes_written)
        )

    logger.debug("Wrote %s in %s", file_metadata.filename, outdir)


def _as_path_obj(path: str, *, validate: bool = True) -> Path | NoReturn:
    """
    Converts a given path string to a Path object and optionally validates its existence.

    Args:
        path (str): The file or directory path as a string.
        validate (bool, optional): If True, raises an error if the path does not exist. Defaults to True.

    Returns:
        Path | NoReturn: The Path object corresponding to the given path string.
    """
    path: Path = Path(path)
    if _illegal_filename(path.name):
        raise OSError("Illegal filename specified: %s" % path.name)
    if validate:
        _validate_path(path)
    return path


def _validate_path(path: os.PathLike) -> None | NoReturn:
    """
    Validates the existence of the given path.

    Args:
        path (os.PathLike): The path to validate.

    Returns:
        None | NoReturn: None if the path exists, raises FileNotFoundError otherwise.
    """
    if not os.path.exists(path):
        raise FileNotFoundError("No file located at %s" % path)


def decode_sng(
    sng_file: os.PathLike | str | BufferedReader,
    *,
    outdir: Optional[os.PathLike | str] = None,
    allow_nonsng_files: bool = False,
    sng_dir: Optional[os.PathLike | str] = None,
    overwrite: bool = False,
) -> None | NoReturn:
    """
    Decodes an SNG file and writes its contents, including metadata and file data, to the specified output directory.

    Args:
        sng_file (os.PathLike | str | BufferedReader): The SNG file or buffer to decode.
        outdir (os.PathLike | str, optional): The base output directory for decoded content. Defaults to the current directory.
        allow_nonsng_files (bool, optional): Allow decoding of files not allowed by the sng standard. Defaults to False.
        sng_dir (os.PathLike | str, optional): The specific directory within outdir to write the decoded content. Generated from metadata if not specified.
        overwrite (bool, optional): If True, existing files or directories will be overwritten. Defaults to False.

    Returns:
        None | NoReturn: None on success, raises an exception on failure.
    """
    path_passed = not isinstance(sng_file, BufferedReader)
    if outdir is None:
        outdir = os.curdir
    if isinstance(outdir, str):
        outdir = _as_path_obj(outdir, validate=False)
    if isinstance(sng_file, str):
        sng_file = _as_path_obj(sng_file)

    if isinstance(sng_file, os.PathLike):
        _validate_path(sng_file)
        sng_file = open(sng_file, "rb")

    header = read_sng_header(sng_file)

    if header.file_identifier.decode() != "SNGPKG":
        raise TypeError("Invalid file identifier")

    metadata = decode_metadata(sng_file)
    if sng_dir is None:
        sng_dir = create_dirname(metadata)
    outdir = os.path.join(outdir, sng_dir)
    try:
        os.makedirs(outdir, exist_ok=overwrite)
    except FileExistsError as fe:
        fe.message = "Song already exists at %s" % outdir
        raise fe

    write_metadata(metadata, outdir)

    file_meta_array: List[SngFileMetadata] = decode_file_metadata(sng_file)
    write_file_contents(
        file_meta_array,
        sng_file,
        xor_mask=header.xor_mask,
        outdir=outdir,
        allow_nonsng_files=allow_nonsng_files,
    )

    if path_passed:
        sng_file.close()

    logger.info("Wrote sng file output in %s", outdir)


def create_dirname(metadata: SngFileMetadata) -> str:
    """
    Creates a directory name from the given file metadata, using artist, song name, and charter info.

    Args:
        metadata (SngFileMetadata): The metadata from which to construct the directory name.

    Returns:
        str: The constructed directory name.
    """
    artist = metadata.get("artist", "Unknown Artist")
    song = metadata.get("name", "Unknown Song")
    charter = metadata.get("charter", "Unknown Charter")
    charter = re.sub(r"<.+?>([\s\w]+)</?.+?>", r"\1", charter)
    return _filter_illegal_chars(f"{artist} - {song} ({charter})")


def write_metadata(metadata: SngMetadataInfo, outdir: os.PathLike) -> None:
    """
    Writes the given metadata as an INI file ('song.ini') in the specified output directory.

    Args:
        metadata (SngMetadataInfo): The metadata to write to the file.
        outdir (os.PathLike): The directory in which to create the 'song.ini' file.

    Returns:
        None
    """
    logger.info("Writing metadata to %s" % outdir)
    cfg = ConfigParser()
    cfg.add_section("Song")
    cfg["Song"] = metadata
    with open(os.path.join(outdir, "song.ini"), "w") as f:
        cfg.write(f)

    logger.debug("Wrote song.ini in %s", outdir)
