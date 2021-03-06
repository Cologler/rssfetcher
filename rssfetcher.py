# -*- coding: utf-8 -*-
#
# Copyright (c) 2020~2999 - Cologler <skyoflw@gmail.com>
# ----------
# require packages:
#   - pyyaml
#   - requests
# ----------

import logging
import sqlite3
from urllib.parse import urlparse
import xml.etree.ElementTree as et
import os
from io import StringIO
import sys
import traceback

import requests
import yaml

TABLE_NAME = 'rss'
COLUMN_NAMES = ['feed_id', 'rss_id', 'title', 'raw']
DEF_COL = ', '.join([
    COLUMN_NAMES[0] + ' TEXT NOT NULL',
    COLUMN_NAMES[1] + ' TEXT NOT NULL',
    COLUMN_NAMES[2] + ' TEXT',
    COLUMN_NAMES[3] + ' TEXT',
    'PRIMARY KEY ({}, {})'.format(COLUMN_NAMES[0], COLUMN_NAMES[1]),
])
SQL_CREATE = 'CREATE TABLE IF NOT EXISTS {} ({});'.format(TABLE_NAME, DEF_COL)
SQL_INSERT = 'INSERT OR IGNORE INTO {} VALUES ({});'.format(
    TABLE_NAME,
    ",".join("?" for _ in COLUMN_NAMES))
SQL_COUNT = 'SELECT COUNT({}) FROM {}'.format(COLUMN_NAMES[0], TABLE_NAME)

def get_logger():
    return logging.getLogger('rssfetcher')

def dump_xml(el):
    sb = StringIO()
    tr = et.ElementTree(el)
    tr.write(sb, encoding='unicode', short_empty_elements=False)
    return sb.getvalue()

def fetch_feed(feed_id, feed_section):
    items = []
    url = feed_section.get('url')
    if url:
        logger = get_logger().getChild(url)
        proxies = feed_section.get('proxies')
        if proxies is None:
            proxy = feed_section.get('proxy')
            if proxy:
                scheme = urlparse(proxy).scheme
                if not scheme:
                    scheme = urlparse(url).scheme or 'http'
                    proxy = scheme + '://' + proxy
                proxies = {}
                proxies[scheme] = proxy

        if proxies:
            logger.info('use proxies: %s', proxies)

        try:
            r = requests.get(url, proxies=proxies, timeout=(5, 60))
        except requests.ConnectionError as error:
            logger.error('raised %s: %s', type(error).__name__, error)
            return []

        try:
            r.raise_for_status()
        except requests.HTTPError as error:
            logger.error('raised %s: %s', type(error).__name__, error)
            return []

        r.encoding = 'utf8'
        try:
            body = r.text
        except (requests.ConnectionError, requests.Timeout) as error:
            logger.error('raised %s: %s', type(error).__name__, error)
        else:
            el = et.fromstring(body)
            for item in el.iter('item'):
                rd = {
                    'feed_id': feed_id,
                    'rss_id': item.find('guid').text,
                    'title': item.find('title').text,
                    'pub_date': item.find('pubDate').text,
                    'raw': dump_xml(item)
                }
                description = item.find('description')
                if description is not None:
                    rd['description'] = description.text
                items.append(rd)
            logger.info('total found %s items',len(items))
    return items

def get_count(cur):
    cur.execute(SQL_COUNT)
    return cur.fetchone()[0]

def from_conf(conf_path):
    if os.path.isfile(conf_path):
        with open(conf_path, mode='r', encoding='utf8') as fp:
            conf_data = yaml.safe_load(fp)
        with sqlite3.connect(conf_data.get('database', 'rss.sqlite3')) as con:
            cur = con.cursor()
            cur.execute(SQL_CREATE)
            count = get_count(cur)
            fetched = []
            for feed_id, feed_section in conf_data.get('feeds', {}).items():
                items = fetch_feed(feed_id, feed_section)
                for item in items:
                    fetched.append(tuple(item.get(x) for x in COLUMN_NAMES))
            cur.executemany(SQL_INSERT, fetched)
            count = get_count(cur) - count
            get_logger().info('total added %s rss', count)
            con.commit()
    else:
        get_logger().error('no such file: %s', conf_path)

def _pop_options_kvp(argv, key):
    option_name = '--logger'
    try:
        index = argv.index(option_name)
    except ValueError:
        index = -1
    option_value = None
    if index >= 0 and len(argv) > index + 1:
        argv.pop(index)
        return argv.pop(index)
    return None

def configure_logger(argv):
    logging_options = dict(
        filename='rssfetcher.log',
        format='%(asctime)s [%(levelname)s] - %(name)s: %(message)s',
        datefmt='%m/%d/%Y %I:%M:%S %p',
        level=logging.INFO
    )
    option_value = _pop_options_kvp(argv, '--logger')
    if option_value == 'console':
        logging_options.pop('filename', None)
    logging.basicConfig(**logging_options)

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    configure_logger(argv)
    try:
        from_conf(argv[0])
    except Exception as error: # pylint: disable=W0703
        get_logger().error('main raised: %s', error, stack_info=True)

if __name__ == '__main__':
    main()
