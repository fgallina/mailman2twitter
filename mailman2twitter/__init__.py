#!/usr/bin/env python
from urllib import urlencode
from urlparse import urljoin
import datetime
import logging.config
import os.path
import pickle
import re
import sys
import textwrap
import time

from bs4 import BeautifulSoup
import requests
import twitter


try:
    from ConfigParser import ConfigParser, NoSectionError
except ImportError:
    from configparser import ConfigParser, NoSectionError


VERSION = (0, 1, 0, 'alpha', 0)
OWLY_API_BASE_URL = 'http://ow.ly/api/1.1/'


logger = logging.getLogger('mailman2twitter')
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

parser = ConfigParser()

parser.add_section('mailman2twitter')
parser.set('mailman2twitter', 'backoff', '4')
parser.set('mailman2twitter', 'base_url', '')
parser.set('mailman2twitter', 'db', '~/mailman2twitter.sqlite')
parser.set('mailman2twitter', 'max_tries', '3')
parser.set('mailman2twitter', 'testing', 'false')

parser.add_section('twitter')
parser.set('twitter', 'consumer_key', '')
parser.set('twitter', 'consumer_secret', '')
parser.set('twitter', 'access_token_key', '')
parser.set('twitter', 'access_token_secret', '')

parser.add_section('owly')
parser.set('owly', 'api_key', '')


class MaxTriesReachedError(Exception):
    pass


# Thanks again, Django.
def get_version(version=VERSION):
    "Returns a PEP 386-compliant version number from VERSION."
    assert len(version) == 5
    assert version[3] in ('alpha', 'beta', 'rc', 'final')

    parts = 2 if version[2] == 0 else 3
    main = '.'.join(str(x) for x in version[:parts])

    if version[3] != 'final':
        mapping = {'alpha': 'a', 'beta': 'b', 'rc': 'c'}
        sub = mapping[version[3]] + str(version[4])

    return str(main + sub)


def load_config():
    """
    Loads a configuration file.

    Files are searched in the following order:
      + ~/.config/mailman2twitter.conf
      + ~/.mailman2twitter.conf
      + /etc/mailman2twitter.conf

    Configuration file can also contain logging configuration.
    """
    paths = [os.path.expanduser("~/.config/mailman2twitter.conf"),
             os.path.expanduser("~/.mailman2twitter.conf"),
             '/etc/mailman2twitter.conf']

    for path in paths:
        if os.path.exists(path):
            break
    else:
        sys.stderr.write("No configuration file found.\n")
        sys.exit(3)

    try:
        logging.config.fileConfig(path)
    except NoSectionError:
        pass

    parser.read(path)
    return parser


def is_testing(config):
    return config.getboolean('mailman2twitter', 'testing')


def print_help():
    doc = """
    Sends new threads to twitter.

    Usage:
        mailman2twitter.py [-h|--help] [-c|--config]

    -h|--help:       prints this help text and exits.
    -c|--config:     prints a sample config and exits.

    You need to create a configuration file at either of the following
    locations:
      + ~/.config/mailman2twitter.conf
      + ~/.mailman2twitter.conf
      + /etc/mailman2twitter.conf

    Here's a sample config:

        [mailman2twitter]
        # DB location
        db = ~/mailman2twitter.db
        # base_url of the archive
        base_url = http://lugro.org.ar/pipermail/lugro/
        # how many attemps to try for every failed network push
        max_tries = 3
        # Initial time in seconds for the exponential backoff.
        backoff = 4
        # In testing mode, no database is written or read and no message is
        # pushed to twitter.  Think of it as a dry-run.
        testing = false

        [twitter]
        consumer_key = consumer_key
        consumer_secret = consumer_secret
        access_token_key = access_token
        access_token_secret = access_token_secret

        [owly]
        api_key = abcdef123456

    Such config can also contain logging configuration settings.

    """
    print (doc)


def print_example_config():
    conf = """
    [mailman2twitter]
    # Where's the sqlite database to use.
    db = ~/mailman2twitter.db
    # base_url of the archive
    base_url = http://lugro.org.ar/pipermail/lugro/
    backoff = 4
    max_tries = 3
    # In testing mode, no database is written or read and no message is pushed
    # to twitter.  Think of it as a dry-run.
    testing = false

    [twitter]
    consumer_key =
    consumer_secret =
    access_token_key =
    access_token_secret =

    [owly]
    api_key =
    """
    print textwrap.dedent(conf).strip()


def shorten_url(config, url):
    """
    Shorten URL using the owly API.

    Args:
        + config: A ConfigParser instance.
        + url: The url to shorten.

    Raises:
        IOError: If API fails somehow.

    Returns:
        A string with the shortened URL.
    """
    key = config.get('owly', 'api_key')
    params = urlencode({'apiKey': key, 'longUrl': url})
    url = urljoin(OWLY_API_BASE_URL, 'url/shorten') + '?' + params
    response = requests.get(url)
    code = response.status_code
    if not code == 200:
        raise IOError("Owly replied with code: %s" % code)
    data = response.json()
    return data['results']['shortUrl'].encode('utf-8')


