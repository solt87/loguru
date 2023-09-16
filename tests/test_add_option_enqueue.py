import pickle
import re
import sys
import threading
import time

import pytest

from loguru import logger

from .conftest import default_threading_excepthook


class NotPicklable:
    def __getstate__(self):
        raise pickle.PicklingError("You shall not serialize me!")

    def __setstate__(self, state):
        pass


class NotPicklableTypeError:
    def __getstate__(self):
        raise TypeError("You shall not serialize me!")

    def __setstate__(self, state):
        pass


class NotUnpicklable:
    def __getstate__(self):
        return "..."

    def __setstate__(self, state):
        raise pickle.UnpicklingError("You shall not de-serialize me!")


class NotUnpicklableTypeError:
    def __getstate__(self):
        return "..."

    def __setstate__(self, state):
        raise TypeError("You shall not de-serialize me!")


class NotWritable:
    def write(self, message):
        if "fail" in message.record["extra"]:
            raise RuntimeError("You asked me to fail...")
        print(message, end="")


def test_enqueue():
    x = []

    def sink(message):
        time.sleep(0.1)
        x.append(message)

    logger.add(sink, format="{message}", enqueue=True)
    logger.debug("Test")
    assert len(x) == 0
    logger.complete()
    assert len(x) == 1
    assert x[0] == "Test\n"


def test_enqueue_with_exception():
    x = []

    def sink(message):
        time.sleep(0.1)
        x.append(message)

    logger.add(sink, format="{message}", enqueue=True)

    try:
        1 / 0  # noqa: B018
    except ZeroDivisionError:
        logger.exception("Error")

    assert len(x) == 0
    logger.complete()
    assert len(x) == 1
    lines = x[0].splitlines()

    assert lines[0] == "Error"
    assert lines[-1] == "ZeroDivisionError: division by zero"


def test_caught_exception_queue_put(writer, capsys):
    logger.add(writer, enqueue=True, catch=True, format="{message}")

    logger.info("It's fine")
    logger.bind(broken=NotPicklable()).info("Bye bye...")
    logger.info("It's fine again")
    logger.remove()

    out, err = capsys.readouterr()
    lines = err.strip().splitlines()
    assert writer.read() == "It's fine\nIt's fine again\n"
    assert out == ""
    assert lines[0] == "--- Logging error in Loguru Handler #0 ---"
    assert re.match(r"Record was: \{.*Bye bye.*\}", lines[1])
    assert lines[-2].endswith("PicklingError: You shall not serialize me!")
    assert lines[-1] == "--- End of logging error ---"


def test_caught_exception_queue_get(writer, capsys):
    logger.add(writer, enqueue=True, catch=True, format="{message}")

    logger.info("It's fine")
    logger.bind(broken=NotUnpicklable()).info("Bye bye...")
    logger.info("It's fine again")
    logger.remove()

    out, err = capsys.readouterr()
    lines = err.strip().splitlines()
    assert writer.read() == "It's fine\nIt's fine again\n"
    assert out == ""
    assert lines[0] == "--- Logging error in Loguru Handler #0 ---"
    assert lines[1] == "Record was: None"
    assert lines[-2].endswith("UnpicklingError: You shall not de-serialize me!")
    assert lines[-1] == "--- End of logging error ---"


def test_caught_exception_sink_write(capsys):
    logger.add(NotWritable(), enqueue=True, catch=True, format="{message}")

    logger.info("It's fine")
    logger.bind(fail=True).info("Bye bye...")
    logger.info("It's fine again")
    logger.remove()

    out, err = capsys.readouterr()
    lines = err.strip().splitlines()
    assert out == "It's fine\nIt's fine again\n"
    assert lines[0] == "--- Logging error in Loguru Handler #0 ---"
    assert re.match(r"Record was: \{.*Bye bye.*\}", lines[1])
    assert lines[-2] == "RuntimeError: You asked me to fail..."
    assert lines[-1] == "--- End of logging error ---"


def test_not_caught_exception_queue_put(writer, capsys):
    logger.add(writer, enqueue=True, catch=False, format="{message}")

    logger.info("It's fine")
    logger.bind(broken=NotPicklable()).info("Bye bye...")
    logger.info("It's fine again")

    logger.remove()

    out, err = capsys.readouterr()
    lines = err.strip().splitlines()
    assert writer.read() == "It's fine\nIt's fine again\n"
    assert out == ""
    assert lines[0] == "--- Logging error in Loguru Handler #0 ---"
    assert re.match(r"Record was: \{.*Bye bye.*\}", lines[1])
    assert lines[-2].endswith("PicklingError: You shall not serialize me!")
    assert lines[-1] == "--- End of logging error ---"


