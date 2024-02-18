import os

from io import BytesIO, BufferedWriter, BufferedReader
from ..common import write_and_mask, mask
import soundfile as sf

# def to_opus(filepath: str) -> BytesIO:
#     filename, ext = filepath.split('.')
#     with sf.SoundFile(filepath, 'r') as f:
#         size = f.seek(0, os.SEEK_END)
#         chunk_size = 1024
#         f.seek(0)
#         out = BytesIO()
#         out.name = filename+'.opus'
#         with sf.SoundFile(out, 'w', samplerate=f.samplerate, channels=f.channels, format='ogg', subtype='Opus', endian=f.endian) as g:
#             while f.tell() != size:
#                 if size - f.tell() < chunk_size:
#                     chunk_size = size - f.tell()
#                 g.write(f.read(chunk_size))
#     out.seek(0)
#     return out

def to_opus(filepath: str, buf: BufferedWriter):
    with sf.SoundFile(filepath, 'r') as f:
        filename, ext = filepath.split('.')
        size = f.seek(0, os.SEEK_END)
        chunk_size = 1024
        f.seek(0)
        out= BytesIO()
        # BufferedWriter(BytesIO())
        out.name = filename+".opus"
        with sf.SoundFile(out, 'w', samplerate=f.samplerate, channels=f.channels, format='ogg', subtype='Opus') as g:
            while f.tell() != size:
                if size - f.tell() < chunk_size:
                    chunk_size = size - f.tell()
                g.write(f.read(chunk_size))
                buf.write(out.read(chunk_size))
                out.seek(0)
    # return out

# def to_opus_generator(filepath: str) -> Generator[None, None, BytesIO]:
#     filename, ext = filepath.split('.')
#     with sf.SoundFile(filepath, 'r') as f:
#         size = f.seek(0, os.SEEK_END)
#         chunk_size = 1024
#         f.seek(0)
#         out = BytesIO()
#         out.name = filename+'.opus'
#         with sf.SoundFile(out, 'w', samplerate=f.samplerate, channels=f.channels, format='ogg', subtype='Opus', endian=f.endian) as g:
#             while f.tell() != size:
#                 if size - f.tell() < chunk_size:
#                     chunk_size = size - f.tell()
#                 g.write(f.read(chunk_size))