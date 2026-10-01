# coding: utf-8
#
# Copyright (C) 2020, Team Kodi
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Functions to interact with various web site APIs."""

from __future__ import absolute_import, unicode_literals

import json
import time

try:
    import xbmc
except ModuleNotFoundError:
    # only used for logging HTTP calls, not available nor needed for testing
    xbmc = None

# from pprint import pformat
try: #PY2 / PY3
    from urllib2 import Request, urlopen
    from urllib2 import URLError
    from urllib import urlencode
except ImportError:
    from urllib.request import Request, urlopen
    from urllib.error import URLError
    from urllib.parse import urlencode
try:
    from typing import Text, Optional, Union, List, Dict, Any  # pylint: disable=unused-import
    InfoType = Dict[Text, Any]  # pylint: disable=invalid-name
except ImportError:
    pass

HEADERS = {}


def set_headers(headers):
    HEADERS.clear()
    HEADERS.update(headers)


def load_info(url, params=None, default=None, resp_type = 'json', data=None):
    # type: (Text, Optional[Dict[Text, Union[Text, List[Text]]]]) -> Union[dict, list]
    """
    Load info from external api

    :param url: API endpoint URL
    :param params: URL query params
    :default: object to return if there is an error
    :resp_type: what to return to the calling function
    :data: optional JSON-serializable body; when set the request is POSTed
    :return: API response or default on error
    """
    theerror = ''
    if params:
        url = url + '?' + urlencode(params)
    if xbmc:
        xbmc.log('Calling URL "{}"'.format(url), xbmc.LOGDEBUG)
        if HEADERS:
            xbmc.log(str(HEADERS), xbmc.LOGDEBUG)
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode('utf-8')
    req = Request(url, data=body, headers=HEADERS)
    try:
        response = urlopen(req)
    except URLError as e:
        if hasattr(e, 'reason'):
            theerror = {'error': 'failed to reach the remote site\nReason: {}'.format(e.reason)}
        elif hasattr(e, 'code'):
            theerror = {'error': 'remote site unable to fulfill the request\nError code: {}'.format(e.code)}
        if default is not None:
            return default
        else:
            return theerror
    if resp_type.lower() == 'json':
        resp = json.loads(response.read().decode('utf-8'))
    else:
        resp = response.read().decode('utf-8')
    # xbmc.log('the api response:\n{}'.format(pformat(resp)), xbmc.LOGDEBUG)
    return resp


def load_info_with_retry(url, params=None, default=None, resp_type='json', data=None,
                         max_retries=5, base_delay=1.0):
    # type: (...) -> Union[dict, list]
    """
    Load info with exponential backoff on HTTP 429 and transient 5xx responses.
    """
    delay = base_delay
    last_result = None
    for attempt in range(max_retries):
        result = load_info(url, params=params, default=default, resp_type=resp_type, data=data)
        last_result = result
        if not isinstance(result, dict) or 'error' not in result:
            return result
        message = result.get('error', '')
        retryable = ('Error code: 429' in message) or ('Error code: 500' in message)
        if retryable and attempt < max_retries - 1:
            if xbmc:
                xbmc.log('Retrying TMDb request after {}s ({})'.format(delay, message), xbmc.LOGDEBUG)
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
            continue
        return result
    return last_result