def push_twitter(config, message):
    """
    Push message to twitter.
    """
    MAX_SUBJECT_SIZE = 116

    consumer_key = config.get('twitter', 'consumer_key')
    consumer_secret = config.get('twitter', 'consumer_secret')
    access_token_key = config.get('twitter', 'access_token_key')
    access_token_secret = config.get('twitter', 'access_token_secret')

    api = twitter.Api(consumer_key=consumer_key,
                      consumer_secret=consumer_secret,
                      access_token_key=access_token_key,
                      access_token_secret=access_token_secret)

    message_id, subject, message_url = message
    short_url = shorten_url(config, message_url)

    if len(subject) > MAX_SUBJECT_SIZE:
        subject = subject[:MAX_SUBJECT_SIZE - 3] + "..."

    post = "%s: %s" % (subject, short_url)

    logger.info("Sending: %s" % post)

    if not is_testing(config):
        api.PostUpdate(post)
    else:
        logger.debug("Not sending to twitter (testing mode): %s" % message_id)


def exec_with_backoff(fn, config, *args, **kwargs):
    """
    Executes fn with exponential backoff.

    Arguments:
        config: A ConfigParser instance, used to get backoff settings.
        fn: A callable to execute.
        args: A list of arguments to pass to the callable.
        kwargs: Keyword of arguments to pass to the callable.

    Raises:
        MaxTriesReachedError: After all retries failed.
    """
    backoff = config.getint('mailman2twitter', 'backoff')
    max_tries = config.getint('mailman2twitter', 'max_tries')

    for _ in range(max_tries):
        try:
            return fn(config, *args, **kwargs)
        except Exception:
            logger.exception("Push failed, waiting for %s seconds" % backoff)
            time.sleep(backoff)
            backoff **= 2
    else:
        raise MaxTriesReachedError('Stop trying to task after: %s' % backoff)


def normalize_base_url(base_url):
    """Sanitizes user provided base_url"""
    if not base_url.endswith('/'):
        base_url += '/'
    return base_url


def get_date_url(base_url):
    """Calculates the archive url from the base_url and current date."""
    base_url = normalize_base_url(base_url)
    today = datetime.datetime.today()
    date_url = '%s/date.html' % today.strftime('%Y-%B')
    return urljoin(base_url, date_url)


def get_message_data(link, archive_url):
    """
    Retrieves message data from a link tag.

    Arguments:
        link: A tag as returned by `BeautifulSoup.find`.
        archive_url: The url of the archive.

    Returns:
        A 3 element tuple where the first element is the message id, the
        second the subject and the last one the message URL
    """
    subject = (link.encode_contents().strip()
               # I got several occurrences of places where spaces where
               # replaced with tabs on subjects for replies to OP, we handle
               # this here.
               .replace("\t", " "))
    href = link.get('href').strip()
    message_id = href.split('.')[0].strip()
    message_url = urljoin(archive_url, href)
    return message_id, subject, message_url


def load_db(config):
    """Loads the database."""
    if is_testing(config):
        return set()

    db_path = config.get('mailman2twitter', 'db')

    if not os.path.exists(db_path):
        # Create database it doesn't exists.
        logger.debug("Database not found at %s, creating..." % db_path)
        with open(db_path, 'w') as db:
            pickle.dump(set(), db)

    with open(db_path, 'r+') as db:
        return pickle.load(db)


def update_db(config, data):
    """Updates the database."""
    if is_testing(config):
        return
    db_path = config.get('mailman2twitter', 'db')
    with open(db_path, 'w') as db:
        return pickle.dump(data, db)


def collect_messages(config, sent_subjects):
    """Collects all messages from the list archive."""
    base_url = config.get('mailman2twitter', 'base_url')
    archive_url = get_date_url(base_url)
    response = requests.get(archive_url)
    soup = BeautifulSoup(response.content)
    messages = []
    sent_subjects = sent_subjects.copy()
    for message_link in soup.find_all('a', href=re.compile("\d+.html")):
        data = get_message_data(message_link, archive_url)
        subject = data[1]
        if subject in sent_subjects:
            continue
        sent_subjects.add(subject)
        messages.append(data)
    return messages


def push_threads(config):
    sent_subjects = load_db(config)
    messages = collect_messages(config, sent_subjects)
    for message in messages:
        message_id, subject, message_url = message
        if message_id in sent_subjects:
            logger.debug('Skipping %s, already sent.' % message_id)
            continue
        try:
            exec_with_backoff(push_twitter, config, message)
            sent_subjects.add(subject)
        except MaxTriesReachedError:
            pass
    update_db(config, sent_subjects)


def main():
    argv = sys.argv
    if len(argv) == 1:
        push_threads(load_config())
        sys.exit(0)
    elif argv[1] in ['-c', '--config']:
        print_example_config()
        sys.exit(0)
    elif argv[1] in ['-h', '--help']:
        print_help()
        sys.exit(0)
    else:
        sys.stderr.write("Unrecognized switch\n")
        print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
