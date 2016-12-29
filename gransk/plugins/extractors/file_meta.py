#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
# breaks http put
# from __future__ import unicode_literals

import re
import os
import json
import subprocess


import gransk.core.helper as helper
import gransk.core.abstract_subscriber as abstract_subscriber
import six


class Subscriber(abstract_subscriber.Subscriber):
  """Class for extracting metadata from documents using Apache Tika."""
  CONSUMES = [helper.EXTRACT_META]

  def setup(self, config):
    """
    Load mediatype mapping from file. This is used to determine document type.

    :param config: Configuration object.
    :type config: ``dict``
    """
    self.config = config
    typecache = {}
    media_path = os.path.join(
        config[helper.CODE_ROOT], 'utils', 'media_types.txt')

    with open(media_path) as inp:
      current = None
      for line in inp:
        if len(line.strip()) == 0 or line.startswith('#'):
          continue

        if line.strip().startswith('-'):
          apptype = line.strip().partition('-')[2]
          apptype = apptype.strip()
          typecache[current].append(re.escape(apptype))
        else:
          current = line.strip()
          typecache[current] = []

    pattern_list = []

    for _type, patterns in typecache.items():
      pattern_list.append('(?P<%s>(%s))' % (_type, '|'.join(patterns)))

    self.typepattern = re.compile('|'.join(pattern_list), re.I)

  def __extract_metadata(self, doc, payload):
    filename = os.path.basename(doc.path)
    headers = {
        'Accept': 'application/json',
        'Content-Disposition': 'attachment; filename=%s' % filename
    }

    tika_url = self.config.get(helper.TIKA_META)

    if not tika_url:
      tika_url = self.config.get(helper.TIKA_HOST)

    connection = self.config[helper.INJECTOR].get_http_connection(tika_url)
    payload.seek(0)
    connection.request('PUT', '/meta', payload.read(), headers)
    payload.seek(0)

    response = connection.getresponse()

    response_text = response.read().decode('utf-8')

    result = json.loads(response_text)

    response.close()

    return result

  def __get_mime_type(self, payload):
    # This method needs testing/changes (https://thraxil.org/users/anders/posts/2008/03/13/Subprocess-Hanging-PIPE-is-your-enemy/)
    """payload.seek(0)
    cmd = ('file', '--brief', '--mime-type', '-')
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, _ = proc.communicate(payload.read())
    payload.seek(0)

    if proc.returncode != 0:
      return None

    return out.strip().decode("utf-8")"""

    return None

  def consume(self, doc, payload):
    """
    Upload document to Apache Tika and parse results.

    :param doc: Document object.
    :param payload: File pointer beloning to document.
    :type doc: ``gransk.core.document.Document``
    :type payload: ``file``
    """
    meta = {}

    max_size = self.config.get(helper.MAX_FILE_SIZE, 0)

    if max_size > 0 and doc.meta['size'] > max_size:
      return

    try:
      meta = self.__extract_metadata(doc, payload)
    except Exception as err:
      doc.meta['meta_error'] = six.text_type(err)

    if 'Content-Type' not in meta:
      meta['Content-Type'] = self.__get_mime_type(payload)

    if not meta['Content-Type']:
      meta['Content-Type'] = 'unknown'

    if type(meta['Content-Type']) == list:
      meta['Content-Type'] = '\x00'.join(meta['Content-Type'])

    for match in self.typepattern.finditer(meta['Content-Type']):
      doc.set_type(match.lastgroup)

    for key, value in meta.items():
      doc.meta[key.replace('.', '_').replace(':', '_')] = value
