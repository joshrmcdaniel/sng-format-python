import io
from multiprocessing.pool import ThreadPool
from concurrent.futures import as_completed, ThreadPoolExecutor
from typing import List, Tuple
from asyncio import Future
from ..audio import to_opus
import tempfile
from ..common import FileOffset, write_and_mask, _validate_and_pack, _with_endian, StructTypes
import logging

s = StructTypes

logger = logging.getLogger(__package__)

def execute_audio_pool(offset_ref: List[FileOffset]) -> Tuple[ThreadPoolExecutor, List[Future]]:
    tmp_files = [(x, y, tempfile.TemporaryFile("w+b")) for x,y in offset_ref]
    pool = ThreadPoolExecutor(6)
    futures = []
    for filename, offset, tmp in tmp_files:
        logger.debug("Submitting conversion task for %s", filename)
        futures.append(pool.submit(_wrap, filename, offset, tmp))
    return pool, futures


def _wrap(filename: str, offset: int, tmpfile: io.FileIO):
    to_opus(filename, tmpfile)
    tmpfile.truncate()
    tmpfile.seek(0)
    return filename, offset, tmpfile


def _eval_transcoding(buf: io.BufferedWriter, filename, offset, tmpfile: io.FileIO, *, xor_mask) -> int:
    logger.debug("Completed %s transcoding", filename)
    before_write = buf.tell()
    write_and_mask(read_from=tmpfile, write_to=buf, xor_mask=xor_mask)
    tmpfile.close()
    after_write =buf.tell()
    buf.truncate()
    opus_size = after_write - before_write
    size = opus_size
    logger.debug("Opus size for %s: %d", filename, size)
    buf.seek(offset)
    buf.write(_validate_and_pack(_with_endian(s.ULONGLONG), opus_size))
    buf.write(_validate_and_pack(_with_endian(s.ULONGLONG), before_write))
    buf.seek(after_write)
    buf.truncate()
    return size

def eval_futures(buf: io.BufferedWriter, pool: ThreadPoolExecutor, futures: List[Future], *, xor_mask: bytearray) -> int:
    size = 0
    logger.debug("Iterating futures.")
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