def test_not_caught_exception_queue_get(writer, capsys):
    logger.add(writer, enqueue=True, catch=False, format="{message}")

    with default_threading_excepthook():
        logger.info("It's fine")
        logger.bind(broken=NotUnpicklable()).info("Bye bye...")
        logger.info("It's fine again")
        logger.remove()

    out, err = capsys.readouterr()
    lines = err.strip().splitlines()
    assert writer.read() == "It's fine\nIt's fine again\n"
    assert out == ""
    assert lines[0] == "--- Logging error in Loguru Handler #0 ---"
    assert lines[1] == "Record was: None"
    assert lines[-2].endswith("UnpicklingError: You shall not de-serialize me!")
    assert lines[-1] == "--- End of logging error ---"


def test_not_caught_exception_sink_write(capsys):
    logger.add(NotWritable(), enqueue=True, catch=False, format="{message}")

    with default_threading_excepthook():
        logger.info("It's fine")
        logger.bind(fail=True).info("Bye bye...")
        logger.info("It's fine again")
        logger.remove()

    out, err = capsys.readouterr()
    lines = err.strip().splitlines()
    assert out == "It's fine\nIt's fine again\n"
    assert lines[0] == "--- Logging error in Loguru Handler #0 ---"
    assert re.match(r"Record was: \{.*Bye bye.*\}", lines[1])
    assert lines[-2] == "RuntimeError: You asked me to fail..."
    assert lines[-1] == "--- End of logging error ---"


def test_not_caught_exception_sink_write_then_complete(capsys):
    logger.add(NotWritable(), enqueue=True, catch=False, format="{message}")

    with default_threading_excepthook():
        logger.bind(fail=True).info("Bye bye...")
        logger.complete()
        logger.complete()  # Called twice to ensure it's re-usable.
        logger.remove()

    out, err = capsys.readouterr()
    lines = err.strip().splitlines()
    assert out == ""
    assert lines[0] == "--- Logging error in Loguru Handler #0 ---"
    assert re.match(r"Record was: \{.*Bye bye.*\}", lines[1])
    assert lines[-2] == "RuntimeError: You asked me to fail..."
    assert lines[-1] == "--- End of logging error ---"


def test_not_caught_exception_queue_get_then_complete(writer, capsys):
    logger.add(writer, enqueue=True, catch=False, format="{message}")

    with default_threading_excepthook():
        logger.bind(broken=NotUnpicklable()).info("Bye bye...")
        logger.complete()
        logger.complete()
        logger.remove()

    out, err = capsys.readouterr()
    lines = err.strip().splitlines()
    assert writer.read() == ""
    assert out == ""
    assert lines[0] == "--- Logging error in Loguru Handler #0 ---"
    assert lines[1] == "Record was: None"
    assert lines[-2].endswith("UnpicklingError: You shall not de-serialize me!")
    assert lines[-1] == "--- End of logging error ---"


def test_wait_for_all_messages_enqueued(capsys):
    def slow_sink(message):
        time.sleep(0.01)
        sys.stderr.write(message)

    logger.add(slow_sink, enqueue=True, catch=False, format="{message}")

    for i in range(10):
        logger.info(i)

    logger.complete()

    out, err = capsys.readouterr()

    assert out == ""
    assert err == "".join("%d\n" % i for i in range(10))


def test_complete_without_logging_any_message(writer):
    logger.add(writer, enqueue=True, catch=False, format="{message}")
    logger.complete()
    assert writer.read() == ""


def test_remove_without_logging_any_message(writer):
    logger.add(writer, enqueue=True, catch=False, format="{message}")
    logger.remove()
    assert writer.read() == ""


def test_main_thread_not_blocked(writer):
    event = threading.Event()

    def sink(message):
        event.wait()
        writer(message)

    logger.add(sink, enqueue=True, catch=False, format=lambda r: "{message}")

    # Pipes have default capacity of 65,536 bytes.
    # If it's full, the logger must not block.
    for _ in range(1000):
        logger.info("." * 10000)

    event.set()

    logger.complete()

    assert writer.read() == "." * 10000 * 1000


@pytest.mark.parametrize("exception_value", [NotPicklable(), NotPicklableTypeError()])
def test_logging_not_picklable_exception(exception_value):
    exception = None

    def sink(message):
        nonlocal exception
        exception = message.record["exception"]

    logger.add(sink, enqueue=True, catch=False)

    try:
        raise ValueError(exception_value)
    except Exception:
        logger.exception("Oups")

    logger.remove()

    type_, value, traceback_ = exception
    assert type_ is ValueError
    assert value is None
    assert traceback_ is None


@pytest.mark.parametrize("exception_value", [NotUnpicklable(), NotUnpicklableTypeError()])
def test_logging_not_unpicklable_exception(exception_value):
    exception = None

    def sink(message):
        nonlocal exception
        exception = message.record["exception"]

    logger.add(sink, enqueue=True, catch=False)

    try:
        raise ValueError(exception_value)
    except Exception:
        logger.exception("Oups")

    logger.remove()

    type_, value, traceback_ = exception
    assert type_ is ValueError
    assert value is None
    assert traceback_ is None
