import os

from io import BytesIO, BufferedWriter
import soundfile as sf

import logging

logger = logging.getLogger(__package__)


def to_opus(filepath: str, buf: BufferedWriter) -> None:
    with sf.SoundFile(filepath, "r") as f:
        filename, _ = filepath.split(".")
        size = f.seek(0, os.SEEK_END)
        chunk_size = 1024
        f.seek(0)
        out = BytesIO()
        out.name = filename + ".opus"
        sample_rate = f.samplerate
        logger.debug("Bitrate of `%s`: %d", filepath, sample_rate)
        if sample_rate > 80000:
            # use recommended
            sample_rate = 80000
            logger.debug(
                "%s bitrate greater than the recommended, capping at %d",
                filepath,
                sample_rate,
            )
        with sf.SoundFile(
            out,
            "w",
            samplerate=sample_rate,
            channels=f.channels,
            format="ogg",
            subtype="Opus",
        ) as g:
            while f.tell() != size:
                if size - f.tell() < chunk_size:
                    chunk_size = size - f.tell()
                g.write(f.read(chunk_size))
                buf.write(out.read(chunk_size))
                out.seek(0)
