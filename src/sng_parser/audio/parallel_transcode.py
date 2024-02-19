import io
from multiprocessing.pool import ThreadPool
from concurrent.futures import as_completed, ThreadPoolExecutor
from typing import List, Callable, Tuple
from asyncio import Future
from .convert import to_opus
import tempfile
from ..common import (
    FileOffset,
    write_and_mask,
    _validate_and_pack,
    _with_endian,
    StructTypes,
)
import logging
from multiprocessing import cpu_count


s = StructTypes

logger = logging.getLogger(__package__)

__all__ = [
    'parllel_transcode_opus',
    'eval_futures'
]
def _execute_audio_pool(
    _wrap: Callable,
    offset_ref: List[FileOffset],
) -> Tuple[ThreadPoolExecutor, List[Future]]:
    try:
        cores = cpu_count() // 4
    except NotImplementedError:
        # sometimes not specified
        cores = 4
    threads = min(cores, len(offset_ref))
    tmp_files = [(x, y, tempfile.TemporaryFile("w+b")) for x, y in offset_ref]
    logger.debug("Spinning up thread pool with %d threads", threads)
    pool = ThreadPoolExecutor(threads)
    futures = []
    for filename, offset, tmp in tmp_files:
        logger.debug("Submitting opus transcoding task for `%s`", filename)
        futures.append(pool.submit(_wrap, filename, offset, tmp))
    logger.debug("Submitted %d transcoding tasks", len(futures))
    return pool, futures


def parllel_transcode_opus(offset_ref: List[FileOffset]):
    logger.debug("Encoding audio files to opus")
    return _execute_audio_pool(_wrap_opus, offset_ref)

def _wrap_opus(filename: str, offset: int, tmpfile: io.FileIO):
    to_opus(filename, tmpfile)
    tmpfile.truncate()
    tmpfile.seek(0)
    return filename, offset, tmpfile


def _eval_transcoding(
    buf: io.BufferedWriter, filename, offset, tmpfile: io.FileIO, *, xor_mask: bytearray
) -> int:
    logger.debug("Completed `%s` transcoding", filename)
    logger.debug("Trancoded to: opus")
    before_write = buf.tell()
    logger.debug("Writing transcoded `%s` to disk", filename)
    write_and_mask(read_from=tmpfile, write_to=buf, xor_mask=xor_mask)
    tmpfile.close()
    after_write = buf.tell()
    buf.truncate()
    opus_size = after_write - before_write
    size = opus_size
    logger.debug("Wrote `%s` transcoded (size: %d bytes)", filename, size)
    buf.seek(offset)
    buf.write(_validate_and_pack(_with_endian(s.ULONGLONG), opus_size))
    buf.write(_validate_and_pack(_with_endian(s.ULONGLONG), before_write))
    buf.seek(after_write)
    buf.truncate()
    return size


def eval_audio_futures(
    buf: io.BufferedWriter,
    pool: ThreadPoolExecutor,
    futures: List[Future],
    *,
    xor_mask: bytearray,
) -> int:
    size = 0
    logger.debug("Iterating transcoding futures.")
    try:
        for future in as_completed(futures):
            size += _eval_transcoding(buf, *future.result(), xor_mask=xor_mask)
    except KeyboardInterrupt as ke:
        logger.error("Keyboard interrupt during transcoding, exiting gracefully")
        pool.shutdown(cancel_futures=True)
        raise ke
    except Exception as e:
        logger.error("Unknown exception occured")
        pool.shutdown(cancel_futures=True)
        raise e
    pool.shutdown()

    return size
