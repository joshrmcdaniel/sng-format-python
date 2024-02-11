import logging
import os
import struct

from configparser import ConfigParser
from io import BufferedWriter
from typing import List, Optional, Tuple


from .common import SNG_RESERVED_FILES, mask, _with_endian, _valid_sng_file, SngFileMetadata, SngMetadataInfo, StructTypes


s = StructTypes
logger = logging.getLogger(__package__)


def write_header(file: BufferedWriter, version: int, xor_mask: bytes) -> None:
    """
    Writes the header information for an SNG file to the given file buffer.

    The header includes a fixed signature ('SNGPKG'), the version of the file
    format as an unsigned integer, and a byte sequence used as an XOR mask
    for encryption.

    Args:
        file (BufferedWriter): The file buffer to write the header to.
        version (int): The version of the SNG file format.
        xor_mask (bytes): The byte sequence used as an XOR mask for file encryption.

    Returns:
        None
    """
    logger.info("Writing sng header")
    file.write(b"SNGPKG")
    file.write(struct.pack(_with_endian(s.UINT), version))
    file.write(xor_mask)
    logger.info("Wrote header")


def write_file_meta(
    file: BufferedWriter, file_meta_array: List[SngFileMetadata]
) -> None:
    """
    Writes metadata for multiple files included in the SNG package.

    Each file's metadata includes its name, content length, and offset within the SNG file.
    The total size of the metadata section and the number of files are also included.

    Args:
        file (BufferedWriter): The file buffer to write the metadata to.
        file_meta_array (List[SngFileMetadata]): A list of metadata objects for each file.

    Returns:
        None
    """
    logger.info("Writing file metadata")

    calcd_size = struct.calcsize(_with_endian(s.ULONGLONG))
    for file_meta in file_meta_array:
        filename_len = len(file_meta.filename)
        calcd_size += (
            struct.calcsize(_with_endian(s.UBYTE))
            + struct.calcsize(_with_endian(filename_len, s.CHAR))
            + struct.calcsize(_with_endian(s.ULONGLONG)) * 2
        )

    file.write(struct.pack(_with_endian(s.ULONGLONG), calcd_size))
    file.write(struct.pack(_with_endian(s.ULONGLONG), len(file_meta_array)))
    logger.debug("Calculated file metadata section size: %d", calcd_size)

    fileoffset = file.tell() + calcd_size
    logger.debug("File content section start: %d", fileoffset)

    for file_meta in file_meta_array:
        logger.debug("Writing file metadata for %s", file_meta.filename)
        filename_len = len(file_meta.filename)
        file.write(struct.pack(_with_endian(s.UBYTE), filename_len))
        filename_packed = struct.pack(
            _with_endian(filename_len, s.CHAR), file_meta.filename.encode("utf-8")
        )
        file.write(filename_packed)
        logger.debug("%s content size: %d", file_meta.filename, file_meta.content_len)
        file.write(struct.pack(_with_endian(s.ULONGLONG), file_meta.content_len))
        logger.debug("%s offset: %d", file_meta.filename, fileoffset)
        file.write(struct.pack(_with_endian(s.ULONGLONG), fileoffset))
        fileoffset += file_meta.content_len

    logger.info("Wrote file metadata for %d files", len(file_meta_array))


def write_metadata(file: BufferedWriter, metadata: SngMetadataInfo) -> None:
    """
    Writes key-value pairs of metadata information for the SNG file.

    The metadata is stored as a series of length-prefixed strings (both for keys and values),
    with the total length of the metadata section prefixed at the start.

    Args:
        file (BufferedWriter): The file buffer to write the metadata to.
        metadata (SngMetadataInfo): A dictionary containing metadata key-value pairs.

    Returns:
        None
    """
    logger.info("Writing song metadata")

    metadata_content = struct.pack(_with_endian(s.ULONGLONG), len(metadata))
    key: str
    value: str
    for key, val in metadata.items():
        key_len: int = len(key)
        key_len_packed = struct.pack(_with_endian(s.UINT), key_len)
        key: bytes = struct.pack(_with_endian(key_len, s.CHAR), key.encode("utf-8"))

        value_len: int = len(val)
        value_len_packed: bytes = struct.pack(_with_endian(s.UINT), value_len)
        value: bytes = struct.pack(_with_endian(value_len, s.CHAR), val.encode("utf-8"))
        metadata_content += key_len_packed + key + value_len_packed + value

    file.write(struct.pack(_with_endian(s.ULONGLONG), len(metadata_content)))
    file.write(metadata_content)

    logger.info("Wrote song metadata")

