from celery import Celery
from django.conf import settings
import logging

from cadasta.workertoolbox.conf import Config
from cadasta.workertoolbox.setup import setup_app

from core import breakers

from .amqp import CircuitBreakerAMQP


logger = logging.getLogger(__name__)


def get_app(conf):
    """ App setup, placed in function to make testing easier """
    app = Celery(amqp=CircuitBreakerAMQP)
    app.config_from_object(conf)
    try:
        breakers.celery.call(setup_app, app, throw=True)
    except breakers.celery.expected_errors:
        logger.exception("Failed to setup celery app.")
    return app


conf = Config(
    broker_transport=settings.CELERY_BROKER_TRANSPORT,
    QUEUE_PREFIX=settings.CELERY_QUEUE_PREFIX,
    SETUP_LOGGING=False,
)
app = get_app(conf)
