import struct

from enum import Enum
from io import BufferedReader
from typing import NamedTuple, TypedDict, Tuple


def mask(data: bytes, xor_mask: bytes) -> bytearray:
    """
    Applies an XOR mask to the given data byte by byte, with an additional
    operation on the XOR key involving the index.

    The XOR key for each byte is the corresponding byte in the xor_mask,
    XORed with the lower 8 bits of the index, allowing the mask to cycle
    every 16 bytes and vary per byte position.

    Args:
        data (bytes): The input data to be masked.
        xor_mask (bytes): The mask to be applied, typically 16 bytes long.

    Returns:
        bytearray: The masked data as a mutable bytearray.
    """
    masked_data = bytearray(len(data))
    for i in range(len(data)):
        xor_key = xor_mask[i % 16] ^ (i & 0xFF)
        masked_data[i] = data[i] ^ xor_key
    return masked_data


def calc_and_unpack(fmt: str, buf: BufferedReader) -> tuple:
    """
    Calculates the size of the structure described by `fmt`, reads
    that many bytes from `buf`, and unpacks the bytes according to `fmt`.

    Args:
        fmt (str): The format string for unpacking the data.
        buf (BufferedReader): The buffer from which to read the data.

    Returns:
        tuple: The unpacked data.
    """
    read_size = struct.calcsize(fmt)
    buffer = buf.read(read_size)
    return struct.unpack_from(fmt, buffer)

def calc_and_read_buf(fmt: str, buf: BufferedReader) -> Tuple[int, bytes]:
    """
    Calculates the size required for the format `fmt`, reads that many bytes
    from the buffer `buf`, and returns the size read along with the bytes.

    Args:
        fmt (str): The format string representing the data structure to read.
        buf (BufferedReader): The buffer from which to read the data.

    Returns:
        Tuple[int, bytes]: A tuple containing the number of bytes read and the read bytes.
    """
    read_size = struct.calcsize(fmt)
    return read_size, buf.read(read_size)


class StructTypes(Enum):
    """
    Enumerates the structure types used for sng data manipulation,
    ensuring consistent endianness and providing easy
    access to format characters for common data types.
    """
    ENDIAN = "<" # Little-endian
    UINT = "I" # Unsigned int
    ULONGLONG = "Q" # Unsigned long long
    UBYTE = "B" # Unsigned byte
    CHAR = "s" # Single character


def _with_endian(*args: Tuple[StructTypes | int]):
    """
    Constructs a format string for struct operations that includes the specified
    endian prefix followed by the format specifiers provided in `args`.

    Args:
        *args (Tuple[StructTypes | int]): A sequence of StructTypes enums or integers
        representing the number of characters.

    Returns:
        str: The format string with endian prefix.
    """
    return StructTypes.ENDIAN.value+''.join(map(lambda x: x.value if isinstance(x, StructTypes) else str(x), args))


class SngFileMetadata(NamedTuple):
    """
    Represents the metadata for a file within an SNG package, including its name,
    content length, and content index (offset within the SNG file).
    """
    filename: str
    content_len: int
    content_idx: int


class SngHeader(NamedTuple):
    """
    Represents the header information of an SNG file, including the file identifier,
    version, and an XOR mask for encryption/decryption.
    """
    file_identifier: bytes
    version: int
    xor_mask: bytes


class SngMetadataInfo(TypedDict):
    """
    A dictionary type that specifies the structure and expected types of metadata
    for an SNG file.
    """
    name: str
    artist: str
    album: str
    genre: str
    year: int
    diff_band: int
    diff_guitar: int
    diff_rhythm: int
    diff_guitar_coop: int
    diff_bass: int
    diff_drums: int
    diff_drums_real: int
    diff_keys: int
    diff_guitarghl: int
    diff_bassghl: int
    diff_guitar_coop_ghl: int
    diff_rhythm_ghl: int
    preview_start_time: int
    playlist_track: int
    modchart: bool
    song_length: int
    pro_drums: bool
    five_lane_drums: bool
    album_track: int
    charter: str
    hopo_frequency: int
    eighthnote_hopo: bool
    multiplier_note: int
    delay: int
    video_start_time: int
    end_events: bool
