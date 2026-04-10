import logging

handler = logging.StreamHandler()
formatter = logging.Formatter('[%(levelname)s] %(name)s_%(method)s: %(message)s %(data)s')  # %(asctime)s if wanting to include time
handler.setFormatter(formatter)

logger = logging.getLogger('LC')
logger.addHandler(handler)
logger.setLevel(level=logging.INFO)
logger.propagate = False


def log_info(message, method, data=""):
    logger.info(message, extra={"method": method, "data": data})


def log_debug(message, method, data=""):
    logger.debug(message, extra={"method": method, "data": data})


def log_error(message, method, data=""):
    logger.error(message, extra={"method": method, "data": data})


def log_trace(message, method, data=""):
    logger.trace(message, extra={"method": method, "data": data})