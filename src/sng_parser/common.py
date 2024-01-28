import struct
from io import BufferedWriter, FileIO

from typing import List, NamedTuple, TypedDict


def write_uint8(byte_io: bytearray | BufferedWriter, value):
    if isinstance(byte_io, bytearray):
        byte_io += struct.pack("<B", value)
    elif isinstance(byte_io, (FileIO, BufferedWriter)):
        byte_io.write(struct.pack("<B", value))


def write_uint32(byte_io: bytearray | BufferedWriter, value: int | str | bytes):
    if isinstance(byte_io, bytearray):
        byte_io += struct.pack("<I", value)
    elif isinstance(byte_io, (FileIO, BufferedWriter)):
        byte_io.write(struct.pack("<I", value))


def write_uint64(byte_io: bytearray | BufferedWriter, value: int | str | bytes):
    if isinstance(byte_io, bytearray):
        byte_io += struct.pack("<Q", value)
    elif isinstance(byte_io, (FileIO, BufferedWriter)):
        byte_io.write(struct.pack("<Q", value))


def write_string(byte_io: bytearray | BufferedWriter, value: int | str | bytes):
    if isinstance(byte_io, bytearray):
        byte_io += value.encode("utf-8")
    elif isinstance(byte_io, (FileIO, BufferedWriter)):
        byte_io.write(value.encode("utf-8"))


def mask(data: bytes, xor_mask: bytes) -> bytearray:
    masked_data = bytearray(len(data))
    for i in range(len(data)):
        xor_key = xor_mask[i % 16] ^ (i & 0xFF)
        masked_data[i] = data[i] ^ xor_key
    return masked_data


class SngFileMetadata(NamedTuple):
    filename: str
    content_len: int
    content_idx: int


class SngMetadataInfo(TypedDict):
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


class ParsedSngData(TypedDict):
    file_identifier: str
    version: int
    xor_mask: bytes
    metadata: SngMetadataInfo
    file_meta_array: List[SngFileMetadata]
    file_data_array: List[bytearray]