def write_file_data(
    out: BufferedWriter,
    file_meta_array: List[Tuple[str, SngFileMetadata]],
    xor_mask: bytes,
):
    """
    Writes the actual file data for each file included in the SNG package.

    File data is read from the source files, optionally masked with an XOR mask for encryption,
    and written to the SNG file. Each file's data is preceded by its total length.

    Args:
        out (BufferedWriter): The output file buffer to write the data to.
        file_meta_array (List[Tuple[str, SngFileMetadata]]): A list of tuples containing file paths and their metadata.
        xor_mask (bytes): The byte sequence used as an XOR mask for file data encryption.

    Returns:
        None
    """
    logger.debug("Writing file data")

    total_file_data_length = sum(map(lambda x: x[1].content_len, file_meta_array))
    out.write(struct.pack(_with_endian(s.ULONGLONG), total_file_data_length))

    for filename, file_metadata in file_meta_array:
        amt_read = 0
        with open(filename, "rb") as f:
            while file_metadata.content_len > amt_read:
                chunk_size = (
                    1024
                    if file_metadata.content_len - amt_read > 1023
                    else file_metadata.content_len - amt_read
                )
                amt_read += chunk_size
                buf = f.read(chunk_size)
                out.write(mask(buf, xor_mask))

    logger.debug("Wrote file data")


def encode_sng(
    dir_to_encode: os.PathLike,
    *,
    output_filename: Optional[os.PathLike] = None,
    allow_nonsng_files: bool= False,
    version: int = 1,
    xor_mask: Optional[bytes] = None,
    metadata: Optional[SngMetadataInfo] = None,
) -> None:
    """
    Encodes a directory of files into a single SNG package file.

    This process involves reading metadata, writing a header, encoding file metadata,
    and writing the actual file data, optionally applying an XOR mask for encryption.

    Args:
        dir_to_encode (os.PathLike): The directory containing files to be encoded into the SNG package.
        output_filename (os.PathLike, optional): The path to the output SNG file. Defaults to the md5 sum of the resulting encoding.
        allow_nonsng_files (bool, optional): Allow encoding of files not allowed by the sng standard. Defaults to False.
        version (int, optional): The version of the SNG format to use. Defaults to 1.
        xor_mask (Optional[bytes], optional): An optional XOR mask for encryption. If not provided, a random one is generated.
        metadata (Optional[SngMetadataInfo], optional): Metadata for the SNG package. If not provided, it's read from a 'song.ini' file in the directory.

    Returns:
        None
    """
    if metadata is None:
        metadata = read_file_meta(dir_to_encode)
    if xor_mask is None:
        xor_mask = os.urandom(16)
    if output_filename is None:
        output_filename = dir_to_encode+'.sng'
    if not output_filename.endswith('.sng'):
        output_filename += '.sng'
    with open(output_filename, "wb") as file:
        write_header(file, version, xor_mask)
        write_metadata(file, metadata)
        file_meta_array = gather_files_from_directory(dir_to_encode, offset=file.tell(), allow_nonsng_files=allow_nonsng_files)
        write_file_meta(file, list(map(lambda x: x[1], file_meta_array)))
        write_file_data(file, file_meta_array, xor_mask)


def gather_files_from_directory(
    directory: os.PathLike, *, offset: int, allow_nonsng_files: bool
) -> List[Tuple[str, SngFileMetadata]]:
    """
    Gathers and prepares file metadata for all files in a given directory, excluding 'song.ini'.

    Each file's metadata includes its name, size, and offset position within the SNG file.

    Args:
        directory (os.PathLike): The directory to scan for files.
        offset (int): The initial offset where file data will start in the SNG file.
        allow_nonsng_files (bool): Allow encoding of files not allowed by the sng standard.

    Returns:
        List[Tuple[str, SngFileMetadata]]: A list of tuples containing file paths and their corresponding metadata objects.
    """
    file_meta_array = []
    current_index = offset

    for filename in os.listdir(directory):
        if not _valid_sng_file(filename):
            if filename in SNG_RESERVED_FILES:
                logger.debug("%s is reserved, skipping", filename)
                continue
            logger.warning("Found encoded file not set by the sng standard: %s", filename)
            if not allow_nonsng_files:
                logger.warning("Allowing non-sng files is set to False, skipping file %s.", filename)
                continue
            logger.warning("Allowing non-sng files is set to True, encoding file %s.", filename)
            
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            with open(filepath, "rb") as file:
                size = file.seek(0, os.SEEK_END)

            file_meta = SngFileMetadata(filename, size, current_index)
            file_meta_array.append((filepath, file_meta))

            current_index += size

    return file_meta_array


def read_file_meta(filedir: os.PathLike) -> SngMetadataInfo:
    """
    Reads metadata from a 'song.ini' file located in the given directory.

    The metadata is expected to be under a '[Song]' section in the INI file.

    Args:
        filedir (os.PathLike): The directory containing the 'song.ini' file.

    Returns:
        SngMetadataInfo: A dictionary containing the metadata key-value pairs.
    """
    cfg = ConfigParser()
    ini_path = os.path.join(filedir, "song.ini")
    if not os.path.exists(ini_path):
        raise FileNotFoundError("song.ini not found in provided directory.")
    with open(ini_path) as f:
        cfg.read_file(f)
    return dict(cfg["Song"])
