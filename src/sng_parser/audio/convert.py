import os

from io import BytesIO, BufferedWriter
import soundfile as sf


def to_opus(filepath: str, buf: BufferedWriter) -> None:
    with sf.SoundFile(filepath, 'r') as f:
        filename, _ = filepath.split('.')
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